#!/usr/bin/env python3
"""
Integration Tests for Pod Creation
Verifies that the PodCreator can successfully create a Pod in a real CCI environment.
"""

import os
import time
import json
import pytest
from src.pod_creator import PodCreator
from src.utils import execute_command_with_retry, get_ccictl_command

# --- Test Configuration ---
# All tests in this file will be skipped if CCI_ACCESS_KEY is not set.
pytestmark = pytest.mark.skipif(
    not os.getenv("CCI_ACCESS_KEY"),
    reason="CCI credentials (CCI_ACCESS_KEY) not set in environment."
)

# Use NAMESPACE from environment, fallback to default test namespace
TEST_NAMESPACE = os.getenv("NAMESPACE", "cron-dispatcher-integration-test")
TEST_TASK_NAME = "my-test-task"
TEST_CONFIGMAP_NAME = "test-pod-def-configmap"
POD_YAML_CONTENT = """
apiVersion: v1
kind: Pod
metadata:
  labels:
    app: integration-test-app
spec:
  containers:
  - name: nginx
    image: nginx:latest
  restartPolicy: Never
"""

# --- Pytest Fixtures for Setup and Teardown ---

@pytest.fixture(scope="module", autouse=True)
def setup_test_namespace():
    """Create and clean up the test namespace for all tests in this module."""
    print(f"\n--- Setting up test namespace: {TEST_NAMESPACE} ---")
    cmd_create = get_ccictl_command(f"create namespace {TEST_NAMESPACE}")
    execute_command_with_retry(cmd_create, shell=True)
    
    yield # This is where the tests will run
    
    # NOTE: Teardown disabled for debugging - resources left for inspection
    print(f"\n--- SKIPPING teardown for debugging - namespace {TEST_NAMESPACE} preserved ---")
    # cmd_delete = get_ccictl_command(f"delete namespace {TEST_NAMESPACE} --wait=false")
    # execute_command_with_retry(cmd_delete, shell=True)


@pytest.fixture
def pod_configmap():
    """Create and clean up the test ConfigMap for a single test."""
    print(f"\n--- Creating test ConfigMap: {TEST_CONFIGMAP_NAME} ---")
    # Using a temporary file to create the ConfigMap from file content
    configmap_file = "/tmp/pod_cm.yaml"
    with open(configmap_file, "w") as f:
        f.write(POD_YAML_CONTENT)

    cmd_create = get_ccictl_command(f"create configmap {TEST_CONFIGMAP_NAME} --from-file=pod.yaml={configmap_file}", TEST_NAMESPACE)
    success, _, stderr = execute_command_with_retry(cmd_create, shell=True)
    assert success, f"Failed to create ConfigMap: {stderr}"
    
    yield TEST_CONFIGMAP_NAME # Provide the ConfigMap name to the test
    
    # NOTE: ConfigMap cleanup disabled for debugging - resources left for inspection
    print(f"\n--- SKIPPING ConfigMap cleanup for debugging - {TEST_CONFIGMAP_NAME} preserved ---")
    # cmd_delete = get_ccictl_command(f"delete configmap {TEST_CONFIGMAP_NAME}", TEST_NAMESPACE)
    # execute_command_with_retry(cmd_delete, shell=True)


# --- Integration Test Case ---

def test_successful_pod_creation(pod_configmap):
    """
    Given a valid ConfigMap with a Pod definition,
    When the PodCreator creates a Pod,
    Then the Pod should be successfully created in the CCI namespace.
    """
    # 1. Arrange
    # The pod_configmap fixture has already created the necessary ConfigMap.
    # The NAMESPACE should already be set from environment or default to TEST_NAMESPACE
    creator = PodCreator()

    # 2. Act
    print(f"\n--- Attempting to create Pod for task: {TEST_TASK_NAME} ---")
    creation_success = creator.create_pod(TEST_TASK_NAME, pod_configmap)
    assert creation_success, "PodCreator.create_pod reported failure."

    # 3. Assert
    # Verify that the Pod actually exists in the CCI environment.
    print("\n--- Verifying Pod creation in CCI ---")
    time.sleep(10) # Allow some time for the Pod to be created and registered
    
    # Check for any pod created for this task
    cmd_get_pod = get_ccictl_command(f"get pods -l cron-dispatcher.io/task-name={TEST_TASK_NAME} -o json", TEST_NAMESPACE)
    success, stdout, stderr = execute_command_with_retry(cmd_get_pod, shell=True)
    
    assert success, f"Failed to get Pods from CCI: {stderr}"
    
    pod_list = json.loads(stdout)
    assert "items" in pod_list and len(pod_list["items"]) > 0, "No Pod found with the expected task label."
    
    pod_name = pod_list["items"][0]["metadata"]["name"]
    print(f"Successfully verified Pod '{pod_name}' exists.")

    # NOTE: Pod cleanup disabled for debugging - resources left for inspection  
    print(f"--- SKIPPING Pod cleanup for debugging - {pod_name} preserved ---")
    # cmd_delete_pod = get_ccictl_command(f"delete pod {pod_name}", TEST_NAMESPACE)
    # execute_command_with_retry(cmd_delete_pod, shell=True) 