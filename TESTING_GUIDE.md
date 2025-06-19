# cron-dispatcher Testing Guide

## Overview

This document provides a comprehensive testing guide for the cron-dispatcher project, covering all test types from unit tests to end-to-end scenarios. It includes detailed test cases, execution instructions, and test environment setup.

## Test Cases Summary

### Unit Test Script Mappings

| Test Script | Modules Tested | Functionality |
|-------------|----------------|---------------|
| `tests/test_logger_config.py` | `src/logger_config.py` | Validates logging setup and file handling. |
| `tests/test_utils.py` | `src/utils.py` | Verifies core utilities like command execution and YAML parsing. |
| `tests/test_cci_auth_manager.py`| `src/cci_auth_manager.py` | Tests CCI credential loading and `ccictl` configuration. |
| `tests/test_pod_creator.py` | `src/pod_creator.py` | Covers Pod creation logic from ConfigMap definitions. |
| `tests/test_pod_cleaner.py` | `src/pod_cleaner.py` | Checks garbage collection logic for completed/expired Pods. |
| `tests/test_main.py` | `src/main.py` | End-to-end tests for the main dispatcher, covering task processing, scheduling, and configuration reloading. |

**Execution Commands**: `python tests/test_runner.py` (all) | `python -m unittest tests.test_category -v` (single category)

### Test Case Statistics

| Test Type | Case Count | Status | Description |
|-----------|------------|--------|-------------|
| **Unit Tests** | **~90+** | **Implemented** | Covers all core modules, error handling, and edge cases. |
| Integration Tests | 29 | Pending | CCI authentication, Pod management, scheduled tasks, hot updates |
| End-to-End Tests | 7 | Pending | Complete workflows, error recovery |
| Performance Tests | 6 | Pending | Scalability, concurrent operations |
| Security Tests | 4 | Pending | Credential security, permission isolation |

**Total: ~136 test cases** | **Priority**: High priority for all implemented unit tests.

## Test Environment Setup

### Prerequisites

1. **CCI 2.0 Environment**: Access to Huawei Cloud Container Instance
2. **Test Namespace**: Dedicated namespace for testing (e.g., `cron-dispatcher-test`)
3. **Test Credentials**: Valid CCI credentials with minimal required permissions
4. **Test ConfigMaps**: Sample task and policy configurations

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

### Test Data Preparation

```bash
# Create test namespace
ccictl create namespace cron-dispatcher-test

# Create test credentials secret
ccictl create secret generic cci-credentials \
  --namespace=cron-dispatcher-test \
  --from-literal=access-key=TEST_ACCESS_KEY \
  --from-literal=secret-key=TEST_SECRET_KEY \
  --from-literal=domain-name=TEST_DOMAIN \
  --from-literal=project-name=TEST_PROJECT
```

## Unit Tests

The unit test suite is designed to run in isolation without external dependencies like a Kubernetes cluster. It extensively uses mocking to simulate interactions with the file system, `ccictl` commands, and the Kubernetes API.

The suite covers the following key areas:
- **Configuration Loading**: Valid, invalid, empty, and missing configuration files.
- **Cron Expression Validation**: Standard Unix and Quartz cron expressions, including invalid and edge-case formats.
- **ConfigMap Validation**: Existence and accessibility checks for ConfigMaps.
- **Garbage Collection Policy**: Default and custom GC policies, including parsing various time interval formats.
- **Task Processing**: Valid task definitions, disabled tasks, and tasks with missing or invalid fields.
- **CCI Authentication**: Initialization with and without credentials, and handling of initialization failures.
- **Main Dispatcher Loop**: Correct startup, shutdown, and dynamic reloading of configurations upon change.

For a detailed breakdown of test files, individual test cases, and execution commands, please refer to the [**Unit Tests Documentation**](./UNIT_TESTS.md).

## Integration Tests

### 5. CCI Authentication Tests

#### Test Case 5.1: Successful Authentication
**Objective**: Verify successful CCI authentication setup
**Input**: Valid CCI credentials
**Expected Result**: Authentication configured successfully
**Test Steps**:
1. Set valid environment variables
2. Call `load_credentials_from_env()`
3. Verify `True` is returned
4. Call `configure_ccictl()` with valid region
5. Verify ccictl is configured correctly

#### Test Case 5.2: Missing Credentials
**Objective**: Verify handling of missing credentials
**Input**: Missing required environment variables
**Expected Result**: Authentication fails gracefully
**Test Steps**:
1. Unset required environment variables
2. Call `load_credentials_from_env()`
3. Verify `False` is returned
4. Verify error is logged

#### Test Case 5.3: Invalid Credentials
**Objective**: Verify handling of invalid credentials
**Input**: Invalid CCI credentials
**Expected Result**: Authentication fails, error logged
**Test Steps**:
1. Set invalid credentials
2. Call `load_credentials_from_env()`
3. Verify `True` is returned (loading succeeds)
4. Call `configure_ccictl()`
5. Verify ccictl configuration fails gracefully

#### Test Case 5.4: Regional Configuration
**Objective**: Verify correct regional endpoint configuration
**Input**: Different CCI regions
**Expected Result**: Correct regional endpoints configured
**Test Steps**:
1. Test various regions (af-south-1, cn-north-4, etc.)
2. Verify correct IAM and CCI endpoints are configured
3. Verify project name defaults to region when not specified

### 6. Pod Creation Tests

#### Test Case 6.1: Successful Pod Creation
**Objective**: Verify successful Pod creation from ConfigMap
**Input**: Valid task name and ConfigMap with Pod definition
**Expected Result**: Pod created successfully with correct labels
**Test Steps**:
1. Create ConfigMap with valid Pod definition
2. Call `create_pod()` with task name and ConfigMap name
3. Verify Pod is created in namespace
4. Verify Pod has correct labels and annotations
5. Verify Pod name follows pattern `task-name-<uuid>`
6. Verify UUID is 9 characters long

#### Test Case 6.2: Pod Creation with Missing ConfigMap
**Objective**: Verify handling of missing Pod definition ConfigMap
**Input**: Non-existent ConfigMap name
**Expected Result**: Pod creation fails, error logged
**Test Steps**:
1. Call `create_pod()` with non-existent ConfigMap
2. Verify `False` is returned
3. Verify error is logged
4. Verify no Pod is created

#### Test Case 6.3: Pod Creation with Invalid Definition
**Objective**: Verify handling of invalid Pod definition
**Input**: ConfigMap with invalid Pod YAML
**Expected Result**: Pod creation fails, error logged
**Test Steps**:
1. Create ConfigMap with invalid Pod definition
2. Call `create_pod()` with ConfigMap name
3. Verify `False` is returned
4. Verify error is logged

#### Test Case 6.4: Pod Label and Annotation Verification
**Objective**: Verify correct Pod metadata is applied
**Input**: Valid Pod creation request
**Expected Result**: Pod has all required labels and annotations
**Test Steps**:
1. Create Pod successfully
2. Verify essential labels:
   - `app.kubernetes.io/name`
   - `app.kubernetes.io/managed-by`
   - `cron-dispatcher.io/task-name`
   - `cron-dispatcher.io/instance`
3. Verify essential annotations:
   - `cron-dispatcher.io/created-by`
   - `cron-dispatcher.io/creation-time`
   - `cron-dispatcher.io/source-configmap`

#### Test Case 6.5: Pod Resource Constraints
**Objective**: Verify Pod resource requests and limits are preserved
**Input**: Pod definition with resource constraints
**Expected Result**: Pod created with correct resource specifications
**Test Steps**:
1. Create ConfigMap with resource-constrained Pod definition
2. Create Pod from ConfigMap
3. Verify Pod has correct resource requests and limits
4. Verify no resource constraints are modified

#### Test Case 6.6: UUID Generation
**Objective**: Verify UUID generation for Pod names
**Input**: Multiple Pod creation requests
**Expected Result**: Each Pod has unique 9-character UUID
**Test Steps**:
1. Create multiple Pods with same task name
2. Verify each Pod has unique UUID
3. Verify UUID is exactly 9 characters
4. Verify UUID contains only alphanumeric characters

### 7. Pod Cleaning Tests

#### Test Case 7.1: Successful Pod Cleanup
**Objective**: Verify successful cleanup of excess Pods
**Input**: Multiple Pods exceeding retention limits
**Expected Result**: Excess Pods deleted according to policy
**Test Steps**:
1. Create multiple completed Pods for same task
2. Configure retention policy (e.g., success: 2, failure: 2)
3. Call `cleanup_pods()` with policy
4. Verify excess Pods are deleted
5. Verify correct number of Pods retained

#### Test Case 7.2: Pod Grouping by Task
**Objective**: Verify correct grouping of Pods by task name
**Input**: Pods from multiple tasks with different statuses
**Expected Result**: Pods correctly grouped by task and status
**Test Steps**:
1. Create Pods for multiple tasks
2. Call `_group_pods_by_task()` with Pod list
3. Verify Pods are grouped by task name
4. Verify Pods are sub-grouped by status (success/failed)

#### Test Case 7.3: Batch Deletion
**Objective**: Verify batch deletion functionality
**Input**: Large number of Pods to delete
**Expected Result**: Pods deleted in batches with proper delays
**Test Steps**:
1. Create large number of Pods (>100)
2. Set small batch size (e.g., 10)
3. Call cleanup with large Pod list
4. Verify Pods are deleted in batches
5. Verify delays between batches

#### Test Case 7.4: Dry Run Mode
**Objective**: Verify dry run mode doesn't actually delete Pods
**Input**: Cleanup request with dry_run=True
**Expected Result**: No Pods deleted, actions logged
**Test Steps**:
1. Enable dry run mode
2. Call cleanup with excess Pods
3. Verify no Pods are actually deleted
4. Verify dry run actions are logged
5. Verify correct count is returned

#### Test Case 7.5: Task-Specific Retention Policies
**Objective**: Verify task-specific retention policies are applied
**Input**: GC policy with task-specific rules
**Expected Result**: Different retention applied per task
**Test Steps**:
1. Create GC policy with task-specific retention
2. Create Pods for different tasks
3. Run cleanup
4. Verify each task follows its specific retention policy

### 8. Crontab Management Tests

#### Test Case 8.1: Crontab Update with Valid Tasks
**Objective**: Verify successful crontab update with valid tasks
**Input**: List of valid task configurations
**Expected Result**: Crontab updated with correct entries
**Test Steps**:
1. Prepare list of valid tasks
2. Call `update_crontab()` with task list
3. Verify crontab contains correct entries
4. Verify each entry has correct schedule and command
5. Verify timezone is correctly applied

#### Test Case 8.2: Crontab Update with Mixed Valid/Invalid Tasks
**Objective**: Verify handling of mixed valid and invalid tasks
**Input**: List containing both valid and invalid tasks
**Expected Result**: Only valid tasks added to crontab
**Test Steps**:
1. Prepare mixed task list
2. Call `update_crontab()` with task list
3. Verify only valid tasks are in crontab
4. Verify warnings logged for invalid tasks

#### Test Case 8.3: Crontab Update with Disabled Tasks
**Objective**: Verify handling of disabled tasks
**Input**: Tasks with `state: off`
**Expected Result**: Disabled tasks not added to crontab
**Test Steps**:
1. Prepare tasks with `state: off`
2. Call `update_crontab()` with task list
3. Verify disabled tasks are not in crontab
4. Verify info messages logged for skipped tasks

#### Test Case 8.4: Crontab Cleanup
**Objective**: Verify old crontab entries are removed
**Input**: Updated task list with removed tasks
**Expected Result**: Old entries removed from crontab
**Test Steps**:
1. Add initial tasks to crontab
2. Update with new task list (removing some tasks)
3. Verify removed tasks are no longer in crontab
4. Verify new/updated tasks are present

#### Test Case 8.5: Quartz to Unix Cron Conversion
**Objective**: Verify correct conversion of Quartz format to Unix format
**Input**: Tasks with Quartz format cron expressions
**Expected Result**: Correct Unix format used in crontab
**Test Steps**:
1. Create tasks with Quartz format expressions
2. Update crontab
3. Verify crontab contains Unix format expressions
4. Verify conversion is correct

### 9. Hot Configuration Update Tests

#### Test Case 9.1: Task Configuration Hot Update
**Objective**: Verify detection and application of task configuration changes
**Input**: Modified task configuration ConfigMap
**Expected Result**: Changes detected and applied automatically
**Test Steps**:
1. Deploy initial configuration
2. Wait for initial load
3. Modify task configuration ConfigMap (simulate file modification time change)
4. Call `watch_tasks_config_change()`
5. Verify changes are detected
6. Verify crontab is updated accordingly

#### Test Case 9.2: GC Policy Hot Update
**Objective**: Verify detection and application of GC policy changes
**Input**: Modified GC policy ConfigMap
**Expected Result**: Policy changes detected and applied
**Test Steps**:
1. Deploy initial GC policy
2. Wait for initial load
3. Modify GC policy ConfigMap (simulate file modification time change)
4. Call `watch_gc_policy_change()`
5. Verify changes are detected
6. Verify new policy is applied

#### Test Case 9.3: File Modification Time Tracking
**Objective**: Verify correct tracking of file modification times
**Input**: File modification operations
**Expected Result**: Modification times correctly tracked and compared
**Test Steps**:
1. Initialize with baseline files
2. Verify initial modification times are recorded
3. Modify files
4. Verify new modification times are detected
5. Verify no false positives on unchanged files

#### Test Case 9.4: Configuration Reload Error Handling
**Objective**: Verify graceful handling of configuration reload errors
**Input**: Invalid configuration updates
**Expected Result**: Errors logged, previous configuration retained
**Test Steps**:
1. Deploy valid initial configuration
2. Update with invalid configuration
3. Verify error is logged
4. Verify previous valid configuration is retained
5. Verify system continues operating

## End-to-End Tests

### 10. Complete Workflow Tests

#### Test Case 10.1: Full Deployment and Execution
**Objective**: Verify complete cron-dispatcher workflow
**Input**: Complete deployment configuration
**Expected Result**: Tasks scheduled and executed successfully
**Test Steps**:
1. Deploy cron-dispatcher with test configuration
2. Verify deployment is healthy
3. Verify CCI authentication is successful
4. Verify tasks are scheduled in crontab
5. Wait for task execution time
6. Verify Pods are created and executed
7. Verify Pod labels and annotations

#### Test Case 10.2: Multi-Task Execution
**Objective**: Verify multiple tasks can run simultaneously
**Input**: Multiple tasks with overlapping schedules
**Expected Result**: All tasks execute without interference
**Test Steps**:
1. Configure multiple tasks with short intervals
2. Deploy configuration
3. Monitor task execution
4. Verify all tasks create Pods independently
5. Verify no resource conflicts

#### Test Case 10.3: Long-Running Operation
**Objective**: Verify system stability over extended periods
**Input**: Long-running deployment with frequent tasks
**Expected Result**: System remains stable and responsive
**Test Steps**:
1. Deploy with frequent task execution (every minute)
2. Monitor for extended period (1+ hours)
3. Verify consistent task execution
4. Verify no memory leaks or resource accumulation
5. Verify log rotation and cleanup

### 11. Error Recovery and Resilience Tests

#### Test Case 11.1: CCI API Failure Recovery
**Objective**: Verify recovery from CCI API failures
**Input**: Simulated CCI API unavailability
**Expected Result**: System recovers when API becomes available
**Test Steps**:
1. Deploy functioning system
2. Simulate CCI API failure
3. Verify errors are logged appropriately
4. Restore CCI API availability
5. Verify system resumes normal operation

#### Test Case 11.2: ConfigMap Corruption Recovery
**Objective**: Verify handling of corrupted ConfigMaps
**Input**: Corrupted configuration data
**Expected Result**: Previous valid configuration retained
**Test Steps**:
1. Deploy with valid configuration
2. Corrupt ConfigMap data
3. Verify corruption is detected
4. Verify error is logged
5. Verify system continues with previous configuration

#### Test Case 11.3: Pod Creation Failure Recovery
**Objective**: Verify handling of Pod creation failures
**Input**: Conditions causing Pod creation to fail
**Expected Result**: Failures logged, retries attempted
**Test Steps**:
1. Create condition causing Pod creation failure
2. Trigger task execution
3. Verify failure is logged
4. Verify retry mechanism works (via cron retry)
5. Verify system continues operating

#### Test Case 11.4: Network Connectivity Issues
**Objective**: Verify handling of network connectivity problems
**Input**: Intermittent network connectivity
**Expected Result**: Operations retry and succeed when connectivity restored
**Test Steps**:
1. Deploy functioning system
2. Introduce network connectivity issues
3. Verify retry mechanisms activate
4. Restore connectivity
5. Verify operations complete successfully

## Performance and Load Tests

### 12. Scalability Tests

#### Test Case 12.1: High Task Volume
**Objective**: Verify performance with large number of tasks
**Input**: 100+ task configurations
**Expected Result**: All tasks processed within acceptable time
**Test Steps**:
1. Create configuration with 100+ tasks
2. Deploy cron-dispatcher
3. Measure configuration load time
4. Verify all tasks are scheduled
5. Monitor resource usage
6. Verify performance remains acceptable

#### Test Case 12.2: Rapid Configuration Changes
**Objective**: Verify handling of frequent configuration updates
**Input**: Rapid successive configuration changes
**Expected Result**: All changes processed correctly
**Test Steps**:
1. Implement automated rapid configuration changes
2. Monitor system response time
3. Verify all changes are applied
4. Check for race conditions or errors
5. Verify system stability

#### Test Case 12.3: Large-Scale Garbage Collection
**Objective**: Verify GC performance with many Pods
**Input**: 1000+ Pods requiring cleanup
**Expected Result**: Cleanup completes within reasonable time
**Test Steps**:
1. Create large number of test Pods
2. Configure aggressive GC policy
3. Trigger garbage collection
4. Measure cleanup time
5. Verify batch processing works correctly
6. Monitor resource usage during cleanup

#### Test Case 12.4: Memory and Resource Usage
**Objective**: Verify acceptable resource consumption
**Input**: Normal operation over extended period
**Expected Result**: Stable resource usage, no leaks
**Test Steps**:
1. Deploy with moderate task load
2. Monitor memory usage over time
3. Monitor CPU usage patterns
4. Verify no memory leaks
5. Verify garbage collection effectiveness

### 13. Concurrent Operations Tests

#### Test Case 13.1: Concurrent Task Execution
**Objective**: Verify multiple tasks can execute simultaneously
**Input**: Multiple tasks scheduled to run at same time
**Expected Result**: All tasks execute successfully
**Test Steps**:
1. Configure multiple tasks with identical schedules
2. Monitor execution at scheduled time
3. Verify all Pods are created
4. Verify no resource conflicts
5. Verify proper isolation between tasks

#### Test Case 13.2: Concurrent Cleanup Operations
**Objective**: Verify concurrent cleanup doesn't cause issues
**Input**: Multiple cleanup operations triggered simultaneously
**Expected Result**: All cleanups complete successfully
**Test Steps**:
1. Create conditions for multiple cleanup triggers
2. Trigger cleanups simultaneously
3. Verify all cleanups complete
4. Verify no duplicate deletions
5. Verify proper synchronization

## Security and Compliance Tests

### 14. Security Tests

#### Test Case 14.1: Credential Security
**Objective**: Verify secure handling of CCI credentials
**Input**: CCI credentials in environment variables
**Expected Result**: Credentials not exposed in logs or outputs
**Test Steps**:
1. Deploy with credentials in environment
2. Review all log outputs
3. Verify credentials are not logged
4. Verify secure credential loading
5. Check for credential leakage in error messages

#### Test Case 14.2: Namespace Isolation
**Objective**: Verify operations are limited to configured namespace
**Input**: Multi-namespace environment
**Expected Result**: Operations only affect target namespace
**Test Steps**:
1. Deploy in specific namespace
2. Create resources in other namespaces
3. Verify cron-dispatcher only affects target namespace
4. Verify no cross-namespace access

#### Test Case 14.3: RBAC Compliance
**Objective**: Verify minimal required permissions
**Input**: Restricted RBAC configuration
**Expected Result**: Operations succeed with minimal permissions
**Test Steps**:
1. Configure minimal RBAC permissions for cron-dispatcher
2. Deploy cron-dispatcher
3. Verify all operations work
4. Verify no permission escalation
5. Test with insufficient permissions to verify failure

#### Test Case 14.4: Secret Management
**Objective**: Verify proper handling of Kubernetes secrets
**Input**: Credentials stored in Kubernetes secrets
**Expected Result**: Secrets accessed securely
**Test Steps**:
1. Store credentials in Kubernetes secrets
2. Configure cron-dispatcher to use secrets
3. Verify secrets are loaded correctly
4. Verify secrets are not exposed in logs
5. Verify secret rotation handling

## Test Data and Fixtures

### Sample Task Configuration
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-cron-dispatcher-config
  namespace: cron-dispatcher-test
data:
  tasks.yaml: |
    - name: test-task-1
      schedule: "*/5 * * * *"  # Every 5 minutes
      podDefinitionConfigmap: test-pod-template-1
      state: on
    - name: test-task-2
      schedule: "0 */1 * * *"  # Every hour
      podDefinitionConfigmap: test-pod-template-2
      state: off
    - name: test-task-3
      schedule: "30 2 * * *"   # Daily at 2:30 AM
      podDefinitionConfigmap: test-pod-template-3
      state: on
    - name: test-quartz-task
      schedule: "0 0 */6 * * *"  # Quartz format - every 6 hours
      podDefinitionConfigmap: test-pod-template-1
      state: on
```

### Sample Pod Template
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-pod-template-1
  namespace: cron-dispatcher-test
data:
  pod.yaml: |
    apiVersion: v1
    kind: Pod
    spec:
      containers:
      - name: test-container
        image: busybox:latest
        command: ["echo", "Test task executed"]
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "200m"
            memory: "256Mi"
      restartPolicy: Never
```

### Sample GC Policy
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-cron-dispatcher-gc-policy
  namespace: cron-dispatcher-test
data:
  gc-policy.yaml: |
    global:
      success: 2
      failure: 2
    tasks:
      - taskSelector:
          cron-dispatcher.io/task-name: "critical-task"
        success: 5
        failure: 3
    labelSelector:
      matchLabels:
        app.kubernetes.io/managed-by: cron-dispatcher
    cleanupInterval: "30m"
```

### Sample Invalid Configurations

#### Invalid Task Configuration
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: invalid-task-config
  namespace: cron-dispatcher-test
data:
  tasks.yaml: |
    - name: invalid-task
      schedule: "invalid cron"
      podDefinitionConfigmap: non-existent-template
      state: on
    - name: missing-fields
      schedule: "0 0 * * *"
      # Missing podDefinitionConfigmap
```

#### Invalid Pod Template
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: invalid-pod-template
  namespace: cron-dispatcher-test
data:
  pod.yaml: |
    apiVersion: v1
    kind: Pod
    spec:
      containers:
      - name: test-container
        # Missing image field
        command: ["echo", "test"]
```

## Test Execution Guidelines

### Automated Test Execution
1. **Unit Tests**: Run using pytest framework
2. **Integration Tests**: Use test environment with mock CCI services
3. **End-to-End Tests**: Execute in dedicated test namespace
4. **Performance Tests**: Run in isolated environment with monitoring

### Manual Test Execution
1. **Security Tests**: Manual review of logs and configurations
2. **Compliance Tests**: Manual audit of system behavior
3. **Error Recovery**: Manual injection of failure conditions

### Test Environment Cleanup
1. Delete all test Pods after each test run
2. Clean up test ConfigMaps and secrets
3. Reset crontab to clean state
4. Clear test logs and temporary files

### Test Reporting
1. Generate detailed test reports with pass/fail status
2. Include performance metrics for load tests
3. Document any security findings
4. Provide recommendations for improvements
