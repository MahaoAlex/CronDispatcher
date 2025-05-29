#!/usr/bin/env python3
"""
CronDispatcher - Kubernetes namespace-level cron job management platform
Declarative configuration mode driven by ConfigMap, implementing containerized orchestration and lifecycle management of scheduled tasks
"""

import os
import sys
import time
import logging
import yaml
import uuid
import subprocess
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

import pytz
from kubernetes import client, config
from crontab import CronTab
from croniter import croniter
from flask import Flask, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/cron-dispatcher/dispatcher.log')
    ]
)
logger = logging.getLogger('CronDispatcher')

class CronDispatcher:
    """CronDispatcher main class"""
    
    def __init__(self):
        self.namespace = os.getenv('NAMESPACE', 'default')
        self.timezone = os.getenv('CRON_TIMEZONE', 'Africa/Johannesburg')
        self.config_map_name = 'cron-dispatcher-config'
        self.gc_policy_map_name = 'cron-dispatcher-gc-policy'
        
        # Garbage Collection configuration
        self.gc_dry_run = os.getenv('GC_DRY_RUN', 'false').lower() == 'true'
        self.gc_batch_size = int(os.getenv('GC_BATCH_SIZE', '50'))
        
        # Initialize Kubernetes client
        try:
            config.load_incluster_config()
        except:
            try:
                config.load_kube_config()
            except:
                logger.error("Unable to load Kubernetes configuration")
                sys.exit(1)
        
        self.k8s_client = client.CoreV1Api()
        self.cron = CronTab(user='root')
        
        # Set timezone
        self.tz = pytz.timezone(self.timezone)
        
        logger.info(f"CronDispatcher initialized - Namespace: {self.namespace}, Timezone: {self.timezone}")
        logger.info(f"Garbage Collection - Dry Run: {self.gc_dry_run}, Batch Size: {self.gc_batch_size}")
    
    def load_config_from_configmap(self) -> Optional[List[Dict]]:
        """Load task configuration from ConfigMap"""
        try:
            config_map = self.k8s_client.read_namespaced_config_map(
                name=self.config_map_name,
                namespace=self.namespace
            )
            
            tasks_yaml = config_map.data.get('tasks.yaml', '')
            if not tasks_yaml:
                logger.warning("tasks.yaml configuration not found in ConfigMap")
                return None
            
            tasks = yaml.safe_load(tasks_yaml)
            logger.info(f"Successfully loaded {len(tasks)} task configurations")
            return tasks
            
        except client.exceptions.ApiException as e:
            if e.status == 404:
                logger.warning(f"ConfigMap {self.config_map_name} does not exist")
            else:
                logger.error(f"Failed to read ConfigMap: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse task configuration: {e}")
            return None
    
    def load_gc_policy(self) -> Dict:
        """Load garbage collection policy"""
        default_policy = {
            'global': {
                'success': 3,
                'failure': 3
            },
            'tasks': [],
            'labelSelector': {
                'matchLabels': {
                    'app.kubernetes.io/managed-by': 'CronDispatcher'
                }
            },
            'cleanupInterval': '60m',
            'timeToLive': '1h'
        }
        
        try:
            config_map = self.k8s_client.read_namespaced_config_map(
                name=self.gc_policy_map_name,
                namespace=self.namespace
            )
            
            policy_yaml = config_map.data.get('gc-policy.yaml', '')
            if policy_yaml:
                policy = yaml.safe_load(policy_yaml)
                logger.info("Successfully loaded garbage collection policy")
                return policy
            
        except client.exceptions.ApiException as e:
            if e.status == 404:
                logger.info("Using default garbage collection policy")
            else:
                logger.warning(f"Failed to read garbage collection policy, using default: {e}")
        except Exception as e:
            logger.warning(f"Failed to parse garbage collection policy, using default: {e}")
        
        return default_policy
    
    def validate_cron_expression(self, cron_expr: str) -> bool:
        """Validate cron expression"""
        try:
            # Convert Quartz format to standard cron format
            parts = cron_expr.split()
            if len(parts) == 6:  # Quartz format: second minute hour day month week
                # Convert to standard format: minute hour day month week
                standard_expr = f"{parts[1]} {parts[2]} {parts[3]} {parts[4]} {parts[5]}"
            else:
                standard_expr = cron_expr
            
            croniter(standard_expr)
            return True
        except Exception as e:
            logger.error(f"Invalid cron expression '{cron_expr}': {e}")
            return False
    
    def convert_quartz_to_cron(self, quartz_expr: str) -> str:
        """Convert Quartz format cron expression to standard format"""
        parts = quartz_expr.split()
        if len(parts) == 6:  # Quartz format
            # Ignore seconds field, convert to standard 5-field format
            return f"{parts[1]} {parts[2]} {parts[3]} {parts[4]} {parts[5]}"
        return quartz_expr
    
    def generate_pod_uuid(self) -> str:
        """Generate 9-digit UUID"""
        return str(uuid.uuid4()).replace('-', '')[:9]
    
    def create_pod_from_template(self, task_name: str, template_path: str) -> bool:
        """Create Pod based on template"""
        try:
            # Read Pod template
            if not os.path.exists(template_path):
                logger.error(f"Pod template file does not exist: {template_path}")
                return False
            
            with open(template_path, 'r', encoding='utf-8') as f:
                pod_template = yaml.safe_load(f)
            
            # Generate unique identifier
            pod_uuid = self.generate_pod_uuid()
            pod_name = f"{task_name}-{pod_uuid}"
            
            # Set Pod name and labels
            pod_template['metadata']['name'] = pod_name
            pod_template['metadata']['namespace'] = self.namespace
            
            # Add necessary labels
            if 'labels' not in pod_template['metadata']:
                pod_template['metadata']['labels'] = {}
            
            pod_template['metadata']['labels'].update({
                'app.kubernetes.io/managed-by': 'CronDispatcher',
                'cron-dispatcher.io/task-name': task_name,
                'cron-dispatcher.io/instance': pod_name
            })
            
            # Use ccictl to create Pod
            temp_file = f"/tmp/pod-{pod_uuid}.yaml"
            with open(temp_file, 'w', encoding='utf-8') as f:
                yaml.dump(pod_template, f)
            
            # Execute ccictl command
            cmd = f"ccictl apply -f {temp_file}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            # Clean up temporary file
            os.remove(temp_file)
            
            if result.returncode == 0:
                logger.info(f"Successfully created Pod: {pod_name}")
                return True
            else:
                logger.error(f"Failed to create Pod: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error occurred while creating Pod: {e}")
            return False
    
    def update_crontab(self, tasks: List[Dict]):
        """Update system crontab"""
        try:
            # Remove existing CronDispatcher tasks
            self.cron.remove_all(comment='CronDispatcher')
            
            for task in tasks:
                name = task.get('name')
                schedule = task.get('schedule')
                template_path = task.get('podTemplatePath')
                state = task.get('state', 'on').lower()
                
                # Skip disabled tasks
                if state != 'on':
                    logger.info(f"Skipping disabled task: {name}")
                    continue
                
                # Validate required fields
                if not all([name, schedule, template_path]):
                    logger.warning(f"Incomplete task configuration, skipping: {name}")
                    continue
                
                # Validate cron expression
                if not self.validate_cron_expression(schedule):
                    logger.warning(f"Skipping task with invalid cron expression: {name}")
                    continue
                
                # Convert cron expression
                standard_cron = self.convert_quartz_to_cron(schedule)
                
                # Create cron job
                command = f"python3 /app/src/pod_creator.py {name} {template_path}"
                job = self.cron.new(command=command, comment='CronDispatcher')
                job.setall(standard_cron)
                
                logger.info(f"Added cron job: {name} - {standard_cron}")
            
            # Write to crontab
            self.cron.write()
            logger.info("Crontab update completed")
            
        except Exception as e:
            logger.error(f"Failed to update crontab: {e}")
    
    def cleanup_pods(self):
        """Clean up expired Pods with garbage collection"""
        try:
            gc_policy = self.load_gc_policy()
            
            # Get Pods managed by CronDispatcher
            label_selector = 'app.kubernetes.io/managed-by=CronDispatcher'
            pods = self.k8s_client.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=label_selector
            )
            
            # Group by task name
            task_pods = {}
            for pod in pods.items:
                task_name = pod.metadata.labels.get('cron-dispatcher.io/task-name')
                if task_name:
                    if task_name not in task_pods:
                        task_pods[task_name] = {'success': [], 'failed': []}
                    
                    if pod.status.phase == 'Succeeded':
                        task_pods[task_name]['success'].append(pod)
                    elif pod.status.phase == 'Failed':
                        task_pods[task_name]['failed'].append(pod)
            
            # Clean up Pods for each task
            total_deleted = 0
            for task_name, pods_by_status in task_pods.items():
                deleted_count = self._cleanup_task_pods(task_name, pods_by_status, gc_policy)
                total_deleted += deleted_count
                
            logger.info(f"Garbage collection completed. Total pods processed for deletion: {total_deleted}")
                
        except Exception as e:
            logger.error(f"Error occurred during garbage collection: {e}")
    
    def _cleanup_task_pods(self, task_name: str, pods_by_status: Dict, gc_policy: Dict) -> int:
        """Clean up Pods for specific task"""
        deleted_count = 0
        
        # Get retention policy for this task
        task_policy = self._get_task_retention_policy(task_name, gc_policy)
        
        max_success = task_policy.get('success', 3)
        max_failed = task_policy.get('failure', 3)
        
        # Clean up successful Pods
        success_pods = sorted(
            pods_by_status['success'],
            key=lambda p: p.metadata.creation_timestamp,
            reverse=True
        )
        
        if len(success_pods) > max_success:
            pods_to_delete = success_pods[max_success:]
            deleted_count += self._delete_pods_batch(
                pods_to_delete, 
                f"Exceeds successful Pod retention limit ({max_success}) for task {task_name}"
            )
        
        # Clean up failed Pods
        failed_pods = sorted(
            pods_by_status['failed'],
            key=lambda p: p.metadata.creation_timestamp,
            reverse=True
        )
        
        if len(failed_pods) > max_failed:
            pods_to_delete = failed_pods[max_failed:]
            deleted_count += self._delete_pods_batch(
                pods_to_delete,
                f"Exceeds failed Pod retention limit ({max_failed}) for task {task_name}"
            )
        
        return deleted_count
    
    def _get_task_retention_policy(self, task_name: str, gc_policy: Dict) -> Dict:
        """Get retention policy for specific task"""
        # Check task-specific policies first
        for task_config in gc_policy.get('tasks', []):
            task_selector = task_config.get('taskSelector', {})
            if task_selector.get('cron-dispatcher.io/task-name') == task_name:
                return {
                    'success': task_config.get('success', 3),
                    'failure': task_config.get('failure', 3)
                }
        
        # Fall back to global policy
        global_policy = gc_policy.get('global', {})
        return {
            'success': global_policy.get('success', 3),
            'failure': global_policy.get('failure', 3)
        }
    
    def _delete_pods_batch(self, pods_to_delete: List, reason: str) -> int:
        """Delete Pods in batches"""
        deleted_count = 0
        
        # Process in batches
        for i in range(0, len(pods_to_delete), self.gc_batch_size):
            batch = pods_to_delete[i:i + self.gc_batch_size]
            
            for pod in batch:
                if self.gc_dry_run:
                    logger.info(f"[DRY RUN] Would delete Pod {pod.metadata.name}: {reason}")
                    deleted_count += 1
                else:
                    if self._delete_pod(pod, reason):
                        deleted_count += 1
            
            # Small delay between batches to avoid API server pressure
            if i + self.gc_batch_size < len(pods_to_delete):
                time.sleep(1)
        
        return deleted_count
    
    def _delete_pod(self, pod, reason: str) -> bool:
        """Delete Pod"""
        try:
            self.k8s_client.delete_namespaced_pod(
                name=pod.metadata.name,
                namespace=pod.metadata.namespace
            )
            logger.info(f"Deleted Pod {pod.metadata.name}: {reason}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete Pod {pod.metadata.name}: {e}")
            return False
    
    def run(self):
        """Main run loop"""
        logger.info("CronDispatcher started")
        
        while True:
            try:
                # Load task configuration
                tasks = self.load_config_from_configmap()
                if tasks:
                    # Update crontab
                    self.update_crontab(tasks)
                
                # Execute garbage collection
                self.cleanup_pods()
                
                # Wait for next check (check configuration changes every 5 minutes)
                time.sleep(300)
                
            except KeyboardInterrupt:
                logger.info("Received stop signal, shutting down...")
                break
            except Exception as e:
                logger.error(f"Runtime error occurred: {e}")
                time.sleep(60)  # Wait 1 minute before retry on error

# Health check service
app = Flask(__name__)

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        # Check crond service status
        result = subprocess.run(['systemctl', 'is-active', 'crond'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout.strip() == 'active':
            return jsonify({'status': 'healthy', 'crond': 'active'}), 200
        else:
            return jsonify({'status': 'unhealthy', 'crond': 'inactive'}), 503
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def main():
    """Main function"""
    if len(sys.argv) > 1 and sys.argv[1] == 'health':
        # Health check mode
        app.run(host='0.0.0.0', port=8080)
    else:
        # Normal run mode
        dispatcher = CronDispatcher()
        dispatcher.run()

if __name__ == '__main__':
    main() 