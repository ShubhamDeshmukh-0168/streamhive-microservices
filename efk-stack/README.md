# EFK Stack (Elasticsearch + Fluent Bit + Kibana)

Centralized logging for all StreamHive pods.

## Setup
```bash
kubectl create namespace logging   # <-- CHANGE: namespace name if you prefer something else

# Elasticsearch + Kibana (using the official Bitnami / Elastic Helm charts is recommended)
helm repo add elastic https://helm.elastic.co
helm repo update
helm install elasticsearch elastic/elasticsearch -n logging   # <-- CHANGE: set resource limits/values.yaml for your cluster size
helm install kibana elastic/kibana -n logging

# Fluent Bit as a DaemonSet (ships container logs from every node)
helm repo add fluent https://fluent.github.io/helm-charts
helm install fluent-bit fluent/fluent-bit -n logging \
  --set backend.es.host=elasticsearch-master.logging.svc.cluster.local   # <-- CHANGE if your ES service name differs
```

Access Kibana:
```bash
kubectl port-forward svc/kibana-kibana -n logging 5601:5601   # <-- CHANGE port if 5601 is taken locally
```
