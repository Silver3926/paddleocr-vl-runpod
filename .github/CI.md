# CI/CD workflows

The repository uses two separate workflows:

- `ci.yml`: runs Ruff, Pytest, Bandit, and pip-audit on pull requests, pushes to
  `main`, and manual runs. It never publishes a container image.
- `release.yml`: builds, scans, and publishes the container only for relevant
  changes pushed to `main`, or for a manual run.

The release image is tagged with the full commit SHA and `latest`. Production
RunPod deployments should use the full commit-SHA tag rather than `latest`.
