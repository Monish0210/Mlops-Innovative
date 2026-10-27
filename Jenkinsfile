pipeline {
    agent any

    options {
        skipDefaultCheckout(false)
        timestamps()
    }

    environment {
        COMPOSE_PROJECT_NAME = 'mlops-innovative'
        IMAGE_NAME = 'mlops-innovative-web:local'
        UPLOADS_DIR = 'C:\\Users\\MONISH\\OneDrive\\Desktop\\Mlops-Innovative\\uploads'
    }

    stages {
        stage('Validate') {
            steps {
                bat 'docker compose config --quiet'
            }
        }

        stage('Build application image') {
            when {
                anyOf {
                    changeset 'Web_Application/**'
                    changeset 'docker-compose.yml'
                    changeset 'Jenkinsfile'
                }
            }
            steps {
                bat 'docker build --tag %IMAGE_NAME% Web_Application'
            }
        }

        stage('Test') {
            when {
                anyOf {
                    changeset 'Web_Application/**'
                    changeset 'docker-compose.yml'
                    changeset 'Jenkinsfile'
                }
            }
            steps {
                bat 'docker run --rm %IMAGE_NAME% python -m py_compile app.py model.py tests/test_app.py'
                bat 'docker run --rm %IMAGE_NAME% python -m unittest discover -s tests -p "test_*.py" -v'
            }
        }

        stage('Deploy monitoring services') {
            steps {
                bat 'docker compose up -d prometheus grafana'
            }
        }

        stage('Deploy web service') {
            when {
                anyOf {
                    changeset 'Web_Application/**'
                    changeset 'docker-compose.yml'
                    changeset 'Jenkinsfile'
                }
            }
            steps {
                bat 'docker compose up -d --no-deps web'
            }
        }

        stage('Verify deployment') {
            steps {
                bat '''powershell -NoProfile -NonInteractive -Command "$checks = @('http://localhost:5000/health', 'http://localhost:9090/-/ready', 'http://localhost:3000/api/health'); foreach ($url in $checks) { $response = Invoke-WebRequest -UseBasicParsing $url; if ($response.StatusCode -ne 200) { exit 1 }; Write-Output ('{0} -> {1}' -f $url, $response.StatusCode) }"'''
            }
        }
    }

    post {
        always {
            bat 'docker compose ps'
        }
    }
}
