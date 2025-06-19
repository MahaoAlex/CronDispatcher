#!/usr/bin/env python3
"""
Pod Cleaner - Responsible for garbage collection and cleanup of cron-dispatcher managed Pods
"""
import time
import subprocess
import json
from typing import Dict, List
from logger_config import setup_logger
from utils import (
    safe_yaml_load,
    execute_command_with_retry,
    get_ccictl_command
)

# Set up logger
logger = setup_logger('PodCleaner', '/var/log/cron-dispatcher/pod-cleaner.log')

class PodCleaner:
    """Pod Cleaner class for garbage collection"""
    
    def __init__(self, namespace: str, gc_dry_run: bool = False, gc_batch_size: int = 50):
        self.namespace = namespace
        self.gc_dry_run = gc_dry_run
        self.gc_batch_size = gc_batch_size
        
        logger.info(f"PodCleaner initialized for namespace: {self.namespace}, dry_run: {self.gc_dry_run}, batch_size: {self.gc_batch_size}")
        logger.info(f"Garbage Collection - Dry Run: {self.gc_dry_run}, Batch Size: {self.gc_batch_size}")
    
    def cleanup_pods(self, gc_policy: Dict) -> int:
        """Clean up expired Pods with garbage collection using ccictl"""
        try:
            logger.info(f"Starting cleanup with policy: {gc_policy}")
            
            # Get Pods managed by cron-dispatcher using ccictl
            cmd = get_ccictl_command("get pods -l app.kubernetes.io/managed-by=cron-dispatcher -o yaml", self.namespace)
            success, stdout, stderr = execute_command_with_retry(cmd, timeout=30, max_retries=3)
            
            if not success:
                logger.warning(f"Failed to get pods for garbage collection: {stderr}")
                return 0
            
            # Parse pod list
            try:
                pod_list = safe_yaml_load(stdout, "Pod list from ccictl")
                if not pod_list or 'items' not in pod_list:
                    logger.info("No pods found for garbage collection")
                    return 0
                
                pods = pod_list['items']
                logger.debug(f"Found {len(pods)} pods to process")
            except Exception as e:
                logger.error(f"Failed to parse pod list: {e}")
                return 0
            
            # Group by task name
            task_pods = self._group_pods_by_task(pods)
            logger.info(f"Grouped pods by task: {json.dumps({k: len(v['success']) + len(v['failed']) for k, v in task_pods.items()}, indent=2)}")
            
            # Clean up Pods for each task
            total_deleted = 0
            for task_name, pods_by_status in task_pods.items():
                logger.debug(f"Processing task: {task_name}")
                logger.debug(f"Success pods: {len(pods_by_status['success'])}, Failed pods: {len(pods_by_status['failed'])}")
                deleted_count = self._cleanup_task_pods(task_name, pods_by_status, gc_policy)
                total_deleted += deleted_count
                
            logger.info(f"Garbage collection completed. Total pods processed for deletion: {total_deleted}")
            return total_deleted
                
        except Exception as e:
            logger.error(f"Error occurred during garbage collection: {e}", exc_info=True)
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
                pod_name = pod.get('metadata', {}).get('name', '')
                logger.debug(f"Pod {pod_name} (task: {task_name}) has phase: {phase}")
                
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
        logger.debug(f"Retention policy for task {task_name}: {task_policy}")
        
        max_success = task_policy.get('success', 3)
        max_failed = task_policy.get('failure', 3)
        
        dry_run_prefix = "[DRY RUN] " if self.gc_dry_run else ""
        
        # Clean up successful Pods
        success_pods = sorted(
            pods_by_status['success'],
            key=lambda p: p.get('metadata', {}).get('creationTimestamp', ''),
            reverse=True
        )
        
        if len(success_pods) > max_success:
            pods_to_delete = success_pods[max_success:]
            logger.info(f"{dry_run_prefix}Task {task_name}: {len(pods_to_delete)} successful pods exceed retention limit of {max_success}")
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
            logger.info(f"{dry_run_prefix}Task {task_name}: {len(pods_to_delete)} failed pods exceed retention limit of {max_failed}")
            deleted_count += self._delete_pods_batch(
                pods_to_delete,
                f"Exceeds failed Pod retention limit ({max_failed}) for task {task_name}"
            )
        
        return deleted_count
    
    def _get_task_retention_policy(self, task_name: str, gc_policy: Dict) -> Dict:
        """Get retention policy for specific task"""
        logger.debug(f"Getting retention policy for task {task_name}")
        logger.debug(f"Available policies: {json.dumps(gc_policy, indent=2)}")
        
        # Check task-specific policies first
        for task_config in gc_policy.get('tasks', []):
            task_selector = task_config.get('taskSelector', {})
            if task_selector.get('cron-dispatcher.io/task-name') == task_name:
                policy = {
                    'success': task_config.get('success', 3),
                    'failure': task_config.get('failure', 3)
                }
                logger.debug(f"Found task-specific policy: {policy}")
                return policy
        
        # Fall back to global policy
        global_policy = gc_policy.get('global', {})
        policy = {
            'success': global_policy.get('success', 3),
            'failure': global_policy.get('failure', 3)
        }
        logger.debug(f"Using global policy: {policy}")
        return policy
    
    def _delete_pods_batch(self, pods_to_delete: List, reason: str) -> int:
        """Delete Pods in batches using ccictl"""
        deleted_count = 0
        
        # Process in batches
        for i in range(0, len(pods_to_delete), self.gc_batch_size):
            batch = pods_to_delete[i:i + self.gc_batch_size]
            logger.debug(f"Processing batch {i//self.gc_batch_size + 1} of {(len(pods_to_delete) + self.gc_batch_size - 1)//self.gc_batch_size}")
            
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
                logger.debug(f"Waiting 60 seconds before processing next batch")
                time.sleep(60)
        
        return deleted_count
    
    def _delete_pod(self, pod_name: str, pod_namespace: str, reason: str) -> bool:
        """Delete Pod using ccictl"""
        try:
            cmd = get_ccictl_command(f"delete pod {pod_name}", pod_namespace)
            success, stdout, stderr = execute_command_with_retry(cmd, timeout=30, max_retries=2)
            
            if success:
                logger.info(f"Deleted Pod {pod_name}: {reason}")
                return True
            else:
                logger.error(f"Failed to delete Pod {pod_name}: {stderr}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete Pod {pod_name}: {e}", exc_info=True)
            return False