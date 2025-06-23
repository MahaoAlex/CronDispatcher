#!/bin/bash
# cron-dispatcher container startup script

set -e

# Logging function
log_info() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Entrypoint - INFO - $1"
}

# Create log directory
mkdir -p /var/log/cron-dispatcher
log_info "Log directory created at /var/log/cron-dispatcher"

# Set timezone
if [ -n "$CRON_TIMEZONE" ]; then
    log_info "Setting timezone to: $CRON_TIMEZONE"
    ln -sf /usr/share/zoneinfo/$CRON_TIMEZONE /etc/localtime
    echo $CRON_TIMEZONE > /etc/timezone
fi

# Display configuration information
log_info "=== cron-dispatcher Configuration ==="
log_info "Namespace: ${NAMESPACE:-default}"
log_info "Timezone: ${CRON_TIMEZONE:-UTC}"
log_info "GC Dry Run: ${GC_DRY_RUN:-false}"
log_info "GC Batch Size: ${GC_BATCH_SIZE:-50}"
log_info "Configuration Directory: /etc/cron-dispatcher-config"
log_info "GC Policy Directory: /etc/cron-dispatcher-gc-policy"
log_info "Pod Definitions: Retrieved from ConfigMaps using ccictl"
log_info "=================================="

# Start cron-dispatcher using process manager
log_info "Starting cron-dispatcher with process manager..."
exec /app/scripts/process_manager.sh start