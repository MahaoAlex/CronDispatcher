#!/bin/bash
# CronDispatcher health check script

# Check crond service status
check_crond() {
    if systemctl is-active --quiet crond; then
        echo "[PASS] crond service is running"
        return 0
    else
        echo "[FAIL] crond service is not running"
        return 1
    fi
}

# Check HTTP health endpoint
check_http_endpoint() {
    if command -v curl >/dev/null 2>&1; then
        if curl -s -f http://localhost:8080/health > /dev/null; then
            echo "[PASS] HTTP health endpoint is responding"
            return 0
        else
            echo "[FAIL] HTTP health endpoint is not responding"
            return 1
        fi
    else
        echo "[WARN] curl not available, skipping HTTP endpoint check"
        return 0
    fi
}

# Check garbage collection configuration
check_gc_config() {
    echo "Garbage Collection Configuration:"
    echo "  - Dry Run Mode: ${GC_DRY_RUN:-false}"
    echo "  - Batch Size: ${GC_BATCH_SIZE:-50}"
    echo "  - Timezone: ${CRON_TIMEZONE:-Africa/Johannesburg}"
}

# Check crontab entries
check_crontab() {
    local cron_count=$(crontab -l 2>/dev/null | grep -c "CronDispatcher" || echo "0")
    echo "Active CronDispatcher tasks: $cron_count"
}

# Main health check
main() {
    echo "=== CronDispatcher Health Check ==="
    echo "Timestamp: $(date)"
    echo
    
    local exit_code=0
    
    # Check crond service
    if ! check_crond; then
        exit_code=1
    fi
    
    # Check HTTP endpoint
    if ! check_http_endpoint; then
        exit_code=1
    fi
    
    # Show configuration
    check_gc_config
    echo
    
    # Show crontab status
    check_crontab
    echo
    
    if [ $exit_code -eq 0 ]; then
        echo "[PASS] All health checks passed"
    else
        echo "[FAIL] Some health checks failed"
    fi
    
    exit $exit_code
}

main "$@" 