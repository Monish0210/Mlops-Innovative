import io
import sys
import unittest
from pathlib import Path

from PIL import Image

APPLICATION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APPLICATION_DIR))

import app


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.app.config.update(TESTING=True)
        cls.client = app.app.test_client()

    def test_health_reports_loaded_model(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            'status': 'healthy',
            'model_loaded': True,
        })

    def test_existing_pages_and_sample_assets(self):
        for path in ('/', '/sample_images', '/evaluation', '/metrics'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

        sample_path = (
            '/static/sample_images/'
            'mexico-earthquake_00000142_pre_disaster.png'
        )
        with self.client.get(sample_path) as response:
            self.assertEqual(response.status_code, 200)

    def test_invalid_upload_is_rejected(self):
        response = self.client.post(
            '/',
            data={
                'pre_image': (io.BytesIO(b'not-an-image'), 'pre.txt'),
                'post_image': (io.BytesIO(b'not-an-image'), 'post.txt'),
                'gsd': '0.5',
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(response.status_code, 400)

    def test_valid_image_can_be_opened_for_fixtures(self):
        image = io.BytesIO()
        Image.new('RGB', (8, 8), (0, 0, 0)).save(image, format='PNG')
        self.assertGreater(len(image.getvalue()), 0)


if __name__ == '__main__':
    unittest.main()
