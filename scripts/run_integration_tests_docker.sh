#!/bin/bash

# Set variables
IMAGE_NAME="cron-dispatcher-integration-test"
# Generate TAG based on timestamp and short random value
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RANDOM_SHORT=$(head /dev/urandom | tr -dc a-z0-9 | head -c 6)
TAG="${TIMESTAMP}-${RANDOM_SHORT}"
CONTAINER_NAME="cron-dispatcher-it-container-${RANDOM_SHORT}"

echo "=== Starting Integration Test Docker Image Build ==="

# 1. Build integration test image
echo "Building image: ${IMAGE_NAME}:${TAG}"
docker build -f Dockerfile.integration-test -t ${IMAGE_NAME}:${TAG} .

if [ $? -eq 0 ]; then
    echo "Image build successful"
else
    echo "Image build failed"
    exit 1
fi

echo ""
echo "=== Running Integration Test Container ==="

# 2. Run container to execute integration tests
# Pass environment variables for CCI integration
echo "Running container: ${CONTAINER_NAME}"
echo "Note: Make sure CCI environment variables are set in your environment"

docker run --name ${CONTAINER_NAME} \
    -e CCI_ACCESS_KEY="${CCI_ACCESS_KEY}" \
    -e CCI_SECRET_KEY="${CCI_SECRET_KEY}" \
    -e CCI_DOMAIN_NAME="${CCI_DOMAIN_NAME}" \
    -e CCI_PROJECT_NAME="${CCI_PROJECT_NAME}" \
    -e CCI_REGION="${CCI_REGION}" \
    -e NAMESPACE="${NAMESPACE:-cron-dispatcher-integration-test}" \
    ${IMAGE_NAME}:${TAG}

# Get container exit status
EXIT_CODE=$?

echo ""
echo "=== Checking Test Results ==="

if [ $EXIT_CODE -eq 0 ]; then
    echo "Integration Tests executed successfully"
else
    echo "Integration Tests failed (exit code: $EXIT_CODE)"
fi

# 3. View container logs for detailed output
echo ""
echo "=== Container Logs ==="
docker logs ${CONTAINER_NAME}

# 4. Clean up resources - DISABLED FOR DEBUGGING
echo ""
echo "=== SKIPPING Resource Cleanup for Debugging ==="
echo "Container ${CONTAINER_NAME} preserved for inspection"
echo "To enter the container for debugging: docker exec -it ${CONTAINER_NAME} /bin/bash"
echo "To manually clean up later: docker rm ${CONTAINER_NAME}"

# 5. Clean up test image to save space - DISABLED FOR DEBUGGING  
echo ""
echo "=== SKIPPING Image Cleanup for Debugging ==="
echo "Test image ${IMAGE_NAME}:${TAG} preserved for inspection"
echo "To manually clean up later: docker rmi ${IMAGE_NAME}:${TAG}"

echo ""
echo "=== Complete ==="
echo "Final exit code: $EXIT_CODE"

# Exit with the same code as the integration tests
exit $EXIT_CODE 