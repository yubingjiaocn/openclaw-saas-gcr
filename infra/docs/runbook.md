# Runbook

## Common Operations

### Add a new tenant namespace manually
```bash
kubectl create namespace tenant-{name}
kubectl apply -f templates/resource-quota.yaml -n tenant-{name}
kubectl apply -f templates/network-policy.yaml -n tenant-{name}
```

### Check Operator status
```bash
kubectl get pods -n openclaw-operator-system
kubectl logs -n openclaw-operator-system -l app=openclaw-operator
```

### Check tenant Agent status
```bash
kubectl get openclawinstances -A
kubectl get pods -n tenant-{name}
```
