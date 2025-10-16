# OTel DaemonSet Architecture - Why and How

## Pattern Comparison

### Deployment Pattern (Old)

```
┌─────────────────────────────────────┐
│            Cluster                   │
│                                      │
│  ┌──────────┐  ┌──────────┐        │
│  │  OTel    │  │  OTel    │        │
│  │Collector │  │Collector │        │
│  │  (2-3)   │  │  (2-3)   │        │
│  └────▲─────┘  └────▲─────┘        │
│       │             │               │
│  ┌────┴─────────────┴────┐         │
│  │   All app pods send   │         │
│  │   to any collector    │         │
│  │  (via load balancer)  │         │
│  └───────────────────────┘         │
└─────────────────────────────────────┘

```

**Issues:**

- ❌ Network hops across nodes
- ❌ Fixed replica count
- ❌ Single point of failure risk
- ❌ Load balancer overhead
- ❌ Hard to scale with cluster

### DaemonSet Pattern (Recommended)

```
┌─────────────────────────────────────┐
│            Cluster                   │
│                                      │
│  Node 1      Node 2      Node 3     │
│  ┌─────┐    ┌─────┐    ┌─────┐     │
│  │OTel │    │OTel │    │OTel │     │
│  │Agent│    │Agent│    │Agent│     │
│  └──▲──┘    └──▲──┘    └──▲──┘     │
│     │          │          │         │
│  ┌──┴──┐   ┌──┴──┐   ┢──┴──┐      │
│  │ App │   │ App │   │ App │      │
│  │Pod 1│   │Pod 2│   │Pod 3│      │
│  └─────┘   └─────┘   └─────┘      │
│                                      │
│  Each pod → local node agent        │
└─────────────────────────────────────┘

```

**Benefits:**

- ✅ Node-local collection (fast)
- ✅ Auto-scales with cluster
- ✅ High availability built-in
- ✅ No load balancer needed
- ✅ K8s metadata enrichment

## How DaemonSet Works

### 1. Automatic Deployment

```bash
# Add a node to cluster
gcloud container clusters resize otel-metrics-cluster --num-nodes=5

# DaemonSet automatically deploys to new node
kubectl get pods -n open-telemetry -o wide
# Shows 5 agents (one per node)

```

### 2. Service Discovery

Apps use a **headless service** that routes to the local node's agent:

```yaml
# In app deployment
env:
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: "http://otel-agent.open-telemetry.svc.cluster.local:4318"

```

Kubernetes DNS resolution:

```
1. App on Node 2 queries: otel-agent.open-telemetry.svc.cluster.local
2. DNS returns IPs of ALL agent pods
3. App connects to nearest/local agent (Node 2's agent)
4. Data stays on same node (no network hop)

```

### 3. Kubernetes Metadata Enrichment

The `k8sattributes` processor adds context:

```yaml
processors:
  k8sattributes:
    extract:
      metadata:
        - k8s.namespace.name      # e.g., "fastapi-metrics"
        - k8s.deployment.name     # e.g., "fastapi-metrics"
        - k8s.pod.name           # e.g., "fastapi-metrics-abc123"
        - k8s.pod.uid            # unique pod ID
        - k8s.node.name          # e.g., "gke-cluster-pool-1-xyz"

```

**Result:** Metrics automatically tagged with K8s context:

```
fastapi_custom_requests_total{
  k8s_namespace_name="fastapi-metrics",
  k8s_deployment_name="fastapi-metrics",
  k8s_pod_name="fastapi-metrics-7d9f8-abc",
  k8s_node_name="gke-pool-1-xyz",
  endpoint="/items"
} 42

```

### 4. Resource Efficiency

**Per-Node Resources:**

```
CPU:    100m request, 500m limit
Memory: 128Mi request, 512Mi limit

```

**Cluster with 10 nodes:**

```
Total CPU:    1000m = 1 core
Total Memory: 1280Mi = 1.25GB

```

Compare to centralized (3 collectors):

```
Total CPU:    600m (3 × 200m)
Total Memory: 768Mi (3 × 256Mi)

```

But DaemonSet provides:

- Better fault tolerance
- No single point of failure
- Node-local processing
- Automatic scaling

## Configuration Deep Dive

### Critical Settings

### 1. Batch Processor

```yaml
processors:
  batch:
    timeout: 10s              # Send every 10s
    send_batch_size: 1024     # Or when 1024 metrics collected

```

**Tuning:**

- High volume: Decrease timeout to 5s
- Low volume: Increase to 30s
- Memory constrained: Decrease batch size to 512

### 2. Memory Limiter

```yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512           # Matches pod limit
    spike_limit_mib: 128     # 25% buffer

```

**Purpose:** Prevents OOM kills by dropping data when approaching limit

### 3. K8s Attributes

```yaml
processors:
  k8sattributes:
    auth_type: "serviceAccount"  # Uses pod's SA
    passthrough: false            # Enrich all data
    extract:
      metadata:
        - k8s.namespace.name
        - k8s.deployment.name
        - k8s.pod.name
        - k8s.node.name

```

**Requires:** ClusterRole to read K8s API (included in manifests)

### 4. Resource Attributes

```yaml
processors:
  resource:
    attributes:
      - key: k8s.cluster.name
        value: "otel-metrics-cluster"
        action: insert
      - key: deployment.environment
        value: "production"
        action: insert

```

**Result:** All metrics tagged with cluster and environment

## Advanced Patterns

### 1. Node Selector (Specific Nodes Only)

```yaml
spec:
  template:
    spec:
      nodeSelector:
        workload-type: application  # Only nodes with this label

```

### 2. Tolerations (Run on Tainted Nodes)

```yaml
spec:
  template:
    spec:
      tolerations:
      - key: dedicated
        operator: Equal
        value: observability
        effect: NoSchedule

```

### 3. Priority Class (Critical Workload)

```yaml
spec:
  template:
    spec:
      priorityClassName: system-node-critical

```

### 4. Host Network (Advanced)

```yaml
spec:
  template:
    spec:
      hostNetwork: true  # Use host's network namespace
      dnsPolicy: ClusterFirstWithHostNet

```

**Use case:** Capture node-level metrics, but requires careful port management

## Monitoring the DaemonSet

### Key Metrics

```
# Number of agents (should equal nodes)
count(up{job="otel-agent"})

# Agent memory usage
container_memory_working_set_bytes{pod=~"otel-agent.*"}

# Agent CPU usage
rate(container_cpu_usage_seconds_total{pod=~"otel-agent.*"}[5m])

# Metrics processed
rate(otelcol_processor_batch_batch_send_size_sum[5m])

# Export failures
rate(otelcol_exporter_send_failed_metric_points[5m])

```

### Health Checks

```bash
# All agents healthy?
kubectl get daemonset -n open-telemetry

# Expected: DESIRED = CURRENT = READY = UP-TO-DATE

# Check specific agent
kubectl exec -n open-telemetry otel-agent-xyz -- \
  wget -O- http://localhost:13133 2>/dev/null

```

## Troubleshooting

### Issue: Agent Not on New Node

**Symptom:**

```bash
kubectl get nodes  # Shows 5 nodes
kubectl get pods -n open-telemetry  # Shows 4 agents

```

**Check:**

```bash
kubectl describe daemonset otel-agent -n open-telemetry
# Look for "Events" section

```

**Common causes:**

- Node has taints
- Node doesn't match nodeSelector
- Resource requests can't be satisfied

**Solution:**

```bash
# Check node taints
kubectl describe node <node-name> | grep Taints

# Add toleration if needed
kubectl edit daemonset otel-agent -n open-telemetry

```

### Issue: High Memory Usage

**Symptom:**

```bash
kubectl top pods -n open-telemetry
# Shows agents using >400Mi

```

**Solutions:**

1. Reduce batch size:

```yaml
processors:
  batch:
    send_batch_size: 512  # Reduced from 1024

```

1. Increase export frequency:

```yaml
processors:
  batch:
    timeout: 5s  # Reduced from 10s

```

1. Increase pod limit:

```yaml
resources:
  limits:
    memory: 768Mi  # Increased from 512Mi

```

### Issue: Metrics Missing K8s Attributes

**Symptom:**
Metrics don't have `k8s_namespace_name`, `k8s_pod_name`, etc.

**Check:**

```bash
# Verify RBAC
kubectl get clusterrole otel-agent
kubectl get clusterrolebinding otel-agent

# Check agent logs for permission errors
kubectl logs -n open-telemetry -l app=otel-agent | grep -i "forbidden\|denied"

```

**Solution:**

```bash
# Reapply RBAC
kubectl apply -f k8s-manifests.yaml

```

### Issue: Prometheus Not Scraping

**Check ServiceMonitor:**

```bash
kubectl get servicemonitor -n open-telemetry -o yaml

```

**Verify selector matches Prometheus:**

```bash
kubectl get prometheus -n monitoring -o yaml | grep -A10 serviceMonitorSelector

```

**Common fix:**

```bash
# Label the namespace
kubectl label namespace open-telemetry monitoring=enabled

```

## Performance Tuning

### Low-Volume Environments (< 1k metrics/sec)

```yaml
processors:
  batch:
    timeout: 30s
    send_batch_size: 512
  memory_limiter:
    limit_mib: 256
resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 200m
    memory: 256Mi

```

### High-Volume Environments (> 10k metrics/sec)

```yaml
processors:
  batch:
    timeout: 5s
    send_batch_size: 2048
  memory_limiter:
    limit_mib: 1024
resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: 1000m
    memory: 1Gi

```

## Migration from Deployment to DaemonSet

If you already have a Deployment-based setup:

```bash
# 1. Deploy DaemonSet alongside existing deployment
kubectl apply -f k8s-manifests.yaml

# 2. Update apps to use new endpoint (rolling update)
kubectl set env deployment/my-app \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-agent.open-telemetry.svc:4318 \
  -n my-namespace

# 3. Monitor both collectors
kubectl top pods -n open-telemetry
kubectl top pods -n old-namespace

# 4. Once all apps migrated, remove old deployment
kubectl delete deployment otel-collector -n old-namespace

```

## Best Practices

1. **Resource Limits**: Always set limits to prevent node resource exhaustion
2. **RBAC**: Use least-privilege for k8sattributes processor
3. **Batch Processing**: Tune based on volume and latency requirements
4. **Health Checks**: Monitor agent health endpoints
5. **Version Management**: Use specific image tags, not `latest`
6. **Config Management**: Use ConfigMaps, restart agents after changes
7. **Monitoring**: Track agent metrics in Prometheus
8. **Documentation**: Document custom processors and exporters

## When NOT to Use DaemonSet

Use Deployment instead if:

- **Centralized processing**: Need sophisticated processing not suitable for edge
- **External collectors**: Sending to collectors outside cluster
- **Resource constraints**: Very large cluster where per-node overhead is significant
- **Gateway pattern**: Need a gateway for external traffic

DaemonSet is ideal for:

- ✅ In-cluster telemetry collection
- ✅ High-volume environments
- ✅ Low-latency requirements
- ✅ Kubernetes-native applications
- ✅ Auto-scaling clusters

## Summary

The DaemonSet pattern provides:

- **Scalability**: Automatic per-node deployment
- **Performance**: Node-local collection
- **Resilience**: No single point of failure
- **Simplicity**: Kubernetes handles scheduling
- **Enrichment**: Automatic K8s metadata

This is the **recommended production pattern** for OTel in Kubernetes.