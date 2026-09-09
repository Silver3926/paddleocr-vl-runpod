name: CI/CD

This workflow is defined in `.github/workflows/docker.yml` and runs:

1. Ruff linting
2. Pytest unit tests
3. Bandit security checks
4. pip-audit dependency checks
5. Docker image build and Trivy scanning

The Docker build only runs after the `quality` job succeeds. Pull requests run
quality checks but do not push an image. Pushes to `main` and manual runs build
and publish the image to GHCR.
