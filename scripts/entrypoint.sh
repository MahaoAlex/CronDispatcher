#!/bin/bash
# CronDispatcher container startup script

set -e

# Create log directory
mkdir -p /var/log/cron-dispatcher

# Set timezone
if [ -n "$CRON_TIMEZONE" ]; then
    echo "Setting timezone to: $CRON_TIMEZONE"
    ln -sf /usr/share/zoneinfo/$CRON_TIMEZONE /etc/localtime
    echo $CRON_TIMEZONE > /etc/timezone
fi

# Initialize crontab
echo "Initializing crontab..."
touch /var/spool/cron/root
chmod 600 /var/spool/cron/root

# Start crond service
echo "Starting crond service..."
systemctl start crond
systemctl enable crond

# Check if crond service is running
if systemctl is-active --quiet crond; then
    echo "[PASS] crond service started successfully"
else
    echo "[FAIL] crond service failed to start"
    exit 1
fi

# Display configuration information
echo "=== CronDispatcher Configuration ==="
echo "Namespace: ${NAMESPACE:-default}"
echo "Timezone: ${CRON_TIMEZONE:-UTC}"
echo "GC Dry Run: ${GC_DRY_RUN:-false}"
echo "GC Batch Size: ${GC_BATCH_SIZE:-50}"
echo "Configuration Directory: /etc/cron-dispatcher-config"
echo "GC Policy Directory: /etc/cron-dispatcher-gc-policy"
echo "Pod Definitions: Retrieved from ConfigMaps using ccictl"
echo "=================================="

# Start main CronDispatcher application
echo "Starting CronDispatcher main application..."
exec python3 /app/src/main.py 