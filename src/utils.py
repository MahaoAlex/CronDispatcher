#!/usr/bin/env python3
"""
Utility functions for cron-dispatcher
Common functions for subprocess calls, YAML parsing, retry mechanisms, etc.
"""

import os
import time
import yaml
import subprocess
from typing import Dict, Optional, Any, Tuple
from logger_config import setup_logger

logger = setup_logger('Utils', '/var/log/cron-dispatcher/utils.log')

def execute_command_with_retry(
    cmd: str, 
    timeout: int = 30, 
    max_retries: int = 3, 
    retry_delay: int = 1,
    shell: bool = True
) -> Tuple[bool, str, str]:
    """
    Execute command with retry mechanism and timeout
    
    Args:
        cmd: Command to execute
        timeout: Command timeout in seconds
        max_retries: Maximum number of retries
        retry_delay: Delay between retries in seconds
        shell: Whether to use shell
        
    Returns:
        Tuple of (success, stdout, stderr)
    """
    for attempt in range(max_retries + 1):
        try:
            logger.debug(f"Executing command (attempt {attempt + 1}): {cmd}")
            result = subprocess.run(
                cmd, 
                shell=shell, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                universal_newlines=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                logger.debug(f"Command executed successfully: {cmd}")
                return True, result.stdout, result.stderr
            else:
                logger.warning(f"Command failed (attempt {attempt + 1}): {cmd}, stderr: {result.stderr}")
                
        except Exception as e:
            logger.warning(f"Command execution error (attempt {attempt + 1}): {cmd}, error: {e}")
        
        # Wait before retry (except for the last attempt)
        if attempt < max_retries:
            logger.debug(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    
    logger.error(f"Command failed after {max_retries + 1} attempts: {cmd}")
    return False, "", f"Command failed after {max_retries + 1} attempts"

def safe_yaml_load(yaml_content: str, source_name: str = "unknown") -> Optional[Dict]:
    """
    Safely load YAML content with error handling
    
    Args:
        yaml_content: YAML content as string
        source_name: Source name for logging
        
    Returns:
        Parsed YAML data or None if failed
    """
    try:
        if not yaml_content or not yaml_content.strip():
            logger.warning(f"Empty YAML content from {source_name}")
            return None
            
        data = yaml.safe_load(yaml_content)
        logger.debug(f"Successfully parsed YAML from {source_name}")
        return data
        
    except Exception as e:
        logger.error(f"Error parsing YAML from {source_name}: {e}")
        return None

def safe_yaml_dump(data: Any, file_path: str) -> bool:
    """
    Safely dump data to YAML file
    
    Args:
        data: Data to dump
        file_path: Output file path
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, indent=2)
        
        logger.debug(f"Successfully wrote YAML to {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to write YAML to {file_path}: {e}")
        return False

def cleanup_temp_file(file_path: str) -> bool:
    """
    Safely cleanup temporary file
    
    Args:
        file_path: Path to temporary file
        
    Returns:
        True if successful or file doesn't exist, False if failed
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"Cleaned up temporary file: {file_path}")
        return True
    except Exception as e:
        logger.warning(f"Failed to cleanup temporary file {file_path}: {e}")
        return False

def get_ccictl_command(base_cmd: str, namespace: str = None) -> str:
    """
    Build ccictl command with proper path and namespace
    
    Args:
        base_cmd: Base ccictl command
        namespace: Kubernetes namespace
        
    Returns:
        Complete ccictl command
    """
    cmd = f"/usr/local/bin/ccictl {base_cmd}"
    if namespace:
        cmd += f" -n {namespace}"
    return cmd 