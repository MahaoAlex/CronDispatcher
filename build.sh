#!/bin/bash

# CronDispatcher build and deployment script
set -e

# Configuration variables
IMAGE_NAME="cron-dispatcher"
IMAGE_TAG="v1.0.0"
REGISTRY_URL=""  # Set your image registry address, e.g.: your-registry.com/namespace
NAMESPACE="default"  # Set target namespace

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Log functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check dependencies
check_dependencies() {
    log_info "Checking build dependencies..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v kubectl &> /dev/null; then
        log_warning "kubectl is not installed, will skip Kubernetes deployment steps"
        SKIP_DEPLOY=true
    fi
    
    log_success "Dependency check completed"
}

# Build Docker image
build_image() {
    log_info "Starting Docker image build..."
    
    # Build image
    if [ -n "$REGISTRY_URL" ]; then
        FULL_IMAGE_NAME="${REGISTRY_URL}/${IMAGE_NAME}:${IMAGE_TAG}"
    else
        FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"
    fi
    
    log_info "Building image: $FULL_IMAGE_NAME"
    
    docker build -t "$FULL_IMAGE_NAME" .
    
    if [ $? -eq 0 ]; then
        log_success "Image build successful: $FULL_IMAGE_NAME"
        
        # Also tag as latest
        if [ -n "$REGISTRY_URL" ]; then
            docker tag "$FULL_IMAGE_NAME" "${REGISTRY_URL}/${IMAGE_NAME}:latest"
        else
            docker tag "$FULL_IMAGE_NAME" "${IMAGE_NAME}:latest"
        fi
        
    else
        log_error "Image build failed"
        exit 1
    fi
}

# Push image to registry
push_image() {
    if [ -n "$REGISTRY_URL" ]; then
        log_info "Pushing image to registry..."
        
        docker push "${REGISTRY_URL}/${IMAGE_NAME}:${IMAGE_TAG}"
        docker push "${REGISTRY_URL}/${IMAGE_NAME}:latest"
        
        if [ $? -eq 0 ]; then
            log_success "Image push successful"
        else
            log_error "Image push failed"
            exit 1
        fi
    else
        log_warning "Registry URL not set, skipping push step"
    fi
}

# Update Kubernetes configuration
update_k8s_config() {
    log_info "Updating Kubernetes configuration files..."
    
    # Update image address and namespace in deployment.yaml
    if [ -n "$REGISTRY_URL" ]; then
        sed -i.bak "s|image: cron-dispatcher:latest|image: ${REGISTRY_URL}/${IMAGE_NAME}:${IMAGE_TAG}|g" config/deployment.yaml
    else
        sed -i.bak "s|image: cron-dispatcher:latest|image: ${IMAGE_NAME}:${IMAGE_TAG}|g" config/deployment.yaml
    fi
    
    # Update namespace
    sed -i.bak "s|namespace: default|namespace: ${NAMESPACE}|g" config/deployment.yaml
    sed -i.bak "s|namespace: default|namespace: ${NAMESPACE}|g" config/cron-dispatcher-config.yaml
    
    log_success "Kubernetes configuration update completed"
}

# Deploy to Kubernetes
deploy_to_k8s() {
    if [ "$SKIP_DEPLOY" = true ]; then
        log_warning "Skipping Kubernetes deployment"
        return
    fi
    
    log_info "Deploying to Kubernetes..."
    
    # Create namespace (if it doesn't exist)
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
    
    # Apply configuration
    kubectl apply -f config/cron-dispatcher-config.yaml -n "$NAMESPACE"
    kubectl apply -f config/deployment.yaml -n "$NAMESPACE"
    
    if [ $? -eq 0 ]; then
        log_success "Kubernetes deployment successful"
        
        # Wait for deployment to complete
        log_info "Waiting for Pod to start..."
        kubectl wait --for=condition=ready pod -l app=cron-dispatcher -n "$NAMESPACE" --timeout=300s
        
        if [ $? -eq 0 ]; then
            log_success "Pod started successfully"
            
            # Show deployment status
            log_info "Deployment status:"
            kubectl get pods -l app=cron-dispatcher -n "$NAMESPACE"
            kubectl get svc -l app=cron-dispatcher -n "$NAMESPACE"
        else
            log_warning "Pod startup timeout, please check logs"
        fi
    else
        log_error "Kubernetes deployment failed"
        exit 1
    fi
}

# Clean up backup files
cleanup() {
    log_info "Cleaning up temporary files..."
    rm -f config/*.bak
    log_success "Cleanup completed"
}

# Show usage instructions
show_usage() {
    echo "CronDispatcher build and deployment script"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -r, --registry URL    Set image registry address"
    echo "  -n, --namespace NAME  Set target namespace (default: default)"
    echo "  -t, --tag TAG         Set image tag (default: v1.0.0)"
    echo "  --build-only          Build image only, do not deploy"
    echo "  --deploy-only         Deploy only, do not build image"
    echo "  -h, --help            Show this help information"
    echo ""
    echo "Examples:"
    echo "  $0 --registry your-registry.com/namespace --namespace cv-cd-generators"
    echo "  $0 --build-only --tag v1.1.0"
    echo "  $0 --deploy-only --namespace data-ingest"
}

# Parse command line arguments
BUILD_ONLY=false
DEPLOY_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--registry)
            REGISTRY_URL="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --deploy-only)
            DEPLOY_ONLY=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown parameter: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main process
main() {
    log_info "Starting CronDispatcher build and deployment process..."
    log_info "Image name: $IMAGE_NAME"
    log_info "Image tag: $IMAGE_TAG"
    log_info "Target namespace: $NAMESPACE"
    
    if [ -n "$REGISTRY_URL" ]; then
        log_info "Image registry: $REGISTRY_URL"
    fi
    
    check_dependencies
    
    if [ "$DEPLOY_ONLY" != true ]; then
        build_image
        push_image
    fi
    
    if [ "$BUILD_ONLY" != true ]; then
        update_k8s_config
        deploy_to_k8s
    fi
    
    cleanup
    
    log_success "CronDispatcher build and deployment completed!"
    
    if [ "$BUILD_ONLY" != true ] && [ "$SKIP_DEPLOY" != true ]; then
        echo ""
        log_info "Next steps:"
        echo "1. Check Pod status: kubectl get pods -l app=cron-dispatcher -n $NAMESPACE"
        echo "2. View logs: kubectl logs -l app=cron-dispatcher -n $NAMESPACE -f"
        echo "3. Check health status: kubectl port-forward svc/cron-dispatcher-service 8080:8080 -n $NAMESPACE"
        echo "   Then visit: http://localhost:8080/health"
    fi

    echo "Environment Variables:"
    echo "  NAMESPACE: Kubernetes namespace (auto-detected from pod metadata)"
    echo "  CRON_TIMEZONE: Timezone for cron jobs (default: Africa/Johannesburg)"
    echo "  GC_DRY_RUN: Enable dry run mode for garbage collection (default: false)"
    echo "  GC_BATCH_SIZE: Number of pods to delete per batch during GC (default: 50)"
    echo "  PYTHONUNBUFFERED: Python output buffering (default: 1)"
}

# Execute main process
main 