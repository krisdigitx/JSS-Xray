# amazon-orders-app

Self-hosted Amazon.co.uk order search application.

It reads Amazon.co.uk transactional emails from Gmail using the Gmail API, parses order and delivery events, stores them in PostgreSQL, and exposes a searchable web UI.

## Repository responsibilities

This repository owns:
- FastAPI backend
- Amazon.co.uk email parser
- Gmail read-only ingestion
- PostgreSQL schema/models
- React/Next.js frontend
- Docker images
- Helm chart
- GitHub Actions that test, build and push images to Docker Hub

Your separate `home-lab` repository should own:
- ArgoCD `Application`
- environment-specific Helm values
- Vault/Vault Secrets Operator configuration
- MetalLB IPs
- ingress/DNS
- monitoring policy

## Images

GitHub Actions pushes:

- `<dockerhub-user>/amazon-orders-backend:<tag>`
- `<dockerhub-user>/amazon-orders-frontend:<tag>`

For `main`, it also publishes `latest`. Every build is tagged with the Git SHA.

## GitHub repository secrets

Create these in **Settings -> Secrets and variables -> Actions**:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Use a Docker Hub access token, not your Docker Hub password.

## Gmail OAuth

The runtime requires Gmail read-only OAuth credentials:

- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REFRESH_TOKEN`

Create an OAuth client in Google Cloud, enable Gmail API, and run:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python ../scripts/generate_gmail_token.py
```

The script requests only `https://www.googleapis.com/auth/gmail.readonly`.

Store the resulting values in Vault for Kubernetes. Never commit them.

## Local development

Create `.env` from `.env.example`, then:

```bash
docker compose up --build
```

Open:
- UI: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`

Run tests:

```bash
cd backend
pip install -r requirements.txt
pytest
```

## Helm

The reusable chart is under:

```text
deploy/helm/amazon-orders
```

Your `home-lab` ArgoCD Application can use this chart from this repository and `$values` from `home-lab`.

Example multi-source ArgoCD application:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: amazon-orders
  namespace: argocd
spec:
  project: default
  sources:
    - repoURL: https://github.com/YOUR_GITHUB_USER/amazon-orders-app.git
      targetRevision: main
      path: deploy/helm/amazon-orders
      helm:
        valueFiles:
          - $values/apps/amazon-orders/values.yaml
    - repoURL: https://github.com/YOUR_GITHUB_USER/home-lab.git
      targetRevision: main
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: amazon-orders
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

Example `home-lab/apps/amazon-orders/values.yaml`:

```yaml
backend:
  image:
    repository: YOUR_DOCKERHUB_USER/amazon-orders-backend
    tag: sha-REPLACE_ME

frontend:
  image:
    repository: YOUR_DOCKERHUB_USER/amazon-orders-frontend
    tag: sha-REPLACE_ME
  service:
    type: LoadBalancer
    loadBalancerIP: 192.168.1.230

existingSecret: amazon-orders-secrets

postgresql:
  persistence:
    storageClass: local-path
    size: 10Gi
```

The Kubernetes secret named by `existingSecret` must contain:

```text
POSTGRES_PASSWORD
GMAIL_CLIENT_ID
GMAIL_CLIENT_SECRET
GMAIL_REFRESH_TOKEN
```

The chart constructs `DATABASE_URL` internally.

## Gmail sync

A Kubernetes CronJob runs the same backend image with:

```bash
python -m app.sync
```

The default schedule is every 30 minutes.

The importer searches trusted Amazon.co.uk transactional senders and processes:
- Ordered
- Dispatched
- Out for delivery
- Delivered
- Cancelled/Canceled
- Refund/Refunded
- Return/Returned

Gmail message IDs are stored to make ingestion idempotent.

## Security

- Gmail permission is read-only.
- Do not put OAuth credentials in Git.
- Do not expose PostgreSQL outside the cluster.
- Keep the UI on LAN until authentication is added.
- Pin production deployments to immutable `sha-*` image tags.
