#!/bin/bash
# Script to run integration tests inside a Docker container

set -e

# Check for required environment variables
if [ -z "$CCI_ACCESS_KEY" ] || [ -z "$CCI_SECRET_KEY" ] || [ -z "$CCI_DOMAIN_NAME" ]; then
    echo "Error: Missing required CCI environment variables."
    echo "Please set CCI_ACCESS_KEY, CCI_SECRET_KEY, and CCI_DOMAIN_NAME."
    exit 1
fi

echo "--- Configuring ccictl Authentication ---"

# Set default region if not provided
CCI_REGION="${CCI_REGION:-af-south-1}"
CCI_PROJECT_NAME="${CCI_PROJECT_NAME:-$CCI_REGION}"

# Generate random suffix to avoid overwriting existing ccictl configurations
RANDOM_SUFFIX=$(head /dev/urandom | tr -dc a-z0-9 | head -c 6)
CLUSTER_NAME="cci-cluster-test-${RANDOM_SUFFIX}"
USER_NAME="cci-user-test-${RANDOM_SUFFIX}"
CONTEXT_NAME="cci-context-test-${RANDOM_SUFFIX}"

echo "Using test configuration names with suffix: ${RANDOM_SUFFIX}"

# Configure ccictl cluster
echo "Setting up ccictl cluster configuration..."
ccictl config set-cluster ${CLUSTER_NAME} --server=https://cci.${CCI_REGION}.myhuaweicloud.com

# Configure ccictl credentials
echo "Setting up ccictl credentials..."
ccictl config set-credentials ${USER_NAME} \
    --auth-provider=iam \
    --auth-provider-arg=iam-endpoint=https://iam.${CCI_REGION}.myhuaweicloud.com \
    --auth-provider-arg=cache=true \
    --auth-provider-arg=project-name=${CCI_PROJECT_NAME} \
    --auth-provider-arg=ak=${CCI_ACCESS_KEY} \
    --auth-provider-arg=sk=${CCI_SECRET_KEY} \
    --auth-provider-arg=domain-name=${CCI_DOMAIN_NAME}

# Configure ccictl context
echo "Setting up ccictl context..."
ccictl config set-context ${CONTEXT_NAME} --cluster=${CLUSTER_NAME} --user=${USER_NAME}
ccictl config use-context ${CONTEXT_NAME}

echo "ccictl configuration completed successfully!"

echo "--- Running Integration Tests ---"

# Function to keep container alive for debugging (run in background)
start_keep_alive_daemon() {
    local exit_code=$1
    
    # Store test results for debugging
    echo "TEST_EXIT_CODE=$exit_code" > /tmp/test_results.txt
    echo "Test completed at: $(date)" >> /tmp/test_results.txt
    
    if [ $exit_code -ne 0 ]; then
        echo "Tests failed! Starting background daemon to keep container alive for 1 hour"
        # Start daemon process in background
        nohup bash -c '
            echo "Container daemon started at $(date)" >> /tmp/container_daemon.log
            sleep 3600
            echo "Container daemon expired at $(date)" >> /tmp/container_daemon.log
        ' > /dev/null 2>&1 &
        echo "Daemon PID: $!" > /tmp/daemon.pid
    else
        echo "Tests passed! Starting background daemon to keep container alive for 5 minutes"
        # Start daemon process in background  
        nohup bash -c '
            echo "Container daemon started at $(date)" >> /tmp/container_daemon.log
            sleep 300
            echo "Container daemon expired at $(date)" >> /tmp/container_daemon.log
        ' > /dev/null 2>&1 &
        echo "Daemon PID: $!" > /tmp/daemon.pid
    fi
}

# Set Python path to include the current directory for src module imports
export PYTHONPATH="/app:$PYTHONPATH"
echo "Python path: $PYTHONPATH"

# Verify src module can be imported
echo "Verifying src module accessibility..."
python3 -c "import sys; print('Python sys.path:'); [print(f'  {p}') for p in sys.path]"
python3 -c "from src.pod_creator import PodCreator; print('✓ src.pod_creator imported successfully')"

# Run tests using pytest
python3 -m pytest tests/integration -s -v

# Store the test exit code
TEST_EXIT_CODE=$?

echo "--- Cleaning up ccictl Test Configuration ---"

# Clean up temporary ccictl configuration
echo "Removing temporary ccictl configuration..."
ccictl config delete-context ${CONTEXT_NAME} 2>/dev/null || true
ccictl config delete-cluster ${CLUSTER_NAME} 2>/dev/null || true  
ccictl config delete-user ${USER_NAME} 2>/dev/null || true

echo "ccictl configuration cleanup completed"

echo ""
echo "=== Test Execution Complete ==="
echo "Exit code: $TEST_EXIT_CODE"

if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo ""
    echo "Tests failed! Container will remain running for debugging."
    echo "You can:"
    echo "  - Check test results: cat /tmp/test_results.txt"
    echo "  - Re-run tests: python3 -m pytest tests/integration -s -v"
    echo "  - Check CCI connection: ccictl get namespaces"
    echo "  - View environment: env | grep CCI"
    echo "  - Check daemon status: cat /tmp/container_daemon.log"
    echo "  - Exit container: exit"
    echo ""
fi

# Start background daemon to keep container alive
start_keep_alive_daemon $TEST_EXIT_CODE

# Exit with the same code as the tests (main process exits, but daemon keeps container alive)
exit $TEST_EXIT_CODE 