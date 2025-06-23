#!/bin/bash

# Set variables
IMAGE_NAME="cron-dispatcher-unit-test"
# Generate TAG based on timestamp and short random value
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RANDOM_SHORT=$(head /dev/urandom | tr -dc a-z0-9 | head -c 6)
TAG="${TIMESTAMP}-${RANDOM_SHORT}"
CONTAINER_NAME="cron-dispatcher-ut-container-${RANDOM_SHORT}"

echo "=== Starting Unit Test Docker Image Build ==="

# 1. Build unit test image
echo "Building image: ${IMAGE_NAME}:${TAG}"
docker build -f Dockerfile.unit-test -t ${IMAGE_NAME}:${TAG} .

if [ $? -eq 0 ]; then
    echo "Image build successful"
else
    echo "Image build failed"
    exit 1
fi

echo ""
echo "=== Running Unit Test Container ==="

# 2. Run container to execute unit tests
echo "Running container: ${CONTAINER_NAME}"
docker run --name ${CONTAINER_NAME} ${IMAGE_NAME}:${TAG}

# Get container exit status
EXIT_CODE=$?

echo ""
echo "=== Checking Test Results ==="

if [ $EXIT_CODE -eq 0 ]; then
    echo "Unit Tests executed successfully"
else
    echo "Unit Tests failed (exit code: $EXIT_CODE)"
fi

# 3. View container logs for detailed output
echo ""
echo "=== Container Logs ==="
docker logs ${CONTAINER_NAME}

# 4. Clean up resources
echo ""
echo "=== Cleaning Up Resources ==="
docker rm ${CONTAINER_NAME}
echo "Container cleaned up"

# 5. Clean up test image to save space
echo ""
echo "=== Image Cleanup ==="
echo "Removing test image: ${IMAGE_NAME}:${TAG}"
docker rmi ${IMAGE_NAME}:${TAG}
if [ $? -eq 0 ]; then
    echo "Test image removed successfully"
else
    echo "Warning: Failed to remove test image"
fi

echo ""
echo "=== Complete ==="
echo "Final exit code: $EXIT_CODE"

# Exit with the same code as the unit tests
exit $EXIT_CODE