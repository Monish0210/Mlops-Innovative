# MLOps Innovative

Local MLOps deployment for a trained satellite-image damage assessment model.
The project keeps model training for reference and deploys the existing Flask
inference application independently.

## Architecture

```text
Browser
  |
  +--> Flask web application :5000
          |
          +--> /metrics --> Prometheus :9090 --> Grafana :3000
          |
          +--> /uploads --> persistent host directory
```

The application uses the existing `Web_Application/siamUnet.pt` artifact and
does not retrain the model during builds or deployments.

## Repository structure

```text
Model_Training/                 Reference training code and notebook
Web_Application/
  app.py                        Flask application and metrics
  model.py                      SiamUnet architecture
  siamUnet.pt                   Required trained model artifact
  templates/                    Flask HTML templates
  static/css/                   Website styles
  static/sample_images/         Tracked sample website assets
  tests/                        Automated application tests
  Dockerfile                    Runtime image definition
  requirements.txt              Runtime dependencies
monitoring/prometheus.yml       Prometheus scrape configuration
grafana/                        Provisioned datasource and dashboard
docker-compose.yml              Web, Prometheus, and Grafana stack
Jenkinsfile                    CI/CD pipeline
uploads/                        Local persistent uploads; ignored by Git
```

## Prerequisites

- Windows 10/11
- Git
- Docker Desktop with Linux containers enabled
- A GitHub repository
- Jenkins for CI/CD (optional for local development)

No paid cloud service, Kubernetes, MLflow, DVC, or training execution is
required.

## Run locally with Docker Compose

From the repository root:

```powershell
New-Item -ItemType Directory -Force uploads
docker compose up -d --build
```

The services are available at:

| Service | URL |
|---|---|
| Web application | http://localhost:5000/ |
| Health | http://localhost:5000/health |
| Metrics | http://localhost:5000/metrics |
| Prometheus | http://localhost:9090/ |
| Prometheus targets | http://localhost:9090/targets |
| Grafana | http://localhost:3000/ |

Grafana's initial local login is `admin` / `admin`. Change it after the first
login and do not commit credentials.

The provisioned dashboard is **MLOps Application** under the **MLOps** folder.
Prometheus automatically scrapes `web:5000/metrics` on the Compose network.

## Storage and model assets

`Web_Application/siamUnet.pt` is a tracked 14.3 MiB runtime artifact. The
Docker build copies it into the image; the training notebook is not executed.

Sample images are tracked website assets under:

```text
Web_Application/static/sample_images/
```

User uploads and generated segmentation images are not tracked and are not
copied into the image. Compose mounts the host directory below into the web
container at `/uploads`:

```text
C:\Users\MONISH\OneDrive\Desktop\Mlops-Innovative\uploads
```

The location can be changed with `UPLOADS_DIR`:

```powershell
$env:UPLOADS_DIR = 'D:\MlopsData\uploads'
docker compose up -d
```

The application reads the container path from `UPLOAD_FOLDER=/uploads`.
Uploads are validated for supported image type, image integrity, pixel count,
request size, and positive finite GSD. Successful results are retained; failed
requests clean up partial files.

Prometheus data is retained for seven days in the named volume
`mlops-innovative_prometheus-data`. Grafana data is retained in
`mlops-innovative_grafana-data`.

## Stop, restart, and cleanup

Stop containers while preserving uploads and monitoring data:

```powershell
docker compose down
```

Restart without rebuilding:

```powershell
docker compose up -d
```

Inspect status and logs:

```powershell
docker compose ps
docker compose logs -f web
docker compose logs -f prometheus
docker compose logs -f grafana
```

`docker compose down -v` deletes the Prometheus and Grafana named volumes.
Use it only when intentionally deleting monitoring history and Grafana state.
The host `uploads` directory is not deleted by Compose.

Inspect disk usage:

```powershell
Get-ChildItem -Recurse uploads | Measure-Object -Property Length -Sum
docker system df
docker system df --verbose
```

Back up the `uploads` directory and monitoring volumes according to local
requirements. Never automate deletion of persistent uploads.

## Tests and validation

The tests are included in the web image so Jenkins does not require Python on
the Windows service account:

```powershell
docker build --tag mlops-innovative-web:local Web_Application
docker run --rm mlops-innovative-web:local python -m py_compile app.py model.py tests/test_app.py
docker run --rm mlops-innovative-web:local python -m unittest discover -s tests -p "test_*.py" -v
```

Expected test result:

```text
Ran 4 tests
OK
```

## Jenkins CI/CD

The Jenkinsfile assumes Jenkins can run Git, Docker, and Docker Compose. Python
is not required on the Jenkins host because validation and tests run inside the
built application image.

The pipeline:

1. Validates `docker-compose.yml`.
2. Builds the web image when application or build files change.
3. Runs syntax checks and tests inside Docker.
4. Ensures Prometheus and Grafana are running.
5. Recreates only the web service for application deployments.
6. Checks web, Prometheus, and Grafana endpoints.
7. Prints Compose status in the post action.

Configure a Jenkins Pipeline job with **Pipeline script from SCM**:

```text
Repository: https://github.com/Monish0210/Mlops-Innovative.git
Branch: */main
Script path: Jenkinsfile
```

Jenkins runs as a Windows service account in this setup. Verify from a
diagnostic Pipeline that `docker version` shows both Client and Server and
that `docker compose version` works. The configured `UPLOADS_DIR` in the
Jenkinsfile must be a persistent path on the Jenkins machine, outside the
workspace. Change it when Jenkins runs on another computer.

For an application code change, the flow is:

```text
git push
  -> Jenkins checkout
  -> validation
  -> Docker build
  -> tests
  -> web deployment
  -> health checks
```

A failed test stops the pipeline before deployment.

## End-to-end verification

1. Start the stack:

   ```powershell
   docker compose up -d --build
   ```

2. Check all services:

   ```powershell
   docker compose ps
   Invoke-WebRequest -UseBasicParsing http://localhost:5000/health
   Invoke-WebRequest -UseBasicParsing http://localhost:9090/-/ready
   Invoke-WebRequest -UseBasicParsing http://localhost:3000/api/health
   ```

3. Open the web application and submit the two tracked sample images.
4. Confirm generated files appear in `uploads/`, not in Git status.
5. Submit an unsupported, corrupt, or oversized file and expect HTTP `400` or
   `413`; confirm no partial files remain.
6. Open Prometheus targets and confirm `mlops-web` is `UP`.
7. Open Grafana and confirm the MLOps Application dashboard has data after
   requests are generated.
8. Stop and recreate the web container; confirm uploads remain in the host
   directory.
9. Run the Jenkins Pipeline and verify all stages pass.
10. For failure-gate testing, use a temporary failing test and confirm Jenkins
    stops before deployment, then restore the test.

## Git tracking rules

Tracked:

- Application source and templates
- Runtime dependency files
- Model artifact
- Sample website images
- Docker, Compose, Prometheus, Grafana, Jenkins, and test files

Ignored:

- `uploads/` user and generated images
- Python caches and virtual environments
- `.env` and other local secrets
- Docker build-only files and temporary artifacts

Do not commit passwords, tokens, virtual environments, user uploads, or
temporary test output.
