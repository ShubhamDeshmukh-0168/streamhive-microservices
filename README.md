# 🐝 StreamHive

A multi-category digital entertainment & services "super-app" — Movies, Music, Gaming, Food Delivery, and a shared Wallet — built as a microservices learning project on **AWS EKS**, deployed via **GitOps (ArgoCD)**, with **EFK** logging and **Prometheus/Grafana** monitoring.

Each category is its own independently deployable micro-frontend, all routed through a single NGINX Ingress, talking to one shared Flask backend (`core-api`) and a MySQL database.

---

## 📁 Project Structure
```
streamhive/
├── backend/                     # Flask core-api (auth, watchlist, bookings, wallet)
│   ├── app.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── schema.sql
│   ├── .env.example
│   ├── core-api-cm.yml          # ConfigMap (env vars)
│   └── core-api-deployment.yml  # Deployment + Service
│
├── frontend/
│   ├── home/                    # Landing page
│   ├── movies/
│   ├── music/
│   ├── gaming/
│   ├── food-delivery/
│   ├── streamwallet/            # Wallet top-up UI
│   │   (each has: index.html, Dockerfile, nginx.conf, deployment.yml)
│   └── home/ingress.yml         # Shared Ingress routing all paths
│
├── EKS-Terraform/
│   ├── main.tf                  # VPC, EKS cluster, node group, bastion
│   ├── rds.tf                   # MySQL RDS instance
│   └── variables.tf
│
├── k8s-argocd/
│   ├── backend-app.yml          # ArgoCD Application for backend
│   └── frontend-app.yml         # ArgoCD Application for frontend
│
├── efk-stack/README.md          # Elasticsearch + Fluent Bit + Kibana setup
├── grafana-prometheus/README.md # Prometheus + Grafana setup
└── .github/workflows/ci.yml     # CI/CD: build → push to ECR → patch manifests → commit
```

---

## ⚠️ Things you MUST change before using this

Every placeholder is marked with a `# <-- CHANGE:` comment in the file itself. Here's the full list in one place:

| File | What to change |
|---|---|
| `EKS-Terraform/variables.tf` | `aws_region`, `bastion_key_name`, `db_username`, `db_password` |
| `EKS-Terraform/main.tf` | Bastion AMI ID (`ami-...`), bastion SSH `cidr_blocks` (don't leave it open to `0.0.0.0/0`) |
| `backend/core-api-cm.yml` | `DB_HOST` (use the Terraform `rds_endpoint` output), `DB_USER`, `DB_PASSWORD`, `MAIL_USERNAME`, `MAIL_PASSWORD` |
| `backend/.env.example` | Same as above, for local dev — copy to `.env`, never commit `.env` itself |
| `backend/core-api-deployment.yml` | `image:` — your ECR account ID/region (auto-patched by CI after first run, but set correctly the first time) |
| `frontend/*/deployment.yml` (all 6) | `image:` — same as above |
| `.github/workflows/ci.yml` | `AWS_REGION`, `ECR_REGISTRY` (your AWS account ID), and add GitHub repo secrets `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` |
| `k8s-argocd/backend-app.yml` & `frontend-app.yml` | `repoURL` — your actual GitHub repo URL, `targetRevision` if not `main`, `namespace` if not `microservices` |
| `efk-stack/README.md` | namespace names, Elasticsearch service name if it differs from the Helm default |
| `grafana-prometheus/README.md` | namespace, local port-forward port if `3000` is taken |

---

## 🚀 Setup Steps

### 1. Provision infrastructure
```bash
cd EKS-Terraform
terraform init
terraform apply       # creates VPC, EKS cluster, node group, bastion, RDS
```
Grab the RDS endpoint from the output and put it into `backend/core-api-cm.yml` → `DB_HOST`.

### 2. Connect kubectl to the new cluster
```bash
aws eks update-kubeconfig --name hive-eks-cluster --region us-west-2   # <-- CHANGE region if different
```

### 3. Load the database schema
```bash
mysql -h <rds_endpoint> -u admin -p < backend/schema.sql
```

### 4. Install cluster add-ons (one-time, manual)
```bash
# NGINX Ingress Controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/aws/deploy.yaml

# ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.password}" | base64 --decode
```

### 5. First-time manual deploy (before ArgoCD takes over)
```bash
kubectl create namespace microservices
kubectl apply -f backend/core-api-cm.yml -n microservices
kubectl apply -f backend/core-api-deployment.yml -n microservices

kubectl apply -f frontend/home/deployment.yml -n microservices
kubectl apply -f frontend/movies/deployment.yml -n microservices
kubectl apply -f frontend/music/deployment.yml -n microservices
kubectl apply -f frontend/gaming/deployment.yml -n microservices
kubectl apply -f frontend/food-delivery/deployment.yml -n microservices
kubectl apply -f frontend/streamwallet/deployment.yml -n microservices

kubectl apply -f frontend/home/ingress.yml -n microservices
```

### 6. Register ArgoCD apps (so future pushes auto-deploy)
```bash
kubectl apply -f k8s-argocd/backend-app.yml
kubectl apply -f k8s-argocd/frontend-app.yml
```

### 7. Push code → CI/CD takes over from here
Every push to `main` now automatically: builds Docker images for every changed service → pushes to ECR → patches the `image:` tag in each `deployment.yml` → commits back to the repo → ArgoCD detects the change and syncs the cluster.

### 8. (Optional) Observability
Follow `efk-stack/README.md` for centralized logs and `grafana-prometheus/README.md` for metrics dashboards.

---

## 🔌 API Endpoints (core-api)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/signup/request` | Start signup, sends OTP email |
| POST | `/api/signup/verify` | Verify OTP, creates the account |
| POST | `/api/login/request` | Start login (OTP only required once/day) |
| POST | `/api/login/verify` | Verify login OTP |
| GET | `/api/watchlist?email=` | Get current watchlist/cart |
| POST | `/api/watchlist/items` | Add an item to watchlist |
| POST | `/api/bookings` | Convert watchlist into a confirmed booking, sends receipt email |
| POST | `/api/wallet/topups` | Top up StreamWallet balance |
| POST | `/api/activity` | Log which micro-app a user opened |
| GET | `/api/history?email=` | Combined bookings + activity history |

---

## 🛡️ Before going to production, also fix
- Move `DB_PASSWORD` / `MAIL_PASSWORD` out of the ConfigMap into a **Kubernetes Secret** instead (ConfigMaps are not encrypted).
- Restrict CORS (`Access-Control-Allow-Origin: *`) to your actual frontend domains.
- Restrict the bastion security group's SSH ingress to your own IP, not `0.0.0.0/0`.
- Set `skip_final_snapshot = false` and `multi_az = true` on the RDS instance for production durability.
