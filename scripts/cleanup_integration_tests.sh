#!/bin/bash

echo "=== Integration Test Cleanup Script ==="
echo "This script will clean up resources created by integration tests"
echo ""

# Function to clean up Docker containers
cleanup_containers() {
    echo "=== Cleaning Up Integration Test Containers ==="
    
    # Find all containers with integration test naming pattern
    CONTAINERS=$(docker ps -a --filter "name=cron-dispatcher-it-container-" --format "{{.Names}}")
    
    if [ -z "$CONTAINERS" ]; then
        echo "No integration test containers found."
        return 0
    fi
    
    echo "Found integration test containers:"
    echo "$CONTAINERS"
    echo ""
    
    read -p "Do you want to remove these containers? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing containers..."
        for container in $CONTAINERS; do
            echo "Removing container: $container"
            docker rm -f "$container" 2>/dev/null || echo "Failed to remove $container"
        done
        echo "Container cleanup completed."
    else
        echo "Skipping container cleanup."
    fi
}

# Function to clean up Docker images
cleanup_images() {
    echo ""
    echo "=== Cleaning Up Integration Test Images ==="
    
    # Find all images with integration test naming pattern
    IMAGES=$(docker images --filter "reference=cron-dispatcher-integration-test" --format "{{.Repository}}:{{.Tag}}")
    
    if [ -z "$IMAGES" ]; then
        echo "No integration test images found."
        return 0
    fi
    
    echo "Found integration test images:"
    echo "$IMAGES"
    echo ""
    
    read -p "Do you want to remove these images? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing images..."
        for image in $IMAGES; do
            echo "Removing image: $image"
            docker rmi "$image" 2>/dev/null || echo "Failed to remove $image"
        done
        echo "Image cleanup completed."
    else
        echo "Skipping image cleanup."
    fi
}

# Function to clean up CCI resources
cleanup_cci_resources() {
    echo ""
    echo "=== Cleaning Up CCI Resources ==="
    
    # Check if ccictl is available
    if ! command -v ccictl &> /dev/null; then
        echo "ccictl not found. Skipping CCI resource cleanup."
        echo "You may need to manually clean up CCI resources if any exist."
        return 0
    fi
    
    # Find all test namespaces (with random suffixes)
    echo "Searching for integration test namespaces..."
    TEST_NAMESPACES=$(ccictl get namespaces --no-headers 2>/dev/null | grep "cron-dispatcher-integration-test" | awk '{print $1}' || true)
    
    if [ -z "$TEST_NAMESPACES" ]; then
        echo "No integration test namespaces found."
        return 0
    fi
    
    echo "Found integration test namespaces:"
    echo "$TEST_NAMESPACES"
    echo ""
    echo "These namespaces may contain:"
    echo "  - ConfigMaps"
    echo "  - Pods"
    echo "  - Other test resources"
    echo ""
    
    read -p "Do you want to delete ALL these test namespaces? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        for namespace in $TEST_NAMESPACES; do
            echo "Deleting namespace: $namespace"
            ccictl delete namespace "$namespace" --wait=false
        done
        echo "Namespace deletions initiated (may take a few moments to complete)."
    else
        echo "Skipping namespace cleanup."
        echo "You can manually clean up with:"
        for namespace in $TEST_NAMESPACES; do
            echo "  ccictl delete namespace $namespace"
        done
    fi
}

# Function to clean up dangling resources
cleanup_dangling_resources() {
    echo ""
    echo "=== Cleaning Up Dangling Docker Resources ==="
    
    read -p "Do you want to remove dangling Docker images and volumes? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing dangling images..."
        docker image prune -f
        
        echo "Removing dangling volumes..."
        docker volume prune -f
        
        echo "Dangling resource cleanup completed."
    else
        echo "Skipping dangling resource cleanup."
    fi
}

# Function to show current resource usage
show_current_usage() {
    echo ""
    echo "=== Current Docker Resource Usage ==="
    
    echo "Docker Images:"
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}" | head -10
    
    echo ""
    echo "Docker Containers:"
    docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.CreatedAt}}" | head -10
    
    echo ""
    echo "Docker System Info:"
    docker system df
}

# Main execution
main() {
    # Show current usage first
    show_current_usage
    
    echo ""
    echo "=== Starting Cleanup Process ==="
    
    # Clean up containers
    cleanup_containers
    
    # Clean up images
    cleanup_images
    
    # Clean up CCI resources
    cleanup_cci_resources
    
    # Clean up dangling resources
    cleanup_dangling_resources
    
    echo ""
    echo "=== Cleanup Process Completed ==="
    echo "Final resource usage:"
    show_current_usage
    
    echo ""
    echo "If you need to clean up additional resources manually:"
    echo "  - List all containers: docker ps -a"
    echo "  - List all images: docker images"
    echo "  - List CCI namespaces: ccictl get namespaces"
    echo "  - System cleanup: docker system prune"
}

# Run main function
main 