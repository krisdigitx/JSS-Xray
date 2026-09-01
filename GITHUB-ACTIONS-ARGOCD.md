# GitHub Actions -> Docker Hub -> ArgoCD

Added `.github/workflows/build-and-promote.yml`.

Flow:

`push to main -> backend tests -> build/push Docker images -> update immutable image tags in values-home-lab.yaml -> commit -> ArgoCD auto-sync`

Required GitHub repository secrets:
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Also enable:

`Settings -> Actions -> General -> Workflow permissions -> Read and write permissions`

ArgoCD should track:
- chart path: `deploy/helm/jss-xray`
- values file: `values-home-lab.yaml`
- automated sync enabled

The promotion commit changes only `values-home-lab.yaml`, which is excluded from the workflow trigger, preventing a CI loop.
