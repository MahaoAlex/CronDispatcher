#!/bin/bash
# CronDispatcher health check script for Kubernetes probes

# Exit codes:
# 0 - healthy
# 1 - unhealthy

# Cache file for one-time checks
CACHE_FILE="/tmp/.cron-dispatcher-health-cache"

# Check crond service status (critical check - always performed)
check_crond() {
    if systemctl is-active --quiet crond 2>/dev/null; then
        return 0
    else
        echo "[FAIL] crond service is not running" >&2
        return 1
    fi
}

# Check if main application process is running
check_main_process() {
    if pgrep -f "python.*main.py" > /dev/null 2>&1; then
        return 0
    else
        echo "[WARN] CronDispatcher main process not found" >&2
        return 1
    fi
}

# Lightweight directory checks (cached for Kubernetes)
check_directories_k8s() {
    local cache_valid=true
    
    # Check if cache file exists and is recent (less than 10 minutes for K8s)
    if [ -f "$CACHE_FILE" ]; then
        local cache_age=$(($(date +%s) - $(stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0)))
        if [ $cache_age -gt 600 ]; then  # 10 minutes cache for K8s
            cache_valid=false
        fi
    else
        cache_valid=false
    fi
    
    # If cache is invalid, perform directory checks
    if [ "$cache_valid" = false ]; then
        local dir_check_failed=false
        
        # Check critical log directory only
        if [ ! -d "/var/log/cron-dispatcher" ]; then
            echo "[FAIL] Log directory does not exist" >&2
            dir_check_failed=true
        fi
        
        # Update cache file
        if [ "$dir_check_failed" = false ]; then
            echo "$(date): Directory checks passed" > "$CACHE_FILE" 2>/dev/null || true
        else
            return 1
        fi
    fi
    
    return 0
}

# Kubernetes liveness probe (minimal checks)
k8s_liveness() {
    # Only check critical components for liveness
    if ! check_crond; then
        exit 1
    fi
    
    if ! check_main_process; then
        exit 1
    fi
    
    exit 0
}

# Kubernetes readiness probe (more comprehensive)
k8s_readiness() {
    local exit_code=0
    
    # Check critical service
    if ! check_crond; then
        exit_code=1
    fi
    
    # Check main process
    if ! check_main_process; then
        exit_code=1
    fi
    
    # Check directories (cached)
    if ! check_directories_k8s; then
        exit_code=1
    fi
    
    exit $exit_code
}

# Verbose health check for manual use
verbose_check() {
    echo "=== CronDispatcher Health Check ==="
    
    local exit_code=0
    
    # Check crond service
    if systemctl is-active --quiet crond 2>/dev/null; then
        echo "[PASS] crond service is running"
    else
        echo "[FAIL] crond service is not running"
        exit_code=1
    fi
    
    # Check main process
    if pgrep -f "python.*main.py" > /dev/null 2>&1; then
        echo "[PASS] CronDispatcher main process is running"
    else
        echo "[WARN] CronDispatcher main process not found"
    fi
    
    # Check directories
    if [ -d "/var/log/cron-dispatcher" ]; then
        echo "[PASS] Log directory exists"
    else
        echo "[FAIL] Log directory does not exist"
        exit_code=1
    fi
    
    if [ -d "/etc/cron-dispatcher-config" ]; then
        echo "[PASS] Configuration directory exists"
    else
        echo "[WARN] Configuration directory does not exist"
    fi
    
    # Note: Pod definitions are now retrieved from ConfigMaps using ccictl
    echo "[INFO] Pod definitions retrieved from ConfigMaps using ccictl"
    
    echo "=================================="
    
    if [ $exit_code -eq 0 ]; then
        echo "[PASS] Health check passed"
    else
        echo "[FAIL] Health check failed"
    fi
    
    exit $exit_code
}

# Main function
main() {
    # Check command line arguments
    case "${1:-}" in
        --liveness|-l)
            k8s_liveness
            ;;
        --readiness|-r)
            k8s_readiness
            ;;
        --verbose|-v)
            verbose_check
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --liveness, -l     Kubernetes liveness probe (minimal checks)"
            echo "  --readiness, -r    Kubernetes readiness probe (comprehensive checks)"
            echo "  --verbose, -v      Verbose health check for manual use"
            echo "  --help, -h         Show this help message"
            echo ""
            echo "Default: Kubernetes liveness probe mode"
            exit 0
            ;;
        *)
            # Default to liveness probe for Kubernetes compatibility
            k8s_liveness
            ;;
    esac
}

# Run main function with all arguments
main "$@" 