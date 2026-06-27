# Prometheus + Grafana

Metrics and dashboards for the StreamHive cluster.

## Setup
```bash
kubectl create namespace monitoring   # <-- CHANGE: namespace name if you prefer something else

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring
```

## Access Grafana
```bash
kubectl port-forward svc/prometheus-grafana -n monitoring 3000:80   # <-- CHANGE port if 3000 is taken locally
```
Default login: `admin` / get the password with:
```bash
kubectl get secret prometheus-grafana -n monitoring -o jsonpath="{.data.admin-password}" | base64 --decode
```

Import a Kubernetes cluster monitoring dashboard (e.g. dashboard ID `315` or `7249` from grafana.com) to visualize node/pod CPU, memory, and network usage for all StreamHive services.
