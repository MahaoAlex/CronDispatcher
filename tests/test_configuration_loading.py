#!/usr/bin/env python3
"""
Unit tests for Configuration Loading functionality
Test Cases: TC-1.1, TC-1.2, TC-1.3, TC-1.4
"""

import unittest
import tempfile
import os
import sys
from unittest.mock import patch
import yaml

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main import CronDispatcher


class TestConfigurationLoading(unittest.TestCase):
    """Test cases for configuration loading functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.cron_dispatcher = CronDispatcher()
        
        # Sample valid task configuration
        self.valid_tasks_config = [
            {
                'name': 'test-task-1',
                'schedule': '*/5 * * * *',
                'podDefinitionConfigmap': 'test-pod-template-1',
                'state': 'on'
            },
            {
                'name': 'test-task-2',
                'schedule': '0 */1 * * *',
                'podDefinitionConfigmap': 'test-pod-template-2',
                'state': 'off'
            }
        ]
        
        self.valid_tasks_yaml = yaml.dump(self.valid_tasks_config)
    
    def test_tc_1_1_valid_task_configuration_loading(self):
        """
        TC-1.1: Valid Task Configuration Loading
        Objective: Verify successful loading of valid configuration
        Input: ConfigMap containing valid tasks.yaml
        Expected Result: Configuration loaded successfully, all tasks parsed correctly
        Priority: High
        """
        # Create temporary file with valid configuration
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_file:
            temp_file.write(self.valid_tasks_yaml)
            temp_file_path = temp_file.name
        
        try:
            # Update the tasks config file path
            self.cron_dispatcher.tasks_config_file = temp_file_path
            
            # Test loading configuration
            result = self.cron_dispatcher.load_tasks_config_from_file()
            
            # Assertions
            self.assertIsNotNone(result, "Configuration should be loaded successfully")
            self.assertEqual(len(result), 2, "Should parse 2 tasks")
            self.assertEqual(result[0]['name'], 'test-task-1', "First task name should match")
            self.assertEqual(result[1]['name'], 'test-task-2', "Second task name should match")
            self.assertEqual(result[0]['schedule'], '*/5 * * * *', "First task schedule should match")
            self.assertEqual(result[1]['state'], 'off', "Second task state should match")
            
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)
    
    def test_tc_1_2_invalid_yaml_configuration(self):
        """
        TC-1.2: Invalid YAML Configuration
        Objective: Verify handling of malformed YAML
        Input: ConfigMap with invalid YAML syntax
        Expected Result: Error logged, None returned
        Priority: High
        """
        # Create temporary file with invalid YAML
        invalid_yaml = """
        - name: test-task
          schedule: "*/5 * * * *"
          podDefinitionConfigmap: test-template
          state: on
        - name: invalid-task
          schedule: "0 0 * * *"
          podDefinitionConfigmap: test-template-2
          state: [unclosed list
        """
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_file:
            temp_file.write(invalid_yaml)
            temp_file_path = temp_file.name
        
        try:
            # Update the tasks config file path
            self.cron_dispatcher.tasks_config_file = temp_file_path
            
            # Mock logger to capture error logs
            with patch('utils.logger') as mock_logger:
                result = self.cron_dispatcher.load_tasks_config_from_file()
                
                # Assertions
                self.assertIsNone(result, "Should return None for invalid YAML")
                mock_logger.error.assert_called_once()
                
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)
    
    def test_tc_1_3_missing_configuration_file(self):
        """
        TC-1.3: Missing Configuration File
        Objective: Verify handling when configuration file doesn't exist
        Input: Non-existent configuration file path
        Expected Result: Warning logged, None returned
        Priority: Medium
        """
        # Set path to non-existent file
        self.cron_dispatcher.tasks_config_file = '/non/existent/path/tasks.yaml'
        
        # Mock logger to capture warning logs
        with patch('main.logger') as mock_logger:
            result = self.cron_dispatcher.load_tasks_config_from_file()
            
            # Assertions
            self.assertIsNone(result, "Should return None for missing file")
            mock_logger.warning.assert_called_once()
            # Check that the warning message contains expected text
            warning_call = mock_logger.warning.call_args[0][0]
            self.assertIn("not found", warning_call)
    
    def test_tc_1_4_empty_configuration_file(self):
        """
        TC-1.4: Empty Configuration File
        Objective: Verify handling of empty or whitespace-only configuration file
        Input: Empty configuration file
        Expected Result: Warning logged, None returned
        Priority: Medium
        """
        test_cases = [
            "",  # Completely empty
            "   ",  # Only spaces
            "\n\n\t\n",  # Only whitespace characters
            "# Only comments\n# No actual content"  # Only comments
        ]
        
        for i, empty_content in enumerate(test_cases):
            with self.subTest(f"Empty content case {i+1}"):
                # Create temporary file with empty/whitespace content
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_file:
                    temp_file.write(empty_content)
                    temp_file_path = temp_file.name
                
                try:
                    # Update the tasks config file path
                    self.cron_dispatcher.tasks_config_file = temp_file_path
                    
                    # Mock logger to capture warning logs
                    with patch('utils.logger') as mock_logger:
                        result = self.cron_dispatcher.load_tasks_config_from_file()
                        
                        # Assertions
                        self.assertIsNone(result, f"Should return None for empty content case {i+1}")
                        mock_logger.warning.assert_called()
                        
                finally:
                    # Clean up temporary file
                    os.unlink(temp_file_path)
    
    def test_configuration_loading_with_file_permissions_error(self):
        """
        Additional test: Verify handling of file permission errors
        """
        # Set path to a valid file (doesn't matter since we'll mock the open)
        self.cron_dispatcher.tasks_config_file = '/some/valid/path.yaml'
        
        # Mock logger to capture error logs and simulate permission error
        with patch('main.logger') as mock_logger, \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', side_effect=PermissionError("Permission denied")):
            result = self.cron_dispatcher.load_tasks_config_from_file()
            
            # Assertions
            self.assertIsNone(result, "Should return None for permission error")
            mock_logger.error.assert_called()
            
            # Verify the error message contains permission-related text
            error_call = mock_logger.error.call_args[0][0]
            self.assertIn("Failed to load task configuration", error_call)
    
    def test_configuration_loading_with_partial_valid_data(self):
        """
        Additional test: Verify handling of partially valid configuration
        """
        # Configuration with some valid and some incomplete tasks
        partial_config = [
            {
                'name': 'valid-task',
                'schedule': '*/5 * * * *',
                'podDefinitionConfigmap': 'test-pod-template',
                'state': 'on'
            },
            {
                'name': 'incomplete-task',
                'schedule': '0 0 * * *',
                # Missing podDefinitionConfigmap
                'state': 'on'
            }
        ]
        
        partial_yaml = yaml.dump(partial_config)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_file:
            temp_file.write(partial_yaml)
            temp_file_path = temp_file.name
        
        try:
            # Update the tasks config file path
            self.cron_dispatcher.tasks_config_file = temp_file_path
            
            # Test loading configuration
            result = self.cron_dispatcher.load_tasks_config_from_file()
            
            # Should still load the configuration, validation happens elsewhere
            self.assertIsNotNone(result, "Should load configuration even with incomplete tasks")
            self.assertEqual(len(result), 2, "Should load both tasks")
            
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)


if __name__ == '__main__':
    unittest.main() 