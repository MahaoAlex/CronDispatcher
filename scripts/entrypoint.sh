#!/bin/bash
set -e

echo "CronDispatcher container starting..."

# Create necessary directories
mkdir -p /var/log/cron-dispatcher
mkdir -p /etc/cron-templates
mkdir -p /tmp

# Set timezone
TIMEZONE=${CRON_TIMEZONE:-Africa/Johannesburg}
if [ -n "$CRON_TIMEZONE" ]; then
    echo "Setting timezone to: $CRON_TIMEZONE"
    if [ -f "/usr/share/zoneinfo/$CRON_TIMEZONE" ]; then
        ln -sf "/usr/share/zoneinfo/$CRON_TIMEZONE" /etc/localtime
        echo "$CRON_TIMEZONE" > /etc/timezone
    else
        echo "Warning: Timezone $CRON_TIMEZONE does not exist, using default Africa/Johannesburg timezone"
    fi
fi

# Set environment variables
export NAMESPACE=${NAMESPACE:-default}
export CRON_TIMEZONE=${CRON_TIMEZONE:-Africa/Johannesburg}

echo "Environment configuration:"
echo "  - Namespace: $NAMESPACE"
echo "  - Timezone: $CRON_TIMEZONE"

# Start crond service
echo "Starting crond service..."
systemctl enable crond
systemctl start crond

# Check crond service status
if systemctl is-active --quiet crond; then
    echo "[PASS] crond service started successfully"
else
    echo "[FAIL] crond service failed to start"
    exit 1
fi

# Start health check service (background)
echo "Starting health check service..."
python3 /app/src/main.py health &
HEALTH_PID=$!

# Wait for health check service to start
sleep 3

# Check if health check service is running normally
if kill -0 $HEALTH_PID 2>/dev/null; then
    echo "[PASS] Health check service started successfully (PID: $HEALTH_PID)"
else
    echo "[FAIL] Health check service failed to start"
    exit 1
fi

# Start main program
echo "Starting CronDispatcher main program..."
exec python3 /app/src/main.py 