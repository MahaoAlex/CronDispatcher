#!/usr/bin/env python3
"""
Pod Creator - Called by cron jobs, responsible for creating specific Pod instances
"""

import os
import sys
import yaml
import uuid
import subprocess
from datetime import datetime
from logger_config import setup_logger

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

            cmd = f"/usr/local/bin/ccictl get configmap {configmap_name} -n {self.namespace} -o yaml"
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            if result.returncode != 0:
                logger.error(f"Failed to retrieve ConfigMap {configmap_name}: {result.stderr}")
                return None
            
            # Parse ConfigMap YAML
            configmap_data = yaml.safe_load(result.stdout)
            if not configmap_data or 'data' not in configmap_data:
                logger.error(f"ConfigMap {configmap_name} has no data section")
                return None
            
            # Get Pod definition from ConfigMap data
            pod_yaml = configmap_data['data'].get('pod.yaml')
            if not pod_yaml:
                logger.error(f"ConfigMap {configmap_name} does not contain 'pod.yaml' key")
                return None 
            
            # Parse Pod definition
            pod_definition = yaml.safe_load(pod_yaml)
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
            with open(temp_file, 'w', encoding='utf-8') as f:
                yaml.dump(pod_template, f, default_flow_style=False)
            
            # Use ccictl to create Pod
            cmd = f"/usr/local/bin/ccictl apply -f {temp_file}"
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            # Clean up temporary file
            try:
                os.remove(temp_file)
            except:
                pass
            
            if result.returncode == 0:
                logger.info(f"Successfully created Pod: {pod_name} (Task: {task_name}, ConfigMap: {configmap_name})")
                print(f"Pod created successfully: {pod_name}")
                return True
            else:
                logger.error(f"Failed to create Pod: {result.stderr}")
                print(f"Pod creation failed: {result.stderr}")
                return False
                
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