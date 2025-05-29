# CronDispatcher Test Cases Documentation

This document contains comprehensive test cases for validating CronDispatcher functionality in the Johannesburg deployment environment.

## Test Environment Configuration

- **Timezone**: Africa/Johannesburg (SAST - UTC+2)
- **Kubernetes Namespace**: To be specified during deployment
- **Image Registry**: To be configured based on deployment environment

## Test Case Categories

### 1. Basic Functionality Tests

| Test ID | Test Item | Test Steps | Expected Output | Test Result |
|---------|-----------|------------|-----------------|-------------|
| TC-001 | Docker Image Build | Run `./build.sh --build-only` | Image builds successfully without errors | |
| TC-002 | Container Startup | Deploy to K8s and check pod status | Pod reaches Running state within 60 seconds | |
| TC-003 | Health Check Endpoint | Access `/health` endpoint | Returns HTTP 200 with `{"status": "healthy", "crond": "active"}` | |
| TC-004 | Timezone Configuration | Check container logs for timezone setting | Logs show "Timezone: Africa/Johannesburg" | |
| TC-005 | crond Service Status | Execute health check script in container | Shows "[PASS] crond service is running" | |

### 2. Configuration Management Tests

| Test ID | Test Item | Test Steps | Expected Output | Test Result |
|---------|-----------|------------|-----------------|-------------|
| TC-006 | ConfigMap Loading | Create cron-dispatcher-config ConfigMap | Logs show "Successfully loaded X task configurations" | |
| TC-007 | Invalid ConfigMap | Deploy with malformed YAML in ConfigMap | Logs show warning about parsing failure, continues running | |
| TC-008 | Missing ConfigMap | Deploy without ConfigMap | Logs show "ConfigMap cron-dispatcher-config does not exist" | |
| TC-009 | Task State Toggle | Set task state to "off" in ConfigMap | Task is skipped, logs show "Skipping disabled task: [name]" | |
| TC-010 | Configuration Reload | Update ConfigMap and wait 5 minutes | New configuration is loaded automatically | |

### 3. Cron Expression Tests

| Test ID | Test Item | Test Steps | Expected Output | Test Result |
|---------|-----------|------------|-----------------|-------------|
| TC-011 | Quartz Format Conversion | Use "0 30 14 * * ? *" (2:30 PM daily) | Converts to "30 14 * * *" in crontab | |
| TC-012 | Standard Cron Format | Use "0 */2 * * *" (every 2 hours) | Accepts format without conversion | |
| TC-013 | Invalid Cron Expression | Use "70 * * * *" (invalid minutes) | Logs error and skips task | |
| TC-014 | Timezone-aware Scheduling | Schedule task for 09:00 SAST | Task executes at 07:00 UTC (09:00 SAST) | |
| TC-015 | Multiple Task Scheduling | Configure 3 tasks with different schedules | All tasks appear in crontab with correct timing | |

### 4. Pod Creation Tests

| Test ID | Test Item | Test Steps | Expected Output | Test Result |
|---------|-----------|------------|-----------------|-------------|
| TC-016 | Pod Template Processing | Trigger task execution | Pod created with correct name format: `[task-name]-[9-digit-uuid]` | |
| TC-017 | Pod Labels Validation | Check created pod labels | Contains required labels: `app.kubernetes.io/managed-by: CronDispatcher` | |
| TC-018 | Pod Namespace | Create pod in specific namespace | Pod created in correct namespace | |
| TC-019 | Missing Template File | Configure task with non-existent template | Logs error "Pod template file does not exist" | |
| TC-020 | Template File Permissions | Set incorrect permissions on template | Logs appropriate error message | |

### 5. Garbage Collection Tests

| Test ID | Test Item | Test Steps | Expected Output | Test Result |
|---------|-----------|------------|-----------------|-------------|
| TC-021 | Default Retention Policy | Create 5 successful pods for same task | Only 3 most recent pods retained | |
| TC-022 | Task-specific Policy | Configure custom retention for specific task | Custom retention applied correctly | |
| TC-023 | Dry Run Mode | Set `GC_DRY_RUN=true` | Logs show "[DRY RUN] Would delete Pod..." without actual deletion | |
| TC-024 | Batch Processing | Set `GC_BATCH_SIZE=2` with 10 pods to delete | Pods deleted in batches of 2 with delays | |
| TC-025 | Failed Pod Cleanup | Create failed pods exceeding retention | Failed pods cleaned up according to policy | |

### 6. Environment Variable Tests

| Test ID | Test Item | Test Steps | Expected Output | Test Result |
|---------|-----------|------------|-----------------|-------------|
| TC-026 | NAMESPACE Variable | Deploy in custom namespace | Logs show correct namespace detection | |
| TC-027 | CRON_TIMEZONE Variable | Set to different timezone | Timezone applied correctly in container | |
| TC-028 | GC_DRY_RUN Variable | Set to "true" | Garbage collection runs in dry-run mode | |
| TC-029 | GC_BATCH_SIZE Variable | Set to custom value | Batch size applied in garbage collection | |
| TC-030 | PYTHONUNBUFFERED Variable | Set to "1" | Python output appears immediately in logs | |

### 7. Error Handling Tests

| Test ID | Test Item | Test Steps | Expected Output | Test Result |
|---------|-----------|------------|-----------------|-------------|
| TC-031 | Kubernetes API Failure | Simulate API server unavailability | Application logs error and retries after 60 seconds | |
| TC-032 | ccictl Command Failure | Configure invalid ccictl parameters | Logs error "Failed to create Pod" with details | |
| TC-033 | Disk Space Full | Fill up /tmp directory | Handles temporary file creation errors gracefully | |
| TC-034 | Memory Pressure | Simulate high memory usage | Pod respects resource limits and handles OOM gracefully | |
| TC-035 | Network Connectivity | Simulate network issues | Retries operations and logs appropriate errors | |

### 8. Performance Tests

| Test ID | Test Item | Test Steps | Expected Output | Test Result |
|---------|-----------|------------|-----------------|-------------|
| TC-036 | High Task Volume | Configure 50 concurrent tasks | All tasks scheduled without performance degradation | |
| TC-037 | Large ConfigMap | Create ConfigMap with 100+ tasks | Configuration loads within acceptable time (< 30s) | |
| TC-038 | Garbage Collection Performance | Test with 1000+ pods to clean | Cleanup completes within reasonable time (< 5 minutes) | |
| TC-039 | Memory Usage | Monitor memory consumption over 24 hours | Memory usage remains stable, no memory leaks | |
| TC-040 | CPU Usage | Monitor CPU usage during peak operations | CPU usage stays within configured limits | |

### 9. Security Tests

| Test ID | Test Item | Test Steps | Expected Output | Test Result |
|---------|-----------|------------|-----------------|-------------|
| TC-041 | RBAC Permissions | Check pod permissions | Only has required permissions for ConfigMaps and Pods | |
| TC-042 | Service Account | Verify service account usage | Uses dedicated service account, not default | |
| TC-043 | Container Security | Check container security context | Runs as root only when necessary for crond | |
| TC-044 | Secret Handling | Test with sensitive data in templates | No secrets exposed in logs | |
| TC-045 | Network Policies | Test with network restrictions | Respects network policies if configured | |

### 10. Integration Tests

| Test ID | Test Item | Test Steps | Expected Output | Test Result |
|---------|-----------|------------|-----------------|-------------|
| TC-046 | End-to-End Workflow | Deploy complete system and run sample task | Task executes successfully and pod is cleaned up | |
| TC-047 | Multi-namespace Deployment | Deploy in multiple namespaces | Each instance operates independently | |
| TC-048 | Monitoring Integration | Configure monitoring tools | Metrics and logs are properly exported | |
| TC-049 | Backup and Recovery | Simulate pod restart | Configuration reloads and operations resume | |
| TC-050 | Upgrade Testing | Upgrade to new version | Upgrade completes without data loss | |

## Test Execution Guidelines

### Pre-requisites
1. Kubernetes cluster with appropriate permissions
2. Docker registry access
3. kubectl configured for target cluster
4. Sufficient resources allocated (CPU: 500m, Memory: 512Mi minimum)

### Test Environment Setup
```bash
# Set environment variables
export NAMESPACE="cron-dispatcher-test"
export REGISTRY_URL="your-registry.com/namespace"

# Build and deploy
./build.sh --registry $REGISTRY_URL --namespace $NAMESPACE
```

### Test Data Preparation
1. Create test ConfigMaps with various task configurations
2. Prepare Pod templates for different scenarios
3. Set up monitoring and logging collection

### Test Execution Order
1. Execute Basic Functionality Tests (TC-001 to TC-005) first
2. Run Configuration Management Tests (TC-006 to TC-010)
3. Proceed with feature-specific tests
4. Perform Error Handling and Performance tests
5. Complete with Security and Integration tests

### Test Result Recording
- **PASS**: Test completed successfully with expected results
- **FAIL**: Test failed with unexpected results (record failure details)
- **SKIP**: Test skipped due to environment limitations
- **BLOCKED**: Test cannot be executed due to dependencies

### Failure Investigation
For failed tests, record:
1. Error messages from logs
2. Pod status and events
3. ConfigMap contents
4. Environment configuration
5. Steps to reproduce

## Test Reporting

After completing all tests, generate a summary report including:
- Total tests executed
- Pass/Fail/Skip/Blocked counts
- Critical issues identified
- Performance metrics
- Recommendations for production deployment

## Johannesburg-Specific Considerations

1. **Timezone Testing**: Verify all scheduled tasks execute at correct local time (SAST)
2. **Daylight Saving**: Test behavior during DST transitions (if applicable)
3. **Local Compliance**: Ensure logging and monitoring meet local requirements
4. **Network Latency**: Account for potential latency to external services
5. **Business Hours**: Schedule maintenance tasks outside business hours (08:00-17:00 SAST) 