#!/usr/bin/env python3
"""
Unit tests for utility functions
"""

import unittest
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock
import yaml

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from utils import (
    execute_command_with_retry,
    safe_yaml_load,
    safe_yaml_dump,
    cleanup_temp_file,
    get_ccictl_command
)

class TestUtils(unittest.TestCase):
    """Test cases for utility functions"""

    @patch('utils.subprocess.run')
    def test_execute_command_success(self, mock_run):
        """Test successful command execution"""
        mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
        success, stdout, stderr = execute_command_with_retry("echo 'hello'")
        self.assertTrue(success)
        self.assertEqual(stdout, "Success")

    @patch('utils.subprocess.run')
    @patch('utils.time.sleep', return_value=None) # Mock sleep to speed up test
    def test_execute_command_retry_and_succeed(self, mock_sleep, mock_run):
        """Test command execution that fails then succeeds on retry"""
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="Fail 1"),
            MagicMock(returncode=0, stdout="Success", stderr="")
        ]
        success, stdout, stderr = execute_command_with_retry("echo 'retry'", max_retries=1)
        self.assertTrue(success)
        self.assertEqual(mock_run.call_count, 2)

    @patch('utils.subprocess.run')
    @patch('utils.time.sleep', return_value=None)
    def test_execute_command_failure(self, mock_sleep, mock_run):
        """Test command execution that fails after all retries"""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Final fail")
        success, stdout, stderr = execute_command_with_retry("echo 'fail'", max_retries=2)
        self.assertFalse(success)
        self.assertEqual(mock_run.call_count, 3)

    def test_safe_yaml_load(self):
        """Test YAML loading utility"""
        yaml_str = "key: value"
        data = safe_yaml_load(yaml_str)
        self.assertEqual(data, {'key': 'value'})

        # Test invalid YAML
        invalid_yaml = "key: value:"
        data = safe_yaml_load(invalid_yaml)
        self.assertIsNone(data)

        # Test empty YAML
        empty_yaml = ""
        data = safe_yaml_load(empty_yaml)
        self.assertIsNone(data)
        
    def test_safe_yaml_dump_and_cleanup(self):
        """Test YAML dumping and file cleanup"""
        data = {'key': 'value'}
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            file_path = tmp.name
        
        # Test dump
        result = safe_yaml_dump(data, file_path)
        self.assertTrue(result)
        with open(file_path, 'r') as f:
            read_data = yaml.safe_load(f)
        self.assertEqual(data, read_data)

        # Test cleanup
        self.assertTrue(os.path.exists(file_path))
        cleanup_temp_file(file_path)
        self.assertFalse(os.path.exists(file_path))

    def test_get_ccictl_command(self):
        """Test ccictl command builder"""
        base_cmd = "get pods"
        # Without namespace
        cmd = get_ccictl_command(base_cmd)
        self.assertEqual(cmd, f"/usr/local/bin/ccictl {base_cmd}")
        # With namespace
        cmd = get_ccictl_command(base_cmd, namespace="my-ns")
        self.assertEqual(cmd, f"/usr/local/bin/ccictl {base_cmd} -n my-ns")

if __name__ == '__main__':
    unittest.main() 