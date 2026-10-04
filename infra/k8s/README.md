# Kubernetes (k3s)

Production runs on k3s with Kustomize overlays. Phase 0 ships the skeleton only; the manifests are written in Phase 4 together with the backup, restore and alerting work.

```text
base/                 one Deployment or StatefulSet per Compose service, NetworkPolicies mirroring the Compose networks
overlays/production/  replicas, resource limits, ingress through Caddy, external secrets
```

Rules carried over from the Compose stack: the `data` network has no egress, the API never reaches object storage with write access to preservation buckets, the policy engine is a sidecar-less separate Deployment, and every secret comes from the cluster secret store, never from a manifest.
