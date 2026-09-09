# CI/CD workflows

This final branch is based on the latest `main` and combines the complete
production hardening stack:

- `ci.yml`: Ruff, Pytest, Bandit, and pip-audit.
- `release.yml`: CUDA 11.8 container build, immutable image tags, SBOM,
  provenance, and Trivy scanning.

The production image uses a non-root runtime user and pre-baked PaddleOCR-VL
model cache. RunPod deployments should use the full commit-SHA image tag.
