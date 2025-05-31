#!/bin/bash

# CronDispatcher Build Preparation Script
# Prepares dependencies and resources for Dockerfile build in CodeArts Pipeline

set -e

# Default values
SKIP_VALIDATION=false

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage
show_usage() {
    cat << EOF
CronDispatcher Build Preparation Script

Usage: $0 [OPTIONS]

Options:
    --skip-validation      Skip dependency validation checks
    --help                 Show this help message

Examples:
    # Prepare for build
    $0

    # Skip validation (for debugging)
    $0 --skip-validation

Purpose:
    This script prepares all necessary dependencies and resources for Docker image build.
    The actual image building is handled by CodeArts build plugins.

Preparation Tasks:
    - Validate build context and dependencies
    - Generate build metadata
    - Optimize build context for CodeArts
    - Clean up previous build artifacts

Prerequisites:
    - Python 3.9+ installed (for validation)
    - All source files present in correct structure

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-validation)
            SKIP_VALIDATION=true
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate build context structure
validate_build_context() {
    print_info "Validating build context structure..."
    
    # Check required files
    local required_files=(
        "Dockerfile"
        "requirements.txt"
        "src/main.py"
        "src/pod_creator.py"
        "src/pod_cleaner.py"
        "scripts/health_check.sh"
    )
    
    local missing_files=()
    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            missing_files+=("$file")
        fi
    done
    
    if [[ ${#missing_files[@]} -gt 0 ]]; then
        print_error "Missing required files:"
        for file in "${missing_files[@]}"; do
            print_error "  - $file"
        done
        exit 1
    fi
    
    # Check required directories
    local required_dirs=("src" "scripts" "config")
    local missing_dirs=()
    
    for dir in "${required_dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            missing_dirs+=("$dir")
        fi
    done
    
    if [[ ${#missing_dirs[@]} -gt 0 ]]; then
        print_error "Missing required directories:"
        for dir in "${missing_dirs[@]}"; do
            print_error "  - $dir"
        done
        exit 1
    fi
    
    print_success "Build context structure validation passed"
}

# Validate Python dependencies
validate_python_dependencies() {
    print_info "Validating Python dependencies..."
    
    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        print_warning "Python3 not found in PATH, skipping dependency validation"
        return 0
    fi
    
    # Display Python and pip version information
    print_info "Environment information:"
    local python_version=$(python3 --version 2>&1)
    print_info "  Python: $python_version"
    
    if command -v pip3 &> /dev/null; then
        local pip_version=$(pip3 --version 2>&1)
        print_info "  Pip: $pip_version"
    else
        print_warning "  Pip3 not found, using python3 -m pip"
    fi
    
    # Check pip functionality
    if ! python3 -m pip --version &> /dev/null; then
        print_error "pip module is not working properly"
        exit 1
    fi
    
    # Check if requirements.txt exists
    if [[ ! -f "requirements.txt" ]]; then
        print_error "requirements.txt file not found"
        exit 1
    fi
    
    # Display requirements.txt content
    print_info "Contents of requirements.txt:"
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ -n "$line" ]] && [[ ! "$line" =~ ^[[:space:]]*# ]]; then
            print_info "  $line"
        fi
    done < requirements.txt
    
    print_info "Checking requirements.txt syntax..."
    
    # First, try to validate the entire requirements.txt file
    if python3 -m pip install --dry-run -r requirements.txt &> /dev/null; then
        print_success "Python dependencies validation passed"
        return 0
    fi
    
    # If overall validation fails, check each dependency individually
    print_warning "Overall requirements.txt validation failed, checking individual dependencies..."
    
    local failed_deps=()
    local success_count=0
    local total_count=0
    
    # Read requirements.txt line by line
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip empty lines and comments
        if [[ -z "$line" ]] || [[ "$line" =~ ^[[:space:]]*# ]]; then
            continue
        fi
        
        # Clean up the line (remove leading/trailing whitespace)
        line=$(echo "$line" | xargs)
        
        # Skip if still empty after cleanup
        if [[ -z "$line" ]]; then
            continue
        fi
        
        total_count=$((total_count + 1))
        
        print_info "Checking dependency: $line"
        
        # Create a temporary requirements file with just this dependency
        echo "$line" > /tmp/temp_req.txt
        
        # Test this specific dependency
        if python3 -m pip install --dry-run -r /tmp/temp_req.txt &> /dev/null; then
            print_success "✓ $line - OK"
            success_count=$((success_count + 1))
        else
            print_error "✗ $line - FAILED"
            failed_deps+=("$line")
            
            # Try to get more detailed error information
            print_info "Detailed error for $line:"
            python3 -m pip install --dry-run -r /tmp/temp_req.txt 2>&1 | head -5 | while read -r error_line; do
                print_info "  $error_line"
            done
        fi
        
        # Clean up temporary file
        rm -f /tmp/temp_req.txt
        
    done < requirements.txt
    
    # Summary report
    echo
    print_info "Dependency validation summary:"
    print_info "Total dependencies checked: $total_count"
    print_info "Successful: $success_count"
    print_info "Failed: ${#failed_deps[@]}"
    
    if [[ ${#failed_deps[@]} -gt 0 ]]; then
        echo
        print_error "The following dependencies failed validation:"
        for dep in "${failed_deps[@]}"; do
            print_error "  - $dep"
        done
        
        echo
        print_info "Possible solutions:"
        print_info "1. Check network connectivity to PyPI"
        print_info "2. Verify package names and versions exist"
        print_info "3. Try using version ranges instead of fixed versions"
        print_info "4. Check if packages are available in your region"
        
        exit 1
    else
        print_success "All individual dependencies validated successfully"
        print_warning "Note: Individual validation passed but combined validation failed"
        print_info "This might indicate dependency conflicts or version incompatibilities"
    fi
}

# Validate Dockerfile
validate_dockerfile() {
    print_info "Validating Dockerfile..."
    
    # Check if Dockerfile exists
    if [[ ! -f "Dockerfile" ]]; then
        print_error "Dockerfile not found"
        exit 1
    fi
    
    print_success "Dockerfile validation passed"
}

# Generate build metadata
generate_build_metadata() {
    print_info "Generating build metadata..."
    
    local metadata_file="build-metadata.json"
    local build_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local git_commit=""
    local git_branch=""
    
    # Get Git information if available
    if command -v git &> /dev/null && git rev-parse --git-dir &> /dev/null; then
        git_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        git_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    else
        git_commit="unknown"
        git_branch="unknown"
    fi
    
    # Create metadata JSON
    cat > "$metadata_file" << EOF
{
  "build": {
    "timestamp": "$build_time",
    "git": {
      "commit": "$git_commit",
      "branch": "$git_branch"
    },
    "version": "$(date +%Y%m%d)-$git_commit"
  },
  "application": {
    "name": "cron-dispatcher",
    "description": "Kubernetes namespace-level cron job management platform"
  }
}
EOF
    
    print_success "Build metadata generated: $metadata_file"
}

# Prepare health check script
prepare_health_check() {
    print_info "Preparing health check script..."
    
    local health_script="scripts/health_check.sh"
    
    if [[ -f "$health_script" ]]; then
        # Make health check script executable
        chmod +x "$health_script"
        print_success "Health check script prepared and made executable"
    else
        print_warning "Health check script not found: $health_script"
    fi
}

# Clean up previous build artifacts
cleanup_build_artifacts() {
    print_info "Cleaning up previous build artifacts..."
    
    # Remove previous build files
    local cleanup_files=("build-metadata.json")
    
    for file in "${cleanup_files[@]}"; do
        if [[ -f "$file" ]]; then
            rm -f "$file"
            print_info "Removed: $file"
        fi
    done
    
    # Remove Python cache
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    
    print_success "Build artifacts cleanup completed"
}

# Main execution
main() {
    print_info "CronDispatcher Build Preparation Script"
    print_info "======================================"
    print_info "Skip Validation: $SKIP_VALIDATION"
    echo
    
    # Clean up previous artifacts
    cleanup_build_artifacts
    
    # Validation phase
    if [[ "$SKIP_VALIDATION" != true ]]; then
        validate_build_context
        validate_python_dependencies
        validate_dockerfile
    else
        print_warning "Skipping validation checks as requested"
    fi
    
    # Preparation phase
    generate_build_metadata
    prepare_health_check
    
    print_success "Build preparation completed successfully!"
    echo
    
    # Show next steps
    print_info "Next steps for CodeArts Pipeline:"
    print_info "1. Build context is ready for Docker image build"
    print_info "2. Use CodeArts Docker build plugin with current directory as context"
    print_info "3. Build metadata available in: build-metadata.json"
    print_info "4. Recommended image tag: \$(cat build-metadata.json | jq -r '.build.version')"
    echo
    print_info "CodeArts Docker Build Plugin Configuration:"
    print_info "- Context Path: ."
    print_info "- Dockerfile: ./Dockerfile"
}

# Run main function
main 