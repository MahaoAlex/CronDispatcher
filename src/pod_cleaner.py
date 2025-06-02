#!/usr/bin/env python3
"""
Pod Cleaner - Responsible for garbage collection and cleanup of cron-dispatcher managed Pods
"""

import os
import time
import logging
import yaml
import subprocess
import json
from typing import Dict, List

# Configure logging
logger = logging.getLogger('PodCleaner')

class PodCleaner:
    """Pod Cleaner class for garbage collection"""
    
    def __init__(self, namespace: str, gc_dry_run: bool = False, gc_batch_size: int = 50):
        self.namespace = namespace
        self.gc_dry_run = gc_dry_run
        self.gc_batch_size = gc_batch_size
        
        logger.info(f"PodCleaner initialized - Namespace: {self.namespace}")
        logger.info(f"Garbage Collection - Dry Run: {self.gc_dry_run}, Batch Size: {self.gc_batch_size}")
    
    def cleanup_pods(self, gc_policy: Dict) -> int:
        """Clean up expired Pods with garbage collection using ccictl"""
        try:
            # Get Pods managed by cron-dispatcher using ccictl
            cmd = f"ccictl get pods -n {self.namespace} -l app.kubernetes.io/managed-by=cron-dispatcher -o yaml"
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            if result.returncode != 0:
                logger.warning("Failed to get pods for garbage collection")
                return 0
            
            # Parse pod list
            try:
                pod_list = yaml.safe_load(result.stdout)
                if not pod_list or 'items' not in pod_list:
                    logger.info("No pods found for garbage collection")
                    return 0
                
                pods = pod_list['items']
            except Exception as e:
                logger.error(f"Failed to parse pod list: {e}")
                return 0
            
            # Group by task name
            task_pods = self._group_pods_by_task(pods)
            
            # Clean up Pods for each task
            total_deleted = 0
            for task_name, pods_by_status in task_pods.items():
                deleted_count = self._cleanup_task_pods(task_name, pods_by_status, gc_policy)
                total_deleted += deleted_count
                
            logger.info(f"Garbage collection completed. Total pods processed for deletion: {total_deleted}")
            return total_deleted
                
        except Exception as e:
            logger.error(f"Error occurred during garbage collection: {e}")
            return 0
    
    def _group_pods_by_task(self, pods: List[Dict]) -> Dict[str, Dict[str, List]]:
        """Group pods by task name and status"""
        task_pods = {}
        
        for pod in pods:
            labels = pod.get('metadata', {}).get('labels', {})
            task_name = labels.get('cron-dispatcher.io/task-name')
            
            if task_name:
                if task_name not in task_pods:
                    task_pods[task_name] = {'success': [], 'failed': []}
                
                phase = pod.get('status', {}).get('phase', '')
                if phase == 'Succeeded':
                    task_pods[task_name]['success'].append(pod)
                elif phase == 'Failed':
                    task_pods[task_name]['failed'].append(pod)
        
        return task_pods
    
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
            key=lambda p: p.get('metadata', {}).get('creationTimestamp', ''),
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
            key=lambda p: p.get('metadata', {}).get('creationTimestamp', ''),
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
        """Delete Pods in batches using ccictl"""
        deleted_count = 0
        
        # Process in batches
        for i in range(0, len(pods_to_delete), self.gc_batch_size):
            batch = pods_to_delete[i:i + self.gc_batch_size]
            
            for pod in batch:
                pod_name = pod.get('metadata', {}).get('name', '')
                pod_namespace = pod.get('metadata', {}).get('namespace', self.namespace)
                
                if self.gc_dry_run:
                    logger.info(f"[DRY RUN] Would delete Pod {pod_name}: {reason}")
                    deleted_count += 1
                else:
                    if self._delete_pod(pod_name, pod_namespace, reason):
                        deleted_count += 1
            
            # Small delay between batches to avoid API server pressure
            if i + self.gc_batch_size < len(pods_to_delete):
                time.sleep(60)
        
        return deleted_count
    
    def _delete_pod(self, pod_name: str, pod_namespace: str, reason: str) -> bool:
        """Delete Pod using ccictl"""
        try:
            cmd = f"ccictl delete pod {pod_name} -n {pod_namespace}"
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            if result.returncode == 0:
                logger.info(f"Deleted Pod {pod_name}: {reason}")
                return True
            else:
                logger.error(f"Failed to delete Pod {pod_name}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete Pod {pod_name}: {e}")
            return False

    def get_pods_by_labels(self, label_selector: Dict) -> List[Dict]:
        """Get Pods by label selector"""
        try:
            # Build label selector string
            match_labels = label_selector.get('matchLabels', {})
            label_parts = [f"{key}={value}" for key, value in match_labels.items()]
            label_string = ','.join(label_parts)
            
            if not label_string:
                logger.warning("No label selector provided, skipping Pod query")
                return []
            
            # Use ccictl to get Pods
            cmd = f"ccictl get pods -n {self.namespace} -l {label_string} -o json"
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            if result.returncode != 0:
                logger.error(f"Failed to get Pods: {result.stderr}")
                return []
            
            # Parse JSON response
            pods_data = json.loads(result.stdout)
            pods = pods_data.get('items', [])
            
            logger.info(f"Found {len(pods)} Pods matching label selector in namespace {self.namespace}")
            return pods
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Pods JSON response: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting Pods by labels: {e}")
            return [] 