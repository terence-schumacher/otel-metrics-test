# Deploy OpenTelemetry Metrics to Google Cloud Platform

## Prerequisites
- GCP Account with billing enabled
- `gcloud` CLI installed and authenticated
- `kubectl` installed
- `helm` installed (optional)

## Step-by-Step Deployment

### 1. Set up GCP Project
```bash
# Set your project ID
export PROJECT_ID="your-project-id"
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable container.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable monitoring.googleapis.com
gcloud services enable logging.googleapis.com
```

### 2. Create GKE Cluster
```bash
# Create a GKE cluster
gcloud container clusters create otel-metrics-cluster \
  --region us-central1 \
  --num-nodes 3 \
  --node-locations us-central1-a,us-central1-b,us-central1-c \
  --enable-autoscaling \
  --min-nodes 3 \
  --max-nodes 10 \
  --machine-type n1-standard-2 \
  --enable-cloud-logging \
  --enable-cloud-monitoring \
  --enable-ip-alias \
  --network "projects/$PROJECT_ID/global/networks/default" \
  --subnetwork "projects/$PROJECT_ID/regions/us-central1/subnetworks/default" \
  --addons HorizontalPodAutoscaling,HttpLoadBalancing \
  --workload-pool=$PROJECT_ID.svc.id.goog

# Get cluster credentials
gcloud container clusters get-credentials otel-metrics-cluster --region us-central1
```

### 3. Set up Workload Identity (for GCP service integration)
```bash
# Create GCP service account
gcloud iam service-accounts create otel-collector \
  --display-name="OpenTelemetry Collector Service Account"

# Grant necessary permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:otel-collector@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:otel-collector@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:otel-collector@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudtrace.agent"

# Bind the KSA to GSA
kubectl create namespace otel-metrics

gcloud iam service-accounts add-iam-policy-binding \
  otel-collector@$PROJECT_ID.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:$PROJECT_ID.svc.id.goog[otel-metrics/otel-collector]"
```

### 4. Build and Push Docker Image

#### Option A: Using Cloud Build (Recommended)
```bash
# Submit build to Cloud Build
gcloud builds submit \
  --config=helm/otel-metrics-test/cloudbuild.yaml \
  --substitutions=_PROJECT_ID=$PROJECT_ID
```

#### Option B: Build Locally and Push
```bash
# Build the Docker image locally
docker build -t gcr.io/$PROJECT_ID/otel-collector:latest \
  -f helm/otel-metrics-test/Dockerfile \
  helm/otel-metrics-test/

# Configure Docker to use gcloud as credential helper
gcloud auth configure-docker

# Push the image
docker push gcr.io/$PROJECT_ID/otel-collector:latest
```

### 5. Deploy to GKE

#### Option A: Using Helm
```bash
# Update values.yaml with your project ID
sed -i "s/YOUR_PROJECT_ID/$PROJECT_ID/g" helm/otel-metrics-test/values.yaml

# Install with Helm
helm install otel-metrics ./helm/otel-metrics-test \
  --namespace otel-metrics \
  --create-namespace \
  --set image.repository=gcr.io/$PROJECT_ID/otel-collector \
  --set image.tag=latest
```

#### Option B: Using kubectl
```bash
# Replace PROJECT_ID in the deployment file
sed -i "s/\${PROJECT_ID}/$PROJECT_ID/g" helm/otel-metrics-test/k8s-deployment.yaml
sed -i "s/YOUR_PROJECT_ID/$PROJECT_ID/g" helm/otel-metrics-test/k8s-deployment.yaml

# Apply the Kubernetes manifests
kubectl apply -f helm/otel-metrics-test/k8s-deployment.yaml
```

### 6. Verify Deployment
```bash
# Check if pods are running
kubectl get pods -n otel-metrics

# Check service endpoints
kubectl get svc -n otel-metrics

# Get the external IP of the LoadBalancer
kubectl get svc otel-collector -n otel-metrics -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Check logs
kubectl logs -n otel-metrics -l app=otel-collector --tail=50

# Test health endpoint (replace EXTERNAL_IP)
curl http://EXTERNAL_IP:13133
```

### 7. Configure Firewall Rules (if needed)
```bash
# Allow traffic to OTLP ports
gcloud compute firewall-rules create allow-otel-metrics \
  --allow tcp:4317,tcp:4318,tcp:8889,tcp:13133 \
  --source-ranges 0.0.0.0/0 \
  --target-tags otel-metrics
```

### 8. Set up Monitoring & Alerting
```bash
# View metrics in Google Cloud Console
echo "https://console.cloud.google.com/monitoring/metrics-explorer?project=$PROJECT_ID"

# Create an alert policy (example)
gcloud alpha monitoring policies create \
  --notification-channels=YOUR_CHANNEL_ID \
  --display-name="OTel Collector High Memory Usage" \
  --condition="resource.type=\"k8s_container\"
    AND resource.labels.namespace_name=\"otel-metrics\"
    AND metric.type=\"kubernetes.io/container/memory/used_bytes\"" \
  --condition-threshold-value=500000000 \
  --condition-threshold-duration=60s
```

### 9. Configure CI/CD with Cloud Build

```bash
# Create Cloud Build trigger
gcloud builds triggers create github \
  --repo-name=your-repo \
  --repo-owner=your-github-username \
  --branch-pattern="^main$" \
  --build-config=helm/otel-metrics-test/cloudbuild.yaml
```

## Sending Metrics to the Collector

Once deployed, you can send metrics to:
- **OTLP gRPC**: `otel-collector.otel-metrics.svc.cluster.local:4317` (internal)
- **OTLP HTTP**: `otel-collector.otel-metrics.svc.cluster.local:4318` (internal)
- **External**: Use the LoadBalancer IP obtained in step 6

Example using curl:
```bash
EXTERNAL_IP=$(kubectl get svc otel-collector -n otel-metrics -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

curl -X POST http://$EXTERNAL_IP:4318/v1/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "resourceMetrics": [{
      "resource": {
        "attributes": [{
          "key": "service.name",
          "value": {"stringValue": "test-service"}
        }]
      },
      "scopeMetrics": [{
        "metrics": [{
          "name": "test.counter",
          "unit": "1",
          "sum": {
            "dataPoints": [{
              "asInt": "100",
              "timeUnixNano": "'$(date +%s%N)'"
            }]
          }
        }]
      }]
    }]
  }'
```

## Cleanup
```bash
# Delete the GKE cluster
gcloud container clusters delete otel-metrics-cluster --region us-central1

# Delete service account
gcloud iam service-accounts delete otel-collector@$PROJECT_ID.iam.gserviceaccount.com

# Delete container images
gcloud container images delete gcr.io/$PROJECT_ID/otel-collector:latest
```

## Troubleshooting

1. **Pods not starting**: Check logs with `kubectl logs -n otel-metrics <pod-name>`
2. **No external IP**: Verify LoadBalancer service is created correctly
3. **Metrics not showing in GCP**: Check IAM permissions and Workload Identity binding
4. **Connection refused**: Check firewall rules and security groups

## Cost Optimization Tips
- Use preemptible nodes for non-production workloads
- Set up autoscaling based on actual usage
- Use regional clusters instead of zonal for better availability
- Monitor and optimize resource requests/limits