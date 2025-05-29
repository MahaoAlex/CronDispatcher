#!/usr/bin/env python3
"""
Pod Creator - Called by cron jobs, responsible for creating specific Pod instances
"""

import os
import sys
import logging
import yaml
import uuid
import subprocess
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/cron-dispatcher/pod-creator.log')
    ]
)
logger = logging.getLogger('PodCreator')

class PodCreator:
    """Pod Creator class"""
    
    def __init__(self):
        self.namespace = os.getenv('NAMESPACE', 'default')
    
    def generate_pod_uuid(self) -> str:
        """Generate 9-digit UUID"""
        return str(uuid.uuid4()).replace('-', '')[:9]
    
    def create_pod(self, task_name: str, template_path: str) -> bool:
        """Create Pod"""
        try:
            # Check if template file exists
            if not os.path.exists(template_path):
                logger.error(f"Pod template file does not exist: {template_path}")
                return False
            
            # Read Pod template
            with open(template_path, 'r', encoding='utf-8') as f:
                pod_template = yaml.safe_load(f)
            
            # Generate unique identifier
            pod_uuid = self.generate_pod_uuid()
            pod_name = f"{task_name}-{pod_uuid}"
            
            # Set Pod name and namespace
            pod_template['metadata']['name'] = pod_name
            pod_template['metadata']['namespace'] = self.namespace
            
            # Add necessary labels
            if 'labels' not in pod_template['metadata']:
                pod_template['metadata']['labels'] = {}
            
            pod_template['metadata']['labels'].update({
                'app.kubernetes.io/managed-by': 'CronDispatcher',
                'cron-dispatcher.io/task-name': task_name,
                'cron-dispatcher.io/instance': pod_name,
                'cron-dispatcher.io/created-at': datetime.utcnow().strftime('%Y%m%d%H%M%S')
            })
            
            # Add annotations
            if 'annotations' not in pod_template['metadata']:
                pod_template['metadata']['annotations'] = {}
            
            pod_template['metadata']['annotations'].update({
                'cron-dispatcher.io/created-by': 'CronDispatcher',
                'cron-dispatcher.io/creation-time': datetime.utcnow().isoformat() + 'Z'
            })
            
            # Create temporary file
            temp_file = f"/tmp/pod-{pod_uuid}.yaml"
            with open(temp_file, 'w', encoding='utf-8') as f:
                yaml.dump(pod_template, f, default_flow_style=False)
            
            # Use ccictl to create Pod
            cmd = f"ccictl apply -f {temp_file}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            # Clean up temporary file
            try:
                os.remove(temp_file)
            except:
                pass
            
            if result.returncode == 0:
                logger.info(f"✅ Successfully created Pod: {pod_name} (Task: {task_name})")
                print(f"Pod created successfully: {pod_name}")
                return True
            else:
                logger.error(f"❌ Failed to create Pod: {result.stderr}")
                print(f"Pod creation failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error occurred while creating Pod: {e}")
            print(f"Error occurred while creating Pod: {e}")
            return False

def main():
    """Main function"""
    if len(sys.argv) != 3:
        print("Usage: python3 pod_creator.py <task_name> <template_path>")
        sys.exit(1)
    
    task_name = sys.argv[1]
    template_path = sys.argv[2]
    
    logger.info(f"Starting Pod creation - Task: {task_name}, Template: {template_path}")
    
    creator = PodCreator()
    success = creator.create_pod(task_name, template_path)
    
    if success:
        logger.info(f"Pod creation task completed - Task: {task_name}")
        sys.exit(0)
    else:
        logger.error(f"Pod creation task failed - Task: {task_name}")
        sys.exit(1)

if __name__ == '__main__':
    main() 