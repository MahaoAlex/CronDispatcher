#!/usr/bin/env python3
"""
cron-dispatcher - Kubernetes namespace-level cron job management platform
Declarative configuration mode driven by ConfigMap, implementing containerized orchestration and lifecycle management of scheduled tasks
"""

import os
import sys
import time
import logging
import yaml
import subprocess
from typing import Dict, List, Optional

from crontab import CronTab
from pod_cleaner import PodCleaner
from cci_auth_manager import CCIAuthManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/cron-dispatcher/dispatcher.log')
    ]
)
logger = logging.getLogger('cron-dispatcher')

class CronDispatcher:
    """CronDispatcher main class"""
    
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
    
    def load_config_from_file(self) -> Optional[List[Dict]]:
        """Load task configuration from mounted file"""
        try:
            if not os.path.exists(self.tasks_config_file):
                logger.warning(f"Task configuration file not found: {self.tasks_config_file}")
                return None
            
            with open(self.tasks_config_file, 'r', encoding='utf-8') as f:
                tasks = yaml.safe_load(f)
            
            if not tasks:
                logger.warning("No tasks found in configuration file")
                return None
            
            logger.info(f"Successfully loaded {len(tasks)} task configurations from {self.tasks_config_file}")
            return tasks
            
        except Exception as e:
            logger.error(f"Failed to load task configuration: {e}")
            return None
    
    def load_gc_policy(self) -> Dict:
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
                policy = yaml.safe_load(f)
            
            if policy:
                logger.info(f"Successfully loaded garbage collection policy from {self.gc_policy_file}")
                return policy
            
        except Exception as e:
            logger.warning(f"Failed to load garbage collection policy, using default: {e}")
        
        return default_policy
    
    def validate_cron_expression(self, cron_expr: str) -> bool:
        """Validate cron expression"""
        try:
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
            cmd = f"ccictl get configmap {configmap_name} -n {self.namespace}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.debug(f"ConfigMap {configmap_name} exists in namespace {self.namespace}")
                return True
            else:
                logger.warning(f"ConfigMap {configmap_name} not found in namespace {self.namespace}")
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
        command = f"python3 /app/src/pod_creator.py {name} {configmap_name}"
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
    
    def watch_config_changes(self) -> bool:
        """Check if configuration files have changed"""
        try:
            # Check task configuration file
            if os.path.exists(self.tasks_config_file):
                tasks_mtime = os.path.getmtime(self.tasks_config_file)
                if not hasattr(self, 'last_tasks_mtime') or tasks_mtime > self.last_tasks_mtime:
                    self.last_tasks_mtime = tasks_mtime
                    logger.info("Task configuration file changed, reloading...")
                    return True
            
            # Check GC policy file
            if os.path.exists(self.gc_policy_file):
                gc_mtime = os.path.getmtime(self.gc_policy_file)
                if not hasattr(self, 'last_gc_mtime') or gc_mtime > self.last_gc_mtime:
                    self.last_gc_mtime = gc_mtime
                    logger.info("Garbage collection policy file changed, reloading...")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking configuration file changes: {e}")
            return False
    
    def _parse_interval_to_seconds(self, interval_str: str) -> int:
        """Parse time interval string to seconds"""
        try:
            interval_str = interval_str.strip()
            
            # If it's just a number, treat as seconds
            if interval_str.isdigit():
                return int(interval_str)
            
            # Parse with unit
            if interval_str.endswith('s'):
                return int(interval_str[:-1])
            elif interval_str.endswith('m'):
                return int(interval_str[:-1]) * 60
            elif interval_str.endswith('h'):
                return int(interval_str[:-1]) * 3600
            elif interval_str.endswith('d'):
                return int(interval_str[:-1]) * 86400
            else:
                # Try to parse as number
                return int(interval_str)
                
        except (ValueError, TypeError):
            logger.warning(f"Invalid interval format: {interval_str}, using default 300 seconds")
            return 300
    
    def update_cleanup_interval(self, gc_policy: Dict):
        """Update cleanup interval from GC policy"""
        try:
            interval_str = gc_policy.get('cleanupInterval', '5m')
            new_interval = self._parse_interval_to_seconds(interval_str)
            
            # Apply safety limits
            new_interval = max(30, min(86400, new_interval))  # 30 seconds to 24 hours
            
            if new_interval != self.cleanup_interval_seconds:
                self.cleanup_interval_seconds = new_interval
                logger.info(f"Updated cleanup interval to {new_interval} seconds ({interval_str})")
                
        except Exception as e:
            logger.warning(f"Failed to update cleanup interval: {e}")
    
    def should_run_cleanup(self) -> bool:
        """Check if cleanup should run based on interval"""
        current_time = time.time()
        return (current_time - self.last_cleanup_time) >= self.cleanup_interval_seconds
    
    def run(self):
        """Main run loop"""
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
                if self.watch_config_changes():
                    self._load_and_apply_config()
                
                # Run cleanup based on interval
                if self.should_run_cleanup():
                    self._run_cleanup()
                
                time.sleep(30)  # Check every 30 seconds
                
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(30)
        
        logger.info("cron-dispatcher stopped")
    
    def _load_and_apply_config(self):
        """Load and apply configuration"""
        # Load task configuration
        tasks = self.load_config_from_file()
        if tasks:
            self.update_crontab(tasks)
        
        # Load GC policy
        gc_policy = self.load_gc_policy()
        self.update_cleanup_interval(gc_policy)
    
    def _run_cleanup(self):
        """Run garbage collection cleanup"""
        gc_policy = self.load_gc_policy()
        self.pod_cleaner.cleanup_pods(gc_policy)
        self.last_cleanup_time = time.time()

def main():
    """Main function"""
    dispatcher = CronDispatcher()
    dispatcher.run()

if __name__ == '__main__':
    main() 