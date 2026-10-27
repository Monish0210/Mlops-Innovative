import os
import __main__
import math
from flask import Flask, render_template, request, send_from_directory, url_for
from PIL import Image
import torch
from torchvision import transforms
from model import SiamUnet
import json
import uuid
import numpy as np
from werkzeug.utils import secure_filename

app = Flask(__name__)

# --- CONFIGURATION ---
UPLOAD_FOLDER = os.environ.get(
    'UPLOAD_FOLDER',
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'uploads'))
)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MODEL_PATH'] = os.path.join(os.path.dirname(__file__), 'siamUnet.pt') # Use os.path.join for safety
app.config['DEFAULT_GSD'] = 0.5
app.config['ORIGINAL_IMAGE_SIZE'] = 1024
app.config['MODEL_IMAGE_SIZE'] = 256
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_UPLOAD_BYTES', 32 * 1024 * 1024))
app.config['MAX_IMAGE_PIXELS'] = int(os.environ.get('MAX_IMAGE_PIXELS', 25_000_000))
app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'jpg', 'jpeg', 'png', 'webp', 'tif', 'tiff'}

# Ensure local upload folder exists right at the start
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Device setup
device = torch.device('cpu')

# Image preprocessing
transform = transforms.Compose([
    transforms.Resize((app.config['MODEL_IMAGE_SIZE'], app.config['MODEL_IMAGE_SIZE'])),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

# Damage classes and color mapping
DAMAGE_CLASSES = {
    0: 'Background',
    1: 'No Damage',
    2: 'Minor Damage',
    3: 'Major Damage',
    4: 'Destroyed'
}
CLASS_COLORS_RGB = [
    (0, 0, 0),       # 0: Background (Black)
    (0, 255, 0),     # 1: No Damage (Green)
    (255, 165, 0),   # 2: Minor Damage (Orange)
    (128, 0, 128),   # 3: Major Damage (Purple)
    (255, 0, 0)      # 4: Destroyed (Red)
]

# --- MODEL LOADING ---
# Load model once when the app starts, not on every request
def load_model():
    print("Loading model...")
    try:
        model_path = app.config['MODEL_PATH']
        if not os.path.exists(model_path):
            print(f"ERROR: Model file not found at {model_path}")
            return "not_found"
        
        # The saved artifact was created from a notebook, where SiamUnet was
        # serialized as __main__.SiamUnet.
        __main__.SiamUnet = SiamUnet
        model_loaded = torch.load(model_path, map_location=device, weights_only=False)
        model_loaded.eval()
        print("Model loaded.")
        return model_loaded
    except Exception as e:
        print(f"ERROR loading model: {e}")
        return "not_found"

model = load_model()

def validate_uploaded_image(file_storage, destination):
    filename = secure_filename(file_storage.filename or '')
    extension = os.path.splitext(filename)[1].lower().lstrip('.')
    if not filename or extension not in app.config['ALLOWED_IMAGE_EXTENSIONS']:
        raise ValueError('Unsupported image type. Use JPG, PNG, WEBP, or TIFF.')

    file_storage.save(destination)
    try:
        with Image.open(destination) as image:
            image.verify()
        with Image.open(destination) as image:
            width, height = image.size
            if width * height > app.config['MAX_IMAGE_PIXELS']:
                raise ValueError('Image dimensions exceed the configured limit.')
    except ValueError:
        if os.path.exists(destination):
            os.remove(destination)
        raise
    except Exception as error:
        if os.path.exists(destination):
            os.remove(destination)
        raise ValueError('Invalid or corrupted image.') from error

    return filename


@app.errorhandler(413)
def request_entity_too_large(_error):
    return 'Uploaded files exceed the configured size limit.', 413

@app.route('/', methods=['GET', 'POST'])
def index():
    if model == "not_found":
        return f"Model file '{app.config['MODEL_PATH']}' not found or failed to load.", 500

    if request.method == 'POST':
        if 'pre_image' not in request.files or 'post_image' not in request.files:
            return "Missing pre or post image file", 400
            
        pre_image_file = request.files['pre_image']
        post_image_file = request.files['post_image']

        if not pre_image_file.filename or not post_image_file.filename:
            return "No selected file", 400
        
        try:
            gsd = float(request.form.get('gsd', app.config['DEFAULT_GSD']))
        except (TypeError, ValueError):
            return "Ground Sample Distance must be a valid positive number.", 400
        if not math.isfinite(gsd) or gsd <= 0:
            return "Ground Sample Distance must be a valid positive number.", 400
            
        
        original_area_per_pixel = gsd * gsd
        scale_factor_squared = (app.config['ORIGINAL_IMAGE_SIZE'] / app.config['MODEL_IMAGE_SIZE']) ** 2
        area_per_predicted_pixel = scale_factor_squared * original_area_per_pixel
        

        unique_id = str(uuid.uuid4())
        pre_filename = f"pre_{unique_id}_{secure_filename(pre_image_file.filename)}"
        post_filename = f"post_{unique_id}_{secure_filename(post_image_file.filename)}"
        output_filename = f"output_{unique_id}.png"

        pre_image_path = os.path.join(app.config['UPLOAD_FOLDER'], pre_filename)
        post_image_path = os.path.join(app.config['UPLOAD_FOLDER'], post_filename)
        output_image_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        try:
            try:
                validate_uploaded_image(pre_image_file, pre_image_path)
                validate_uploaded_image(post_image_file, post_image_path)
            except ValueError as error:
                for path in (pre_image_path, post_image_path):
                    if os.path.exists(path):
                        os.remove(path)
                return str(error), 400

            with Image.open(pre_image_path) as source:
                pre_image = source.convert("RGB")
            with Image.open(post_image_path) as source:
                post_image = source.convert("RGB")
            pre_image_tensor = transform(pre_image).unsqueeze(0).to(device)
            post_image_tensor = transform(post_image).unsqueeze(0).to(device)

            with torch.no_grad():
                _, _, damage_output = model(pre_image_tensor, post_image_tensor)
                preds_cls_tensor = torch.argmax(torch.nn.functional.softmax(damage_output, dim=1), dim=1)
                
            # --- Analysis Calculation ---
            preds_cls_np = preds_cls_tensor.cpu().numpy().flatten() 
            unique_classes, counts = np.unique(preds_cls_np, return_counts=True)
            total_predicted_pixels = preds_cls_np.size
            
            damage_analysis_percent, damage_analysis_area = {}, {}
            total_damaged_area = 0.0

            for i, count in zip(unique_classes, counts):
                class_name = DAMAGE_CLASSES.get(i, "Unknown")
                percentage = (count / total_predicted_pixels) * 100
                area_m2 = count * area_per_predicted_pixel 
                
                damage_analysis_percent[class_name] = percentage
                damage_analysis_area[class_name] = area_m2 

                if i > 0: # Assumes class 0 is 'Background'
                    total_damaged_area += area_m2
            
           
            colors = torch.tensor(CLASS_COLORS_RGB, dtype=torch.uint8)
            output_image_tensor = colors[preds_cls_tensor.squeeze(0).cpu().long()].permute(2, 0, 1)
            output_image = transforms.ToPILImage()(output_image_tensor)
            output_image.save(output_image_path)

            return render_template('index.html',
                                   pre_image_rel_path=url_for('uploaded_file', filename=pre_filename),
                                   post_image_rel_path=url_for('uploaded_file', filename=post_filename),
                                   output_image_rel_path=url_for('uploaded_file', filename=output_filename),
                                   damage_analysis_percent_json=json.dumps(damage_analysis_percent),
                                   damage_analysis_area_json=json.dumps(damage_analysis_area),
                                   damage_analysis_area_dict=damage_analysis_area, 
                                   total_damaged_area=total_damaged_area,
                                   gsd_used=gsd)
        except Exception as e:
            print(f"Error during prediction: {e}")
            # Clean up saved files if an error occurs
            if os.path.exists(pre_image_path): os.remove(pre_image_path)
            if os.path.exists(post_image_path): os.remove(post_image_path)
            if os.path.exists(output_image_path): os.remove(output_image_path)
            return f"An error occurred during processing: {e}", 500

    return render_template('index.html', gsd_used=app.config['DEFAULT_GSD']) 

@app.route('/sample_images')
def sample_images():
    return render_template('sample_images.html')


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/evaluation')
def evaluation():
    metrics = {
        "Overall Pixel Accuracy": 96.61, 
        "Mean IoU (mIoU)": 49.69,       
        "Macro Average Precision": 65.97, 
        "Macro Average Recall": 58.97,    
        "Macro Average F1-Score": 61.81, 
        "class_metrics": [
            {"name": "Background", "iou": 96.87, "precision": 98.67, "recall": 98.16, "f1": 98.41},  # Example
            {"name": "No Damage", "iou": 57.95, "precision": 67.49, "recall": 80.38, "f1": 73.38},    # Example
            {"name": "Minor Damage", "iou": 7.90, "precision": 32.12, "recall": 9.48, "f1": 9.48}, # Example
            {"name": "Major Damage", "iou": 38.62, "precision": 63.28, "recall": 49.77, "f1": 55.72},  # Example
            {"name": "Destroyed", "iou": 38.27, "precision": 53.01, "recall": 57.93, "f1": 55.36}     # Example
        ]
    }
    return render_template('evaluation.html', metrics=metrics)


@app.route('/health')
def health():
    if model == "not_found":
        return {"status": "unhealthy", "model_loaded": False}, 503
    return {"status": "healthy", "model_loaded": True}, 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)