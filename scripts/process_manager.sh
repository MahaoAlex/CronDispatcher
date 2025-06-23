#!/bin/bash
# cron-dispatcher process manager for container environment
# This script manages crond and main application processes

set -e

# Logging function
log_info() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ProcessManager - INFO - $1"
}

# PID files
CROND_PID_FILE="/var/run/crond.pid"
MAIN_APP_PID_FILE="/var/run/cron-dispatcher.pid"

# Log files
CROND_LOG="/var/log/cron.log"
MAIN_APP_LOG="/var/log/cron-dispatcher/dispatcher.log"

# Create necessary directories
RUN mkdir -p /var/log/cron-dispatcher && \
    mkdir -p /etc/cron-dispatcher-config && \
    mkdir -p /etc/cron-dispatcher-gc-policy && \
    mkdir -p /var/run && \
    mkdir -p /var/spool/cron

# Function to start crond
start_crond() {
    log_info "Starting crond service..."
    
    # Ensure cron spool directory exists
    mkdir -p /var/spool/cron
    touch /var/spool/cron/root
    chmod 600 /var/spool/cron/root
    
    # Export environment variables to cron environment
    log_info "Exporting environment variables to /etc/cron.d/cron-env"
    {
        echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        echo "SHELL=/bin/bash"
        # Export all relevant environment variables
        env | grep -E '^(NAMESPACE|KUBERNETES|CCI)' | while read -r line; do
            echo "$line"
        done
    } > /etc/cron.d/cron-env
    
    # Create a wrapper script to source environment and run the command
    log_info "Creating cron job wrapper at /usr/local/bin/run_cron_job.sh"
    cat > /usr/local/bin/run_cron_job.sh << 'EOF'
#!/bin/bash
# Source environment variables
if [ -f /etc/cron.d/cron-env ]; then
    set -a
    source /etc/cron.d/cron-env
    set +a
fi
# Execute the command with all arguments
exec "$@"
EOF
    
    chmod +x /usr/local/bin/run_cron_job.sh
    
    # Start crond in background with basic options
    /usr/sbin/crond -n -s -m off &
    local crond_pid=$!
    
    # Wait a moment for crond to start
    sleep 2
    
    # Verify crond is running
    if kill -0 $crond_pid 2>/dev/null; then
        echo $crond_pid > $CROND_PID_FILE
        log_info "[PASS] crond started successfully (PID: $crond_pid)"
        # Display crond process details
        log_info "crond process details:"
        ps -f -p $crond_pid | while IFS= read -r line; do log_info "  $line"; done
        # Display cron jobs
        log_info "Current cron jobs:"
        crontab -l | while IFS= read -r line; do log_info "  $line"; done
        return 0
    else
        log_info "[FAIL] crond failed to start"
        return 1
    fi
}

# Function to start main application
start_main_app() {
    log_info "Starting cron-dispatcher main application..."
    
    # Ensure log directory exists
    mkdir -p /var/log/cron-dispatcher
    
    # Start main application in background
    python3 /app/src/main.py &
    local main_pid=$!
    
    # Wait a moment for application to start
    sleep 3
    
    # Verify main application is running
    if kill -0 $main_pid 2>/dev/null; then
        echo $main_pid > $MAIN_APP_PID_FILE
        log_info "[PASS] cron-dispatcher main application started successfully (PID: $main_pid)"
        return 0
    else
        log_info "[FAIL] cron-dispatcher main application failed to start"
        return 1
    fi
}

# Function to check if process is running
is_process_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

# Function to stop process
stop_process() {
    local pid_file=$1
    local process_name=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            log_info "Stopping $process_name (PID: $pid)..."
            kill -TERM "$pid"
            
            # Wait for graceful shutdown
            local count=0
            while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
                sleep 1
                count=$((count + 1))
            done
            
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                log_info "Force killing $process_name (PID: $pid)..."
                kill -KILL "$pid"
            fi
            
            rm -f "$pid_file"
            log_info "$process_name stopped"
        fi
    fi
}

# Function to restart process
restart_process() {
    local process_type=$1
    
    case $process_type in
        "crond")
            stop_process "$CROND_PID_FILE" "crond"
            start_crond
            ;;
        "main")
            stop_process "$MAIN_APP_PID_FILE" "main application"
            start_main_app
            ;;
        *)
            log_info "Unknown process type: $process_type"
            return 1
            ;;
    esac
}

# Function to monitor processes
monitor_processes() {
    while true; do
        # Check crond
        if ! is_process_running "$CROND_PID_FILE"; then
            log_info "[WARN] crond process not running, restarting..."
            restart_process "crond"
        fi
        
        # Check main application
        if ! is_process_running "$MAIN_APP_PID_FILE"; then
            log_info "[WARN] main application process not running, restarting..."
            restart_process "main"
        fi
        
        # Wait before next check
        sleep 30
    done
}

# Signal handlers
cleanup() {
    log_info "Received shutdown signal, cleaning up..."
    stop_process "$MAIN_APP_PID_FILE" "main application"
    stop_process "$CROND_PID_FILE" "crond"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Main execution
case "${1:-start}" in
    "start")
        log_info "=== cron-dispatcher Process Manager ==="
        
        # Start crond
        if ! start_crond; then
            exit 1
        fi
        
        # Start main application
        if ! start_main_app; then
            exit 1
        fi
        
        log_info "=== All processes started successfully ==="
        log_info "Monitoring processes..."
        
        # Monitor processes
        monitor_processes
        ;;
    "stop")
        stop_process "$MAIN_APP_PID_FILE" "main application"
        stop_process "$CROND_PID_FILE" "crond"
        ;;
    "restart")
        restart_process "crond"
        restart_process "main"
        ;;
    "status")
        log_info "=== Process Status ==="
        if is_process_running "$CROND_PID_FILE"; then
            local crond_pid=$(cat "$CROND_PID_FILE")
            log_info "[PASS] crond is running (PID: $crond_pid)"
        else
            log_info "[FAIL] crond is not running"
        fi
        
        if is_process_running "$MAIN_APP_PID_FILE"; then
            local main_pid=$(cat "$MAIN_APP_PID_FILE")
            log_info "[PASS] main application is running (PID: $main_pid)"
        else
            log_info "[FAIL] main application is not running"
        fi
        ;;
    *)
        log_info "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac 