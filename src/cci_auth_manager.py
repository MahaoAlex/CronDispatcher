#!/usr/bin/env python3
"""
CCI Authentication Manager
Manages CCI credentials and configures ccictl authentication
"""

import os
import subprocess
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

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
            elif env_var != 'CCI_PROJECT_NAME':  # project_name is optional
                missing_vars.append(env_var)
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
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
            logger.error(f"Missing required credentials: {', '.join(missing_keys)}")
            return False
        
        try:
            return self._configure_ccictl_commands(region)
        except Exception as e:
            logger.error(f"Error configuring ccictl: {e}")
            return False
    
    def _configure_ccictl_commands(self, region: str) -> bool:
        """Execute ccictl configuration commands"""
        project_name = self.credentials.get('project_name', region)
        
        commands = [
            {
                'name': 'set-cluster',
                'cmd': [
                    'ccictl', 'config', 'set-cluster', 'cci-cluster',
                    f'--server=https://cci.{region}.myhuaweicloud.com'
                ]
            },
            {
                'name': 'set-credentials',
                'cmd': [
                    'ccictl', 'config', 'set-credentials', 'cci-user',
                    '--auth-provider=iam',
                    f'--auth-provider-arg=iam-endpoint=https://iam.{region}.myhuaweicloud.com',
                    '--auth-provider-arg=cache=true',
                    f'--auth-provider-arg=project-name={project_name}',
                    f'--auth-provider-arg=ak={self.credentials["access_key"]}',
                    f'--auth-provider-arg=sk={self.credentials["secret_key"]}',
                    f'--auth-provider-arg=domain-name={self.credentials["domain_name"]}'
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
    
    def _execute_command(self, cmd: list, operation: str) -> bool:
        """Execute a single ccictl command"""
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            logger.debug(f"CCI {operation}: {result.stdout.strip()}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to {operation}: {e.stderr}")
            return False
    
    def test_authentication(self) -> bool:
        """
        Test CCI authentication by listing namespaces
        
        Returns:
            bool: True if authentication successful, False otherwise
        """
        try:
            result = subprocess.run(
                ['ccictl', 'get', 'namespaces'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=30
            )
            logger.info("CCI authentication test successful")
            logger.debug(f"Available namespaces: {result.stdout.strip()}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"CCI authentication test failed: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            logger.error("CCI authentication test timed out")
            return False
        except Exception as e:
            logger.error(f"Error testing CCI authentication: {e}")
            return False
    
    def get_credentials_info(self) -> Dict[str, str]:
        """
        Get non-sensitive credentials information for logging
        
        Returns:
            Dict with non-sensitive credential info
        """
        if not self.credentials:
            return {}
        
        return {
            'domain_name': self.credentials.get('domain_name', 'Not set'),
            'project_name': self.credentials.get('project_name', 'Not set'),
            'has_access_key': bool(self.credentials.get('access_key')),
            'has_secret_key': bool(self.credentials.get('secret_key'))
        } 