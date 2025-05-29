# CronDispatcher

## Feature Overview

CronDispatcher is a Kubernetes namespace-level cron job management platform that implements containerized orchestration and lifecycle management of scheduled tasks through a declarative configuration mode driven by ConfigMap.

## Project Structure

```
CronDispatcher/
├── src/                          # Source code directory
│   ├── main.py                   # Main program file
│   └── pod_creator.py            # Pod creator
├── config/                       # Configuration files directory
│   ├── deployment.yaml           # Kubernetes deployment configuration
│   └── cron-dispatcher-config.yaml # ConfigMap configuration example
├── scripts/                      # Scripts directory
│   ├── entrypoint.sh            # Container startup script
│   └── health_check.sh          # Health check script
├── Dockerfile                    # Docker image build file
├── requirements.txt              # Python dependencies
├── build.sh                     # Build and deployment script
├── .dockerignore                # Docker ignore file
└── README_UPDATED.md            # Project documentation
```

## Core Features

### 1. Task Management
- ✅ ConfigMap-based declarative task configuration
- ✅ Support for Quartz format cron expressions
- ✅ Task state control (on/off)
- ✅ Automatic generation of unique Pod names and labels

### 2. Pod Lifecycle Management
- ✅ Use ccictl tool to create Pods
- ✅ Automatically add management labels and annotations
- ✅ Support for custom Pod templates
- ✅ Configurable garbage collection policies

### 3. Health Monitoring
- ✅ crond service status monitoring
- ✅ HTTP health check endpoint
- ✅ Container health check configuration
- ✅ Detailed logging

### 4. Timezone Management
- ✅ Support for custom timezone configuration
- ✅ Default UTC timezone
- ✅ Environment variable configuration

## Quick Start

### 1. Build Image

```bash
# Basic build (local image)
./build.sh --build-only

# Build and push to image registry
./build.sh --registry your-registry.com/namespace --build-only

# Specify image tag
./build.sh --build-only --tag v1.1.0
```

### 2. Deploy to Kubernetes

```bash
# Deploy to default namespace
./build.sh --deploy-only

# Deploy to specified namespace
./build.sh --deploy-only --namespace cv-cd-generators

# Complete build and deployment process
./build.sh --registry your-registry.com/namespace --namespace cv-cd-generators
```

### 3. Configure Tasks

Create or update the `cron-dispatcher-config` ConfigMap:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cron-dispatcher-config
  namespace: your-namespace
data:
  tasks.yaml: |
    - name: example-task
      schedule: "0 */1 * * ? *"  # Execute every hour
      podTemplatePath: /etc/cron-templates/example-task-pod.yaml
      state: on
```

### 4. Configure Pod Templates

Provide Pod templates through the `cron-templates` ConfigMap:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cron-templates
  namespace: your-namespace
data:
  example-task-pod.yaml: |
    apiVersion: v1
    kind: Pod
    metadata:
      name: example-task  # Will be automatically replaced
    spec:
      restartPolicy: Never
      containers:
      - name: task-container
        image: busybox:latest
        command: ["echo", "Hello from CronDispatcher!"]
```

## Configuration Description

### Task Configuration (cron-dispatcher-config)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | ✅ | Unique task identifier |
| schedule | string | ✅ | Cron expression (supports Quartz format) |
| podTemplatePath | string | ✅ | Pod template file path |
| state | string | ❌ | Task state: on/off (default: on) |

### Garbage Collection Policy (cron-dispatcher-gc-policy)

```yaml
retentionPolicy:
  successPods:
    maxRetained: 3        # Number of successful Pods to retain
  failedPods:
    maxRetained: 3        # Number of failed Pods to retain
cleanupInterval: "60m"    # Cleanup interval
timeToLive: "1h"         # Pod maximum survival time
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| NAMESPACE | default | Kubernetes namespace |
| CRON_TIMEZONE | UTC | Timezone setting |
| PYTHONUNBUFFERED | 1 | Python output buffering |

## Monitoring and Operations

### Health Check

```bash
# Check Pod status
kubectl get pods -l app=cron-dispatcher -n your-namespace

# View logs
kubectl logs -l app=cron-dispatcher -n your-namespace -f

# Health check endpoint
kubectl port-forward svc/cron-dispatcher-service 8080:8080 -n your-namespace
curl http://localhost:8080/health
```

### View Cron Jobs

```bash
# Enter container to view crontab
kubectl exec -it deployment/cron-dispatcher -n your-namespace -- crontab -l

# View cron logs
kubectl exec -it deployment/cron-dispatcher -n your-namespace -- tail -f /var/log/cron
```

### View Created Pods

```bash
# View Pods created by CronDispatcher
kubectl get pods -l app.kubernetes.io/managed-by=CronDispatcher -n your-namespace

# View Pods for specific task
kubectl get pods -l cron-dispatcher.io/task-name=your-task-name -n your-namespace
```

## Troubleshooting

### Common Issues

1. **Pod Creation Failed**
   - Check if ccictl tool is correctly installed
   - Verify Pod template file path and format
   - Check RBAC permission configuration

2. **Cron Jobs Not Executing**
   - Verify cron expression format
   - Check if task state is "on"
   - Check crond service status

3. **Health Check Failed**
   - Check if crond service is running
   - Verify health check port accessibility
   - Check container logs

### Log Locations

- Main program logs: `/var/log/cron-dispatcher/dispatcher.log`
- Pod creation logs: `/var/log/cron-dispatcher/pod-creator.log`
- Cron system logs: `/var/log/cron`

## Security Considerations

### RBAC Permissions

CronDispatcher requires the following minimum permissions:

```yaml
rules:
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch", "create", "delete"]
```

### Container Security

- Container runs as root user (required by crond service)
- Add necessary Linux capabilities
- Use SecurityContext to limit permissions

## Extension and Customization

### Custom Timezone

```yaml
env:
- name: CRON_TIMEZONE
  value: "Africa/Johannesburg"  # Or other timezone
```

### Custom Resource Limits

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

### Add Monitoring

Can integrate Prometheus monitoring:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8080"
  prometheus.io/path: "/metrics"
```

## Version History

- **v1.0.0**: Initial version
  - Basic cron job management functionality
  - ConfigMap-driven configuration
  - Pod lifecycle management
  - Health check and monitoring

## Contributing Guidelines

1. Fork the project
2. Create a feature branch
3. Submit changes
4. Create a Pull Request

## License

This project is licensed under the MIT License.

## Support

For questions or suggestions, please create an Issue or contact the maintenance team. 