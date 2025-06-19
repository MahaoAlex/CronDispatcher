#!/usr/bin/env python3
"""
cron-dispatcher - Kubernetes namespace-level cron job management platform
Declarative configuration mode driven by ConfigMap, implementing containerized orchestration and lifecycle management of scheduled tasks
"""

import os
import time
import subprocess
from typing import Dict, List, Optional
from crontab import CronTab
from pod_cleaner import PodCleaner
from cci_auth_manager import CCIAuthManager
from logger_config import setup_logger
from utils import (
    safe_yaml_load, 
    execute_command_with_retry,
    get_ccictl_command
)

# Set up logger
logger = setup_logger('CronDispatcher', '/var/log/cron-dispatcher/dispatcher.log')

class CronDispatcher:
    """CronDispatcher main class"""
    
    # Time interval constants
    MIN_INTERVAL_SECONDS = 30
    MAX_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours in seconds
    DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes in seconds
    
    # Time unit multipliers
    SECONDS_PER_MINUTE = 60
    SECONDS_PER_HOUR = 60 * 60
    SECONDS_PER_DAY = 24 * 60 * 60
    
    def __init__(self):
        self.namespace = os.getenv('NAMESPACE', 'default')
        self.timezone = os.getenv('CRON_TIMEZONE', 'UTC')
        self.region = os.getenv('CCI_REGION', 'af-south-1')
        
        # Configuration file paths (mounted from ConfigMaps)
        self.config_dir = '/etc/cron-dispatcher-config'
        self.gc_policy_dir = '/etc/cron-dispatcher-gc-policy'
        
        # Configuration files
        self.tasks_config_file = os.path.join(self.config_dir, 'tasks.yaml')
        self.gc_policy_file = os.path.join(self.gc_policy_dir, 'gc-policy.yaml')
        
        # Garbage Collection configuration
        self.gc_dry_run = os.getenv('GC_DRY_RUN', 'false').lower() == 'true'
        self.gc_batch_size = int(os.getenv('GC_BATCH_SIZE', '50'))
        
        # Cleanup timing
        self.last_cleanup_time = 0
        self.cleanup_interval_seconds = 300  # Default 5 minutes
        
        # Initialize crontab
        self.cron = CronTab(user='root')
        
        # Initialize Pod Cleaner
        self.pod_cleaner = PodCleaner(
            namespace=self.namespace,
            gc_dry_run=self.gc_dry_run,
            gc_batch_size=self.gc_batch_size
        )
        
        # Initialize CCI Authentication Manager
        self.cci_auth = self._initialize_cci_auth()
        
        logger.info(f"cron-dispatcher initialized - Namespace: {self.namespace}, Timezone: {self.timezone}")
        logger.info(f"Configuration directory: {self.config_dir}")
        logger.info(f"Garbage Collection - Dry Run: {self.gc_dry_run}, Batch Size: {self.gc_batch_size}")
        logger.info(f"CCI Region: {self.region}")
    
    def _initialize_cci_auth(self) -> Optional[CCIAuthManager]:
        """Initialize CCI Authentication Manager"""
        try:
            cci_auth = CCIAuthManager()
            logger.info("CCI Authentication Manager initialized")
            return cci_auth
        except Exception as e:
            logger.error(f"Failed to initialize CCI Authentication Manager: {e}")
            return None
    
    def load_tasks_config_from_file(self) -> Optional[List[Dict]]:
        """Load task configuration from mounted file"""
        try:
            if not os.path.exists(self.tasks_config_file):
                logger.warning(f"Task configuration file not found: {self.tasks_config_file}")
                return None
            
            with open(self.tasks_config_file, 'r', encoding='utf-8') as f:
                yaml_content = f.read()
            
            tasks = safe_yaml_load(yaml_content, f"tasks config file: {self.tasks_config_file}")
            
            if not tasks:
                logger.warning("No tasks found in configuration file")
                return None
            
            logger.info(f"Successfully loaded {len(tasks)} task configurations from {self.tasks_config_file}")
            return tasks
            
        except Exception as e:
            logger.error(f"Failed to load task configuration: {e}")
            return None
    
    def load_gc_policy_from_file(self) -> Dict:
        """Load garbage collection policy from mounted file"""
        default_policy = {
            'global': {
                'success': 3,
                'failure': 3
            },
            'tasks': [],
            'labelSelector': {
                'matchLabels': {
                    'app.kubernetes.io/managed-by': 'cron-dispatcher'
                }
            },
            'cleanupInterval': '5m',
        }
        
        try:
            if not os.path.exists(self.gc_policy_file):
                logger.info(f"Garbage collection policy file not found: {self.gc_policy_file}, using default policy")
                return default_policy
            
            with open(self.gc_policy_file, 'r', encoding='utf-8') as f:
                yaml_content = f.read()
            
            policy = safe_yaml_load(yaml_content, f"GC policy file: {self.gc_policy_file}")
            
            if policy:
                logger.info(f"Successfully loaded garbage collection policy from {self.gc_policy_file}")
                return policy
            
        except Exception as e:
            logger.warning(f"Failed to load garbage collection policy, using default: {e}")
        
        return default_policy

    def _load_and_apply_config(self):
        """Load and apply configuration"""
        # Load task configuration
        tasks = self.load_tasks_config_from_file()
        if tasks:
            self.update_crontab(tasks)
        
        # Load GC policy
        gc_policy = self.load_gc_policy_from_file()
        self.update_cleanup_interval(gc_policy)
    
    def watch_tasks_config_change(self) -> bool:
        """Check if the task configuration file has changed"""
        try:
            if os.path.exists(self.tasks_config_file):
                tasks_mtime = os.path.getmtime(self.tasks_config_file)
                if not hasattr(self, 'last_tasks_mtime') or tasks_mtime > self.last_tasks_mtime:
                    self.last_tasks_mtime = tasks_mtime
                    logger.info("Task configuration file changed, reloading...")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking task configuration file change: {e}")
            return False

    def watch_gc_policy_change(self) -> bool:
        """Check if the GC policy file has changed"""
        try:
            if os.path.exists(self.gc_policy_file):
                gc_mtime = os.path.getmtime(self.gc_policy_file)
                if not hasattr(self, 'last_gc_mtime') or gc_mtime > self.last_gc_mtime:
                    self.last_gc_mtime = gc_mtime
                    logger.info("Garbage collection policy file changed, reloading...")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking GC policy file change: {e}")
            return False

    def validate_cron_expression(self, cron_expr: str) -> bool:
        """Validate cron expression"""
        try:
            # Check for special strings that are not standard cron expressions
            special_strings = ['@yearly', '@annually', '@monthly', '@weekly', '@daily', '@midnight', '@hourly']
            if cron_expr in special_strings:
                logger.error(f"Special string '{cron_expr}' is not supported in standard cron format")
                return False
            
            # Convert Quartz format to standard cron format
            standard_expr = self._convert_quartz_to_cron(cron_expr)
            
            # Create a temporary cron job to validate the expression
            temp_cron = CronTab()
            temp_job = temp_cron.new(command='echo test')
            temp_job.setall(standard_expr)
            
            # If we get here without exception, the expression is valid
            return True
        except Exception as e:
            logger.error(f"Invalid cron expression '{cron_expr}': {e}")
            return False
    
    def _convert_quartz_to_cron(self, quartz_expr: str) -> str:
        """Convert Quartz format cron expression to standard format"""
        parts = quartz_expr.split()
        if len(parts) == 6:  # Quartz format: second minute hour day month week
            # Ignore seconds field, convert to standard 5-field format
            return f"{parts[1]} {parts[2]} {parts[3]} {parts[4]} {parts[5]}"
        return quartz_expr
    
    def validate_configmap_exists(self, configmap_name: str) -> bool:
        """Validate that the specified ConfigMap exists in the current namespace"""
        try:
            cmd = get_ccictl_command(f"get configmap {configmap_name}", self.namespace)
            success, stdout, stderr = execute_command_with_retry(cmd, timeout=10, max_retries=2)
            
            if success:
                logger.debug(f"ConfigMap {configmap_name} exists in namespace {self.namespace}")
                return True
            else:
                logger.warning(f"ConfigMap {configmap_name} not found in namespace {self.namespace}: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking ConfigMap {configmap_name}: {e}")
            return False
    
    def update_crontab(self, tasks: List[Dict]):
        """Update system crontab"""
        try:
            # Remove existing cron-dispatcher tasks
            self.cron.remove_all(comment='cron-dispatcher')
            
            active_tasks = 0
            for task in tasks:
                if self._process_task(task):
                    active_tasks += 1
            
            # Write crontab
            self.cron.write()
            logger.info(f"Crontab updated with {active_tasks} active tasks")
            
        except Exception as e:
            logger.error(f"Failed to update crontab: {e}")
    
    def _process_task(self, task: Dict) -> bool:
        """Process individual task and add to crontab if valid"""
        name = task.get('name')
        schedule = task.get('schedule')
        configmap_name = task.get('podDefinitionConfigmap')
        
        # Handle state field - convert boolean to string if necessary
        state_value = task.get('state', 'on')
        if isinstance(state_value, bool):
            # Convert boolean to string: True -> 'on', False -> 'off'
            state = 'on' if state_value else 'off'
        else:
            # Convert string to lowercase
            state = str(state_value).lower()
        
        # Skip disabled tasks
        if state != 'on':
            logger.info(f"Skipping disabled task: {name}")
            return False
        
        # Validate required fields
        if not all([name, schedule, configmap_name]):
            logger.warning(f"Incomplete task configuration, skipping: {name}")
            return False
        
        # Validate cron expression
        if not self.validate_cron_expression(schedule):
            logger.warning(f"Skipping task with invalid cron expression: {name}")
            return False
        
        # Validate ConfigMap exists
        if not self.validate_configmap_exists(configmap_name):
            logger.warning(f"Skipping task with non-existent ConfigMap: {name} -> {configmap_name}")
            return False
        
        # Convert cron expression and create job
        standard_cron = self._convert_quartz_to_cron(schedule)
        # Use wrapper script to ensure environment variables are available
        command = f"/usr/local/bin/run_cron_job.sh python3 /app/src/pod_creator.py {name} {configmap_name}"
        job = self.cron.new(command=command, comment='cron-dispatcher')
        job.setall(standard_cron)
        
        logger.info(f"Added cron job: {name} - {standard_cron} (ConfigMap: {configmap_name})")
        return True
    
    def initialize_cci_authentication(self) -> bool:
        """Initialize CCI authentication"""
        if not self.cci_auth:
            logger.warning("CCI Authentication Manager not available")
            return False
        
        try:
            if not self.cci_auth.load_credentials_from_env():
                logger.error("Failed to load CCI credentials from environment")
                return False
            
            if not self.cci_auth.configure_ccictl(region=self.region):
                logger.error("Failed to configure ccictl")
                return False
            
            logger.info("CCI authentication configured successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error during CCI authentication initialization: {e}")
            return False
    
    def _parse_interval_to_seconds(self, interval_str: str) -> int:
        """Parse human-readable interval string to seconds, with validation."""
        original_interval_str = str(interval_str).strip()
        if not original_interval_str:
            logger.warning(f"Empty interval string, using default {self.DEFAULT_INTERVAL_SECONDS} seconds")
            return self.DEFAULT_INTERVAL_SECONDS

        unit = original_interval_str[-1]
        value_str = original_interval_str[:-1]

        multipliers = {
            's': self.SECONDS_PER_MINUTE / 60,
            'm': self.SECONDS_PER_MINUTE,
            'h': self.SECONDS_PER_HOUR,
            'd': self.SECONDS_PER_DAY,
        }

        # If no unit, assume seconds
        if unit.isdigit():
            value_str = original_interval_str
            unit = 's'
        
        multiplier = multipliers.get(unit)

        try:
            if multiplier is None:
                raise ValueError(f"Invalid time unit '{unit}'")
            
            value = int(value_str)
            if value < 0:
                raise ValueError("Interval value cannot be negative")

            seconds = value * multiplier
            
            if seconds < self.MIN_INTERVAL_SECONDS:
                logger.warning(f"Interval '{original_interval_str}' is below minimum ({self.MIN_INTERVAL_SECONDS}s), clamping to minimum.")
                return self.MIN_INTERVAL_SECONDS
            
            if seconds > self.MAX_INTERVAL_SECONDS:
                logger.warning(f"Interval '{original_interval_str}' is above maximum ({self.MAX_INTERVAL_SECONDS}s), clamping to maximum.")
                return self.MAX_INTERVAL_SECONDS
            
            return int(seconds)

        except (ValueError, TypeError):
            logger.warning(f"Invalid interval format '{original_interval_str}', using default {self.DEFAULT_INTERVAL_SECONDS} seconds")
            return self.DEFAULT_INTERVAL_SECONDS
    
    def update_cleanup_interval(self, gc_policy: Dict):
        """Update cleanup interval from GC policy"""
        try:
            interval_str = gc_policy.get('cleanupInterval', '5m')
            new_interval = self._parse_interval_to_seconds(interval_str)
            # Apply safety limits using class constants
            new_interval = max(self.MIN_INTERVAL_SECONDS, min(self.MAX_INTERVAL_SECONDS, new_interval))
            if new_interval != self.cleanup_interval_seconds:
                self.cleanup_interval_seconds = new_interval
                logger.info(f"Updated cleanup interval to {new_interval} seconds ({interval_str})")
                self.last_cleanup_time = 0
        except Exception as e:
            logger.warning(f"Failed to update cleanup interval: {e}")
    
    def _run_cleanup(self):
        """Run garbage collection cleanup if interval has elapsed"""
        current_time = time.time()
        if (current_time - self.last_cleanup_time) >= self.cleanup_interval_seconds:
            gc_policy = self.load_gc_policy_from_file()
            self.pod_cleaner.cleanup_pods(gc_policy)
            self.last_cleanup_time = current_time

    def run(self):
        """Main run loop"""
        # Configuration check interval
        CONFIG_CHECK_INTERVAL_SECONDS = 30
        
        logger.info("cron-dispatcher starting...")
        
        # Initialize CCI authentication
        if not self.initialize_cci_authentication():
            logger.error("Failed to initialize CCI authentication, continuing without it...")
        
        # Initial configuration load
        self._load_and_apply_config()
        
        logger.info("cron-dispatcher started successfully")
        
        # Main monitoring loop
        while True:
            try:
                # Check for configuration changes every 30 seconds
                if self.watch_tasks_config_change():
                    # Load task configuration
                    tasks = self.load_tasks_config_from_file()
                    if tasks:
                        self.update_crontab(tasks)

                if self.watch_gc_policy_change():
                    # Load GC policy
                    gc_policy = self.load_gc_policy_from_file()
                    self.update_cleanup_interval(gc_policy)
                
                # Run cleanup if interval has elapsed
                self._run_cleanup()
                
                time.sleep(CONFIG_CHECK_INTERVAL_SECONDS)  # Check every 30 seconds
                
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(CONFIG_CHECK_INTERVAL_SECONDS)
        
        logger.info("cron-dispatcher stopped")

def main():
    """Main function"""
    dispatcher = CronDispatcher()
    dispatcher.run()

if __name__ == '__main__':
    main() 