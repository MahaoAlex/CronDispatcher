#!/bin/bash
# cron-dispatcher container startup script

set -e

# Create log directory
mkdir -p /var/log/cron-dispatcher

# Set timezone
if [ -n "$CRON_TIMEZONE" ]; then
    echo "Setting timezone to: $CRON_TIMEZONE"
    ln -sf /usr/share/zoneinfo/$CRON_TIMEZONE /etc/localtime
    echo $CRON_TIMEZONE > /etc/timezone
fi

# Display configuration information
echo "=== cron-dispatcher Configuration ==="
echo "Namespace: ${NAMESPACE:-default}"
echo "Timezone: ${CRON_TIMEZONE:-UTC}"
echo "GC Dry Run: ${GC_DRY_RUN:-false}"
echo "GC Batch Size: ${GC_BATCH_SIZE:-50}"
echo "Configuration Directory: /etc/cron-dispatcher-config"
echo "GC Policy Directory: /etc/cron-dispatcher-gc-policy"
echo "Pod Definitions: Retrieved from ConfigMaps using ccictl"
echo "=================================="

# Start cron-dispatcher using process manager
echo "Starting cron-dispatcher with process manager..."
exec /app/scripts/process_manager.sh start