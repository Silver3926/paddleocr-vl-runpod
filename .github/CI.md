# CI/CD workflows

The repository uses two separate workflows:

- `ci.yml`: runs Ruff, Pytest, Bandit, and pip-audit on pull requests and manual
  runs. It can also be called as a reusable workflow.
- `release.yml`: on relevant pushes to `main`, first calls `ci.yml` as a quality
  gate and only then builds, scans, and publishes the container. It can also be
  started manually.

The release workflow uses path filters, so README-only and unrelated
Documentation changes do not trigger a container build. Production RunPod
deployments should use the full commit-SHA image tag rather than `latest`.
