#!/usr/bin/env python3
"""
CCI Authentication Manager
Manages CCI credentials and configures ccictl authentication
"""

import os
import subprocess
from typing import Dict, List
from logger_config import setup_logger
from utils import execute_command_with_retry

# Set up logger
logger = setup_logger('CCIAuthManager', '/var/log/cron-dispatcher/cci-auth.log')

class CCIAuthManager:
    """Manages CCI authentication using environment variables and configures ccictl"""
    
    def __init__(self):
        """Initialize CCI Auth Manager"""
        self.credentials = {}
        logger.info("CCI Authentication Manager initialized")
    
    def load_credentials_from_env(self) -> bool:
        """
        Load CCI credentials from environment variables
        
        Returns:
            bool: True if credentials loaded successfully, False otherwise
        """
        env_mapping = {
            'access_key': 'CCI_ACCESS_KEY',
            'secret_key': 'CCI_SECRET_KEY', 
            'domain_name': 'CCI_DOMAIN_NAME',
            'project_name': 'CCI_PROJECT_NAME'
        }
        
        missing_vars = []
        for cred_key, env_var in env_mapping.items():
            value = os.getenv(env_var)
            if value:
                self.credentials[cred_key] = value
            elif env_var != 'CCI_PROJECT_NAME': 
                missing_vars.append(env_var)
        
        if missing_vars:
            logger.error("Missing required environment variables: {}".format(', '.join(missing_vars)))
            return False
        
        logger.info("Successfully loaded credentials from environment variables")
        return True
    
    def configure_ccictl(self, region: str = "af-south-1") -> bool:
        """
        Configure ccictl with loaded credentials
        
        Args:
            region: CCI region (default: af-south-1)
            
        Returns:
            bool: True if configuration successful, False otherwise
        """
        if not self.credentials:
            logger.error("No credentials loaded. Call load_credentials_from_env() first")
            return False
        
        required_keys = ['access_key', 'secret_key', 'domain_name']
        missing_keys = [key for key in required_keys if key not in self.credentials]
        if missing_keys:
            logger.error("Missing required credentials: {}".format(', '.join(missing_keys)))
            return False
        
        try:
            return self._configure_ccictl_commands(region)
        except Exception as e:
            logger.error("Error configuring ccictl: {}".format(e))
            return False
    
    def _configure_ccictl_commands(self, region: str) -> bool:
        """Execute ccictl configuration commands"""
        project_name = self.credentials.get('project_name', region)
        
        commands = [
            {
                'name': 'set-cluster',
                'cmd': [
                    'ccictl', 'config', 'set-cluster', 'cci-cluster',
                    '--server=https://cci.{}.myhuaweicloud.com'.format(region)
                ]
            },
            {
                'name': 'set-credentials',
                'cmd': [
                    'ccictl', 'config', 'set-credentials', 'cci-user',
                    '--auth-provider=iam',
                    '--auth-provider-arg=iam-endpoint=https://iam.{}.myhuaweicloud.com'.format(region),
                    '--auth-provider-arg=cache=true',
                    '--auth-provider-arg=project-name={}'.format(project_name),
                    '--auth-provider-arg=ak={}'.format(self.credentials["access_key"]),
                    '--auth-provider-arg=sk={}'.format(self.credentials["secret_key"]),
                    '--auth-provider-arg=domain-name={}'.format(self.credentials["domain_name"])
                ]
            },
            {
                'name': 'set-context',
                'cmd': [
                    'ccictl', 'config', 'set-context', 'cci-context',
                    '--cluster=cci-cluster',
                    '--user=cci-user'
                ]
            },
            {
                'name': 'use-context',
                'cmd': ['ccictl', 'config', 'use-context', 'cci-context']
            }
        ]
        
        for command in commands:
            if not self._execute_command(command['cmd'], command['name']):
                return False
        
        logger.info("Successfully configured ccictl authentication")
        return True
    
    def _execute_command(self, cmd: List[str], operation: str) -> bool:
        """Execute a single ccictl command"""
        try:
            cmd_str = ' '.join(cmd)
            success, stdout, stderr = execute_command_with_retry(cmd_str, timeout=30, max_retries=2, shell=False)
            
            if success:
                logger.debug("CCI {}: {}".format(operation, stdout.strip()))
                return True
            else:
                logger.error("Failed to {}: {}".format(operation, stderr))
                return False
        except Exception as e:
            logger.error("Error executing CCI command {}: {}".format(operation, e))
            return False
    