# CronDispatcher Test Cases

## Overview

This document outlines comprehensive test cases for the CronDispatcher project, covering all major functionality including configuration management, Pod creation, garbage collection, and error handling scenarios.

## Test Environment Setup

### Prerequisites

1. **CCI 2.0 Environment**: Access to Huawei Cloud Container Instance
2. **Test Namespace**: Dedicated namespace for testing (e.g., `cron-dispatcher-test`)
3. **Test Credentials**: Valid CCI credentials with minimal required permissions
4. **Test ConfigMaps**: Sample task and policy configurations

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

### 1. Configuration Loading Tests

#### Test Case 1.1: Valid Task Configuration Loading
**Objective**: Verify successful loading of valid task configuration
**Input**: Valid `tasks.yaml` in ConfigMap
**Expected Result**: Configuration loaded successfully, all tasks parsed correctly
**Test Steps**:
1. Create ConfigMap with valid task configuration
2. Call `load_config_from_file()`
3. Verify returned task list contains expected tasks
4. Verify all required fields are present

#### Test Case 1.2: Invalid YAML Configuration
**Objective**: Verify error handling for malformed YAML
**Input**: ConfigMap with invalid YAML syntax
**Expected Result**: Error logged, `None` returned
**Test Steps**:
1. Create ConfigMap with malformed YAML
2. Call `load_config_from_file()`
3. Verify error is logged
4. Verify `None` is returned

#### Test Case 1.3: Missing Configuration File
**Objective**: Verify handling of missing configuration file
**Input**: Non-existent configuration file path
**Expected Result**: Warning logged, `None` returned
**Test Steps**:
1. Set non-existent file path
2. Call `load_config_from_file()`
3. Verify warning is logged
4. Verify `None` is returned

### 2. Cron Expression Validation Tests

#### Test Case 2.1: Valid Unix Cron Expression
**Objective**: Verify validation of standard Unix cron expressions
**Input**: `"0 */6 * * *"` (every 6 hours)
**Expected Result**: Validation passes
**Test Steps**:
1. Call `validate_cron_expression()` with valid expression
2. Verify `True` is returned

#### Test Case 2.2: Valid Quartz Cron Expression
**Objective**: Verify validation and conversion of Quartz format
**Input**: `"0 0 */6 * * *"` (Quartz format)
**Expected Result**: Validation passes, converted to Unix format
**Test Steps**:
1. Call `validate_cron_expression()` with Quartz expression
2. Verify `True` is returned
3. Verify `_convert_quartz_to_cron()` produces correct Unix format

#### Test Case 2.3: Invalid Cron Expression
**Objective**: Verify rejection of invalid cron expressions
**Input**: `"invalid cron"` (malformed expression)
**Expected Result**: Validation fails, error logged
**Test Steps**:
1. Call `validate_cron_expression()` with invalid expression
2. Verify `False` is returned
3. Verify error is logged

### 3. ConfigMap Validation Tests

#### Test Case 3.1: Existing ConfigMap Validation
**Objective**: Verify detection of existing ConfigMaps
**Input**: Name of existing ConfigMap
**Expected Result**: Validation passes
**Test Steps**:
1. Create test ConfigMap
2. Call `validate_configmap_exists()` with ConfigMap name
3. Verify `True` is returned

#### Test Case 3.2: Non-existent ConfigMap Validation
**Objective**: Verify detection of missing ConfigMaps
**Input**: Name of non-existent ConfigMap
**Expected Result**: Validation fails, warning logged
**Test Steps**:
1. Call `validate_configmap_exists()` with non-existent name
2. Verify `False` is returned
3. Verify warning is logged

### 4. Garbage Collection Policy Tests

#### Test Case 4.1: Default Policy Loading
**Objective**: Verify loading of default GC policy when file is missing
**Input**: Missing GC policy file
**Expected Result**: Default policy returned
**Test Steps**:
1. Ensure GC policy file doesn't exist
2. Call `load_gc_policy()`
3. Verify default policy structure is returned
4. Verify default values (success: 3, failure: 3)

#### Test Case 4.2: Custom Policy Loading
**Objective**: Verify loading of custom GC policy
**Input**: Valid custom GC policy ConfigMap
**Expected Result**: Custom policy loaded successfully
**Test Steps**:
1. Create ConfigMap with custom GC policy
2. Call `load_gc_policy()`
3. Verify custom policy values are returned

#### Test Case 4.3: Cleanup Interval Parsing
**Objective**: Verify parsing of various cleanup interval formats
**Input**: Different interval formats (`30s`, `5m`, `1h`, `1d`, `120`)
**Expected Result**: Correct conversion to seconds
**Test Steps**:
1. Test each format with `_parse_interval_to_seconds()`
2. Verify correct conversion:
   - `30s` → 30
   - `5m` → 300
   - `1h` → 3600
   - `1d` → 86400
   - `120` → 120

## Integration Tests

### 5. CCI Authentication Tests

#### Test Case 5.1: Successful Authentication
**Objective**: Verify successful CCI authentication setup
**Input**: Valid CCI credentials
**Expected Result**: Authentication configured successfully
**Test Steps**:
1. Set valid environment variables
2. Call `initialize_cci_authentication()`
3. Verify `True` is returned
4. Verify ccictl is configured correctly

#### Test Case 5.2: Missing Credentials
**Objective**: Verify handling of missing credentials
**Input**: Missing required environment variables
**Expected Result**: Authentication fails gracefully
**Test Steps**:
1. Unset required environment variables
2. Call `initialize_cci_authentication()`
3. Verify `False` is returned
4. Verify error is logged

#### Test Case 5.3: Invalid Credentials
**Objective**: Verify handling of invalid credentials
**Input**: Invalid CCI credentials
**Expected Result**: Authentication fails, error logged
**Test Steps**:
1. Set invalid credentials
2. Call `initialize_cci_authentication()`
3. Verify `False` is returned
4. Verify error is logged

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

### 7. Crontab Management Tests

#### Test Case 7.1: Crontab Update with Valid Tasks
**Objective**: Verify successful crontab update with valid tasks
**Input**: List of valid task configurations
**Expected Result**: Crontab updated with correct entries
**Test Steps**:
1. Prepare list of valid tasks
2. Call `update_crontab()` with task list
3. Verify crontab contains correct entries
4. Verify each entry has correct schedule and command

#### Test Case 7.2: Crontab Update with Mixed Valid/Invalid Tasks
**Objective**: Verify handling of mixed valid and invalid tasks
**Input**: List containing both valid and invalid tasks
**Expected Result**: Only valid tasks added to crontab
**Test Steps**:
1. Prepare mixed task list
2. Call `update_crontab()` with task list
3. Verify only valid tasks are in crontab
4. Verify warnings logged for invalid tasks

#### Test Case 7.3: Crontab Update with Disabled Tasks
**Objective**: Verify handling of disabled tasks
**Input**: Tasks with `state: off`
**Expected Result**: Disabled tasks not added to crontab
**Test Steps**:
1. Prepare tasks with `state: off`
2. Call `update_crontab()` with task list
3. Verify disabled tasks are not in crontab
4. Verify info messages logged for skipped tasks

### 8. Hot Configuration Update Tests

#### Test Case 8.1: Task Configuration Hot Update
**Objective**: Verify detection and application of task configuration changes
**Input**: Modified task configuration ConfigMap
**Expected Result**: Changes detected and applied automatically
**Test Steps**:
1. Deploy initial configuration
2. Wait for initial load
3. Modify task configuration ConfigMap
4. Wait for detection interval (30 seconds)
5. Verify changes are applied to crontab

#### Test Case 8.2: GC Policy Hot Update
**Objective**: Verify detection and application of GC policy changes
**Input**: Modified GC policy ConfigMap
**Expected Result**: Policy changes detected and applied
**Test Steps**:
1. Deploy initial GC policy
2. Wait for initial load
3. Modify GC policy ConfigMap
4. Wait for detection interval
5. Verify new policy is applied

#### Test Case 8.3: Multiple Simultaneous Updates
**Objective**: Verify handling of simultaneous configuration updates
**Input**: Both task and GC policy changes
**Expected Result**: Both changes detected and applied
**Test Steps**:
1. Modify both ConfigMaps simultaneously
2. Wait for detection interval
3. Verify both changes are applied
4. Verify no conflicts or errors

## End-to-End Tests

### 9. Complete Workflow Tests

#### Test Case 9.1: Full Deployment and Execution
**Objective**: Verify complete CronDispatcher workflow
**Input**: Complete deployment configuration
**Expected Result**: Tasks scheduled and executed successfully
**Test Steps**:
1. Deploy CronDispatcher with test configuration
2. Verify deployment is healthy
3. Verify tasks are scheduled in crontab
4. Wait for task execution time
5. Verify Pods are created and executed
6. Verify Pod labels and annotations

#### Test Case 9.2: Garbage Collection Execution
**Objective**: Verify garbage collection functionality
**Input**: Multiple completed Pods exceeding retention limits
**Expected Result**: Excess Pods cleaned up according to policy
**Test Steps**:
1. Create multiple completed test Pods
2. Configure GC policy with low retention limits
3. Trigger garbage collection
4. Verify excess Pods are deleted
5. Verify retained Pods match policy

#### Test Case 9.3: Error Recovery and Resilience
**Objective**: Verify system recovery from various error conditions
**Input**: Simulated error conditions
**Expected Result**: System recovers gracefully
**Test Steps**:
1. Simulate network failures
2. Simulate ConfigMap corruption
3. Simulate CCI API failures
4. Verify system continues operating
5. Verify errors are logged appropriately

## Performance Tests

### 10. Load and Stress Tests

#### Test Case 10.1: High Task Volume
**Objective**: Verify performance with large number of tasks
**Input**: 100+ task configurations
**Expected Result**: All tasks processed within acceptable time
**Test Steps**:
1. Create configuration with 100+ tasks
2. Deploy CronDispatcher
3. Measure configuration load time
4. Verify all tasks are scheduled
5. Monitor resource usage

#### Test Case 10.2: Rapid Configuration Changes
**Objective**: Verify handling of frequent configuration updates
**Input**: Rapid successive configuration changes
**Expected Result**: All changes processed correctly
**Test Steps**:
1. Implement rapid configuration changes
2. Monitor system response
3. Verify all changes are applied
4. Check for race conditions or errors

#### Test Case 10.3: Large-Scale Garbage Collection
**Objective**: Verify GC performance with many Pods
**Input**: 1000+ Pods requiring cleanup
**Expected Result**: Cleanup completes within reasonable time
**Test Steps**:
1. Create large number of test Pods
2. Configure aggressive GC policy
3. Trigger garbage collection
4. Measure cleanup time
5. Verify batch processing works correctly

## Security Tests

### 11. Security and Access Control Tests

#### Test Case 11.1: Credential Security
**Objective**: Verify secure handling of CCI credentials
**Input**: CCI credentials in Kubernetes secrets
**Expected Result**: Credentials not exposed in logs or outputs
**Test Steps**:
1. Deploy with credentials in secrets
2. Review all log outputs
3. Verify credentials are not logged
4. Verify secure credential loading

#### Test Case 11.2: Namespace Isolation
**Objective**: Verify operations are limited to configured namespace
**Input**: Multi-namespace environment
**Expected Result**: Operations only affect target namespace
**Test Steps**:
1. Deploy in specific namespace
2. Create resources in other namespaces
3. Verify CronDispatcher only affects target namespace
4. Verify no cross-namespace access

#### Test Case 11.3: RBAC Compliance
**Objective**: Verify minimal required permissions
**Input**: Restricted RBAC configuration
**Expected Result**: Operations succeed with minimal permissions
**Test Steps**:
1. Configure minimal RBAC permissions
2. Deploy CronDispatcher
3. Verify all operations work
4. Verify no permission escalation

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
          cron-dispatcher.io/task-name: "test-task-1"
        success: 5
        failure: 3
    labelSelector:
      matchLabels:
        app.kubernetes.io/managed-by: CronDispatcher
    cleanupInterval: "2m"
```

## Test Execution Guidelines

### Pre-Test Setup
1. Ensure test environment is clean
2. Deploy test ConfigMaps and secrets
3. Verify CCI connectivity
4. Set appropriate log levels for debugging

### Test Execution Order
1. Unit tests (configuration, validation)
2. Integration tests (authentication, Pod creation)
3. End-to-end tests (complete workflows)
4. Performance tests (load, stress)
5. Security tests (access control, isolation)

### Post-Test Cleanup
1. Remove test Pods and ConfigMaps
2. Clean up test namespace
3. Archive test logs and results
4. Document any issues or failures

## Success Criteria

### Functional Requirements
- All unit tests pass with 100% success rate
- Integration tests demonstrate correct component interaction
- End-to-end tests verify complete workflow functionality
- Hot configuration updates work within 30 seconds

### Performance Requirements
- Configuration loading completes within 5 seconds for 100 tasks
- Pod creation completes within 30 seconds
- Garbage collection processes 1000 Pods within 5 minutes
- Memory usage remains stable under load

### Security Requirements
- No credential exposure in logs or outputs
- Namespace isolation maintained
- Minimal required permissions sufficient
- No security vulnerabilities detected

### Reliability Requirements
- System recovers from transient failures
- Configuration errors handled gracefully
- No data loss during updates
- Consistent behavior across test runs
