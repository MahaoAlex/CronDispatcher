# cron-dispatcher

## Overview

cron-dispatcher is a Kubernetes namespace-level cron job management platform that implements containerized orchestration and lifecycle management of scheduled tasks through a declarative configuration mode driven by ConfigMap. It provides a robust, scalable solution for managing scheduled workloads in CCI 2.0 environments.

## Key Features

- **ConfigMap-Driven Configuration**: Declarative task management through Kubernetes ConfigMaps
- **Dynamic Pod Creation**: Creates Pods from ConfigMap-stored definitions using ccictl
- **Hot Configuration Updates**: Automatic detection and application of configuration changes
- **Intelligent Garbage Collection**: Configurable cleanup policies for completed and failed Pods
- **CCI 2.0 Integration**: Native support for Huawei Cloud Container Instance service
- **Timezone Support**: Configurable timezone handling for global deployments
- **Health Monitoring**: Built-in health checks and comprehensive logging

## Architecture

### Core Components

1. **cron-dispatcher Main Service** (`main.py`)
   - Configuration management and hot updates
   - Crontab synchronization and task scheduling
   - CCI authentication and Pod lifecycle management

2. **Pod Creator** (`pod_creator.py`)
   - Dynamic Pod creation from ConfigMap definitions
   - UUID generation and labeling
   - Error handling and logging

3. **Pod Cleaner** (`pod_cleaner.py`)
   - Garbage collection based on configurable policies
   - Batch processing for efficient cleanup
   - Dry-run mode for testing

4. **CCI Authentication Manager** (`cci_auth_manager.py`)
   - Secure credential management
   - ccictl configuration and authentication
   - Connection testing and validation

5. **Process Manager** (`scripts/process_manager.sh`)
   - Container-friendly service management
   - Direct crond process management (no systemctl dependency)
   - Process monitoring and automatic restart
   - Graceful shutdown handling

### Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Namespace                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌──────────────────────────────────┐ │
│  │ cron-dispatcher  │    │         ConfigMaps               │ │
│  │   Deployment    │◄───┤ • cron-dispatcher-config         │ │
│  │                 │    │ • cron-dispatcher-gc-policy      │ │
│  │                 │    │ • pod-definition-templates       │ │
│  └─────────────────┘    └──────────────────────────────────┘ │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Scheduled Pod Instances                    │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │ │
│  │  │ Task-A  │ │ Task-B  │ │ Task-C  │ │   ...   │      │ │
│  │  │   Pod   │ │   Pod   │ │   Pod   │ │   Pod   │      │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘      │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Task Configuration (`cron-dispatcher-config`)

Define scheduled tasks through a ConfigMap containing task definitions:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cron-dispatcher-config
  namespace: your-namespace
data:
  tasks.yaml: |
    - name: data-processor
      schedule: "0 */6 * * *"  # Every 6 hours
      podDefinitionConfigmap: data-processor-template
      state: on
    - name: report-generator
      schedule: "30 2 * * *"   # Daily at 2:30 AM
      podDefinitionConfigmap: report-generator-template
      state: on
    - name: maintenance-task
      schedule: "0 0 * * 0"    # Weekly on Sunday
      podDefinitionConfigmap: maintenance-task-template
      state: off
```

#### Task Configuration Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique task identifier |
| `schedule` | string | Yes | Cron expression (Unix format) |
| `podDefinitionConfigmap` | string | Yes | ConfigMap containing Pod definition |
| `state` | string | No | Task state: `on` (default) or `off` |

### Pod Definition ConfigMaps

Store Pod definitions in separate ConfigMaps for reusability:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: data-processor-template
  namespace: your-namespace
data:
  pod.yaml: |
    apiVersion: v1
    kind: Pod
    spec:
      containers:
      - name: processor
        image: your-registry/data-processor:latest
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "1000m"
            memory: "2Gi"
      restartPolicy: Never
```

### Garbage Collection Policy (`cron-dispatcher-gc-policy`)

Configure cleanup behavior for completed and failed Pods:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cron-dispatcher-gc-policy
  namespace: your-namespace
data:
  gc-policy.yaml: |
    global:
      success: 3  # Keep 3 successful Pods
      failure: 3  # Keep 3 failed Pods
    tasks:
      - taskSelector:
          cron-dispatcher.io/task-name: "critical-task"
        success: 10  # Keep more for critical tasks
        failure: 5
    labelSelector:
      matchLabels:
        app.kubernetes.io/managed-by: cron-dispatcher
    cleanupInterval: "60m"  # Run cleanup every hour
```

#### Cleanup Interval Configuration

| Format | Description | Seconds |
|--------|-------------|---------|
| `30s` | 30 seconds | 30 |
| `5m` | 5 minutes | 300 |
| `1h` | 1 hour | 3600 |
| `1d` | 1 day | 86400 |
| `120` | Raw seconds | 120 |

**Limits**: 30 seconds minimum, 24 hours maximum

## Deployment

### Prerequisites

1. **CCI 2.0 Environment**: Huawei Cloud Container Instance service
2. **Credentials**: CCI access credentials (AK/SK, domain, project)
3. **Namespace**: Kubernetes namespace with appropriate permissions
4. **ConfigMaps**: Task and policy configurations

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NAMESPACE` | No | `default` | Kubernetes namespace |
| `CRON_TIMEZONE` | No | `UTC` | Timezone for cron execution |
| `CCI_REGION` | No | `af-south-1` | CCI region |
| `GC_DRY_RUN` | No | `false` | Enable garbage collection dry run |
| `GC_BATCH_SIZE` | No | `50` | Pods to delete per batch |
| `CCI_ACCESS_KEY` | Yes | - | CCI access key |
| `CCI_SECRET_KEY` | Yes | - | CCI secret key |
| `CCI_DOMAIN_NAME` | Yes | - | CCI domain name |
| `CCI_PROJECT_NAME` | No | region | CCI project name |

### Deployment Steps

1. **Create Credentials Secret**:
```bash
ccictl create secret generic cci-credentials \
  --from-literal=access-key=YOUR_ACCESS_KEY \
  --from-literal=secret-key=YOUR_SECRET_KEY \
  --from-literal=domain-name=YOUR_DOMAIN \
  --from-literal=project-name=YOUR_PROJECT
```

2. **Deploy Configuration**:
```bash
ccictl apply -f config/cron-dispatcher-config.yaml
ccictl apply -f config/cron-dispatcher-gc-policy.yaml
```

3. **Deploy cron-dispatcher**:
```bash
ccictl apply -f config/deployment.yaml
```

### Health Checks

cron-dispatcher includes comprehensive health monitoring with container-friendly architecture:

- **Liveness Probe**: Monitors crond service and main process (no systemctl dependency)
- **Readiness Probe**: Validates configuration and dependencies
- **Process Management**: Built-in process monitoring and automatic restart
- **Manual Health Check**: `health_check.sh --verbose`

**Container-Friendly Features**:
- Direct process management without systemd
- PID-based process monitoring
- Automatic service recovery
- Graceful shutdown handling

## Pod Labeling

All Pods created by cron-dispatcher include standardized labels:

```yaml
metadata:
  name: "task-name-abc123def"
  labels:
    app.kubernetes.io/name: "task-name"
    app.kubernetes.io/managed-by: "cron-dispatcher"
    cron-dispatcher.io/task-name: "task-name"
    cron-dispatcher.io/instance: "task-name-abc123def"
  annotations:
    cron-dispatcher.io/created-by: "cron-dispatcher"
    cron-dispatcher.io/creation-time: "2024-12-01T12:00:00Z"
    cron-dispatcher.io/source-configmap: "task-template-name"
```

## Hot Configuration Updates

cron-dispatcher automatically detects and applies configuration changes:

- **Detection Frequency**: Every 30 seconds
- **Supported Changes**: Task addition, removal, modification, and GC policy updates
- **Update Process**: Automatic crontab rebuild and policy refresh
- **Zero Downtime**: No container restart required

## Cron Expression Format

Supports standard Unix cron format with Quartz compatibility:

| Field | Values | Special Characters |
|-------|--------|--------------------|
| Minute | 0-59 | `* , - /` |
| Hour | 0-23 | `* , - /` |
| Day | 1-31 | `* , - / ?` |
| Month | 1-12 | `* , - /` |
| Weekday | 0-7 | `* , - / ?` |

### Examples

```bash
"0 */6 * * *"     # Every 6 hours
"30 2 * * *"      # Daily at 2:30 AM
"0 0 * * 0"       # Weekly on Sunday
"*/15 * * * *"    # Every 15 minutes
"0 9-17 * * 1-5"  # Hourly during business hours
```

## Logging

Comprehensive logging across all components:

- **Main Application**: `/var/log/cron-dispatcher/dispatcher.log`
- **Pod Creator**: `/var/log/cron-dispatcher/pod-creator.log`
- **System Cron**: Standard syslog integration
- **Health Checks**: Structured health status reporting

### Log Levels

- **INFO**: Normal operations and status updates
- **WARN**: Non-critical issues and fallbacks
- **ERROR**: Critical errors requiring attention
- **DEBUG**: Detailed troubleshooting information

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Verify CCI credentials in secret
   - Check region configuration
   - Validate ccictl connectivity

2. **Pod Creation Failures**
   - Verify ConfigMap exists and contains valid Pod definition
   - Check namespace permissions
   - Review resource quotas

3. **Configuration Not Loading**
   - Verify ConfigMap mounting
   - Check YAML syntax
   - Review file permissions

### Debugging Commands

```bash
# Check cron-dispatcher status
ccictl logs deployment/cron-dispatcher

# Verify configuration
ccictl get configmap cron-dispatcher-config -o yaml

# Test health manually
ccictl exec deployment/cron-dispatcher -- /usr/local/bin/health_check.sh --verbose

# Check crontab status
ccictl exec deployment/cron-dispatcher -- crontab -l
```

## Dependency of ccictl

When creating pods within `CronDispatch` running on `CCI2.0` using `ccictl`, there are two available methods:

- Through Internet

- Through VPC network
  Note: Since the 100.64 network route is no longer permitted, accessing the CCI management API and IAM management API via this method requires using VPCEP (VPC Endpoint).

  Implementation Steps:

  * Create a VPC Endpoint to connect to the Endpoint Service of APIGateway Manage Plane.

  * Add CNAME DNS records for CCI and IAM to the internal domain of the above endpoint.
    (e.g. APIGateway VPC Endpint Inner Domain: vpcep-99bb88e4-5459-42c2-8b37-2c4a3dcf2087.af-south-1.huaweicloud.com)
    CNAME: iam.af-south-1.myhuaweicloud.com -> vpcep-99bb88e4-5459-42c2-8b37-2c4a3dcf2087.af-south-1.huaweicloud.com
    CNAME: cci.af-south-1.myhuaweicloud.com -> vpcep-99bb88e4-5459-42c2-8b37-2c4a3dcf2087.af-south-1.huaweicloud.com

  ** Important Note: **
  When creating Private Zone `af-south-1.myhuaweicloud.com` in DNS Service, please make sure to enable the feature `Recursive resolution proxy for subdomains `.

## Performance Considerations

- **Resource Limits**: Configure appropriate CPU and memory limits
- **Batch Processing**: Adjust `GC_BATCH_SIZE` for large-scale deployments
- **Cleanup Frequency**: Balance `cleanupInterval` with resource usage
- **Concurrent Pods**: Monitor namespace quotas and resource consumption

## Security

- **Least Privilege**: Use minimal CCI permissions for Pod operations
- **Secret Management**: Store credentials securely in Kubernetes secrets
- **Network Policies**: Implement appropriate network restrictions
- **Image Security**: Use trusted base images and regular updates

## Version Information

- **Current Version**: 1.0.0
- **Kubernetes Compatibility**: 1.20+
- **CCI Version**: 2.0
- **Python Version**: 3.8+

## Dependencies

### Python Dependencies

- **PyYAML==6.0.1**: YAML configuration parsing
- **python-crontab==2.7.1**: Cron expression parsing and validation
- **python-dateutil==2.8.2**: Date and time utilities
- **requests==2.31.0**: HTTP client for API calls
