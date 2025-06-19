#!/usr/bin/env python3
"""
Pod Creator - Called by cron jobs, responsible for creating specific Pod instances
"""

import os
import sys
import uuid
import subprocess
from datetime import datetime
from logger_config import setup_logger
from utils import (
    safe_yaml_load,
    safe_yaml_dump,
    execute_command_with_retry,
    get_ccictl_command,
    cleanup_temp_file
)

# Set up logger
logger = setup_logger('PodCreator', '/var/log/cron-dispatcher/pod-creator.log')

class PodCreator:
    """Pod Creator class"""
    
    def __init__(self):
        self.namespace = os.getenv('NAMESPACE', 'default')
    
    def generate_pod_uuid(self) -> str:
        """Generate 9-digit UUID"""
        return str(uuid.uuid4()).replace('-', '')[:9]
    
    def get_pod_definition_from_configmap(self, configmap_name: str) -> dict:
        """Retrieve Pod definition from ConfigMap using ccictl"""
        try:
            logger.info(f"Trying to retrieve Pod definition from ConfigMap {configmap_name} and namespace {self.namespace}")

            cmd = get_ccictl_command(f"get configmap {configmap_name} -o yaml", self.namespace)
            success, stdout, stderr = execute_command_with_retry(cmd, timeout=30, max_retries=3)
            
            if not success:
                logger.error(f"Failed to retrieve ConfigMap {configmap_name}: {stderr}")
                return None
            
            # Parse ConfigMap YAML
            configmap_data = safe_yaml_load(stdout, f"ConfigMap {configmap_name}")
            if not configmap_data or 'data' not in configmap_data:
                logger.error(f"ConfigMap {configmap_name} has no data section")
                return None
            
            # Get Pod definition from ConfigMap data
            pod_yaml = configmap_data['data'].get('pod.yaml')
            if not pod_yaml:
                logger.error(f"ConfigMap {configmap_name} does not contain 'pod.yaml' key")
                return None 
            
            # Parse Pod definition
            pod_definition = safe_yaml_load(pod_yaml, f"Pod definition from ConfigMap {configmap_name}")
            if not pod_definition:
                logger.error(f"Invalid Pod definition in ConfigMap {configmap_name}")
                return None
            
            logger.info(f"Successfully retrieved Pod definition from ConfigMap {configmap_name} and namespace {self.namespace}")
            return pod_definition
            
        except Exception as e:
            logger.error(f"Error retrieving Pod definition from ConfigMap {configmap_name}: {e}")
            return None
    
    def create_pod(self, task_name: str, configmap_name: str) -> bool:
        """Create Pod from ConfigMap definition"""
        try:
            # Get Pod definition from ConfigMap
            pod_template = self.get_pod_definition_from_configmap(configmap_name)
            if not pod_template:
                logger.error(f"Failed to retrieve Pod definition from ConfigMap: {configmap_name}")
                return False
            
            # Generate unique identifier
            pod_uuid = self.generate_pod_uuid()
            pod_name = f"{task_name}-{pod_uuid}"
            
            # Set Pod name and namespace
            if 'metadata' not in pod_template:
                pod_template['metadata'] = {}
            
            pod_template['metadata']['name'] = pod_name
            pod_template['metadata']['namespace'] = self.namespace
            
            # Add necessary labels
            if 'labels' not in pod_template['metadata']:
                pod_template['metadata']['labels'] = {}
            
            # Essential labels for cron-dispatcher
            pod_template['metadata']['labels'].update({
                'app.kubernetes.io/name': task_name,
                'app.kubernetes.io/managed-by': 'cron-dispatcher',
                'cron-dispatcher.io/task-name': task_name,
                'cron-dispatcher.io/instance': pod_name
            })
            
            # Add annotations
            if 'annotations' not in pod_template['metadata']:
                pod_template['metadata']['annotations'] = {}
            
            pod_template['metadata']['annotations'].update({
                'cron-dispatcher.io/created-by': 'cron-dispatcher',
                'cron-dispatcher.io/creation-time': datetime.utcnow().isoformat() + 'Z',
                'cron-dispatcher.io/source-configmap': configmap_name
            })
            
            # Create temporary file
            temp_file = f"/tmp/pod-{pod_uuid}.yaml"
            
            if not safe_yaml_dump(pod_template, temp_file):
                logger.error(f"Failed to create temporary Pod definition file: {temp_file}")
                return False
            
            try:
                # Use ccictl to create Pod
                cmd = get_ccictl_command(f"apply -f {temp_file}")
                success, stdout, stderr = execute_command_with_retry(cmd, timeout=60, max_retries=3)
                
                if success:
                    logger.info(f"Successfully created Pod: {pod_name} (Task: {task_name}, ConfigMap: {configmap_name})")
                    print(f"Pod created successfully: {pod_name}")
                    return True
                else:
                    logger.error(f"Failed to create Pod: {stderr}")
                    print(f"Pod creation failed: {stderr}")
                    return False
            finally:
                # Clean up temporary file
                cleanup_temp_file(temp_file)
                
        except Exception as e:
            logger.error(f"Error occurred while creating Pod: {e}")
            print(f"Error occurred while creating Pod: {e}")
            return False

def main():
    """Main function"""
    if len(sys.argv) != 3:
        print("Usage: python3 pod_creator.py <task_name> <configmap_name>")
        sys.exit(1)
    
    task_name = sys.argv[1]
    configmap_name = sys.argv[2]
    
    logger.info(f"Starting Pod creation - Task: {task_name}, ConfigMap: {configmap_name}")
    
    creator = PodCreator()
    success = creator.create_pod(task_name, configmap_name)
    
    if success:
        logger.info(f"Pod creation task completed - Task: {task_name}")
        sys.exit(0)
    else:
        logger.error(f"Pod creation task failed - Task: {task_name}")
        sys.exit(1)

if __name__ == '__main__':
    main() 