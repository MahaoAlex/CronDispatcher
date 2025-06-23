#!/usr/bin/env python3
"""
Unit tests for ConfigMap Validation functionality
Test Cases: TC-3.1, TC-3.2, TC-3.3
"""

import unittest
import os
import sys
from unittest.mock import patch

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from main import CronDispatcher


class TestConfigMapValidation(unittest.TestCase):
    """Test cases for ConfigMap validation functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.cron_dispatcher = CronDispatcher()
    
    def test_tc_3_1_existing_configmap_validation(self):
        """
        TC-3.1: Existing ConfigMap Validation
        Objective: Verify detection of existing ConfigMaps
        Input: Existing ConfigMap name
        Expected Result: Validation passes, returns True
        Priority: High
        """
        # Mock successful ccictl command execution
        mock_stdout = """
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: test-configmap
          namespace: test-namespace
        data:
          config.yaml: |
            test: value
        """
        
        with patch('main.execute_command_with_retry') as mock_execute:
            mock_execute.return_value = (True, mock_stdout, "")
            
            # Test with existing ConfigMap
            result = self.cron_dispatcher.validate_configmap_exists("test-configmap")
            
            # Assertions
            self.assertTrue(result, "Should return True for existing ConfigMap")
            mock_execute.assert_called_once()
            
            # Verify the command was built correctly
            called_command = mock_execute.call_args[0][0]
            self.assertIn("get configmap test-configmap", called_command)
    
    def test_tc_3_2_non_existent_configmap_validation(self):
        """
        TC-3.2: Non-existent ConfigMap Validation
        Objective: Verify detection of missing ConfigMaps
        Input: Non-existent ConfigMap name
        Expected Result: Validation fails, warning logged
        Priority: High
        """
        # Mock failed ccictl command execution (ConfigMap not found)
        mock_stderr = "Error from server (NotFound): configmaps \"non-existent-configmap\" not found"
        
        with patch('main.execute_command_with_retry') as mock_execute:
            mock_execute.return_value = (False, "", mock_stderr)
            
            with patch('main.logger') as mock_logger:
                # Test with non-existent ConfigMap
                result = self.cron_dispatcher.validate_configmap_exists("non-existent-configmap")
                
                # Assertions
                self.assertFalse(result, "Should return False for non-existent ConfigMap")
                mock_logger.warning.assert_called()
                
                # Verify warning message contains relevant information
                warning_call = mock_logger.warning.call_args[0][0]
                self.assertIn("non-existent-configmap", warning_call)
    
    def test_tc_3_3_configmap_access_permissions(self):
        """
        TC-3.3: ConfigMap Access Permissions
        Objective: Verify handling of restricted access permissions
        Input: ConfigMap without read permissions
        Expected Result: Validation fails, appropriate error logged
        Priority: Medium
        """
        # Mock permission denied error
        mock_stderr = "Error from server (Forbidden): configmaps \"restricted-configmap\" is forbidden: User cannot get resource \"configmaps\" in API group \"\" in the namespace \"test\""
        
        with patch('main.execute_command_with_retry') as mock_execute:
            mock_execute.return_value = (False, "", mock_stderr)
            
            with patch('main.logger') as mock_logger:
                # Test with restricted ConfigMap
                result = self.cron_dispatcher.validate_configmap_exists("restricted-configmap")
                
                # Assertions
                self.assertFalse(result, "Should return False for restricted ConfigMap")
                mock_logger.warning.assert_called()
                
                # Verify error message contains permission-related information
                warning_call = mock_logger.warning.call_args[0][0]
                self.assertIn("restricted-configmap", warning_call)
    
    def test_configmap_validation_with_timeout_error(self):
        """
        Additional test: Verify handling of timeout errors
        """
        # Mock timeout error
        mock_stderr = "Error: command timed out"
        
        with patch('main.execute_command_with_retry') as mock_execute:
            mock_execute.return_value = (False, "", mock_stderr)
            
            with patch('main.logger') as mock_logger:
                result = self.cron_dispatcher.validate_configmap_exists("timeout-configmap")
                
                # Assertions
                self.assertFalse(result, "Should return False for timeout error")
                mock_logger.warning.assert_called()
    
    def test_configmap_validation_with_network_error(self):
        """
        Additional test: Verify handling of network connectivity issues
        """
        # Mock network error
        mock_stderr = "Unable to connect to the server: dial tcp: lookup kubernetes.default.svc on 8.8.8.8:53: no such host"
        
        with patch('main.execute_command_with_retry') as mock_execute:
            mock_execute.return_value = (False, "", mock_stderr)
            
            with patch('main.logger') as mock_logger:
                result = self.cron_dispatcher.validate_configmap_exists("network-error-configmap")
                
                # Assertions
                self.assertFalse(result, "Should return False for network error")
                mock_logger.warning.assert_called()
    
    def test_configmap_validation_with_invalid_namespace(self):
        """
        Additional test: Verify handling of invalid namespace
        """
        # Mock invalid namespace error
        mock_stderr = "Error from server (NotFound): namespaces \"invalid-namespace\" not found"
        
        with patch('main.execute_command_with_retry') as mock_execute:
            mock_execute.return_value = (False, "", mock_stderr)
            
            with patch('main.logger') as mock_logger:
                result = self.cron_dispatcher.validate_configmap_exists("test-configmap")
                
                # Assertions
                self.assertFalse(result, "Should return False for invalid namespace")
                mock_logger.warning.assert_called()
    
    def test_configmap_validation_with_malformed_response(self):
        """
        Additional test: Verify handling of malformed response from ccictl
        """
        # Mock malformed YAML response
        mock_stdout = "invalid yaml content: [unclosed bracket"
        
        with patch('main.execute_command_with_retry') as mock_execute:
            mock_execute.return_value = (True, mock_stdout, "")
            
            with patch('main.logger') as mock_logger:
                result = self.cron_dispatcher.validate_configmap_exists("malformed-response-configmap")
                
                # Should still return True since the command succeeded
                # The validation only checks if the command succeeds, not the content
                self.assertTrue(result, "Should return True when command succeeds regardless of content")
    
    def test_configmap_validation_command_construction(self):
        """
        Additional test: Verify correct command construction for different scenarios
        """
        test_cases = [
            ("simple-configmap", "default"),
            ("complex-configmap-name", "test-namespace"),
            ("configmap-with-123", "kube-system"),
        ]
        
        for configmap_name, namespace in test_cases:
            with self.subTest(configmap=configmap_name, namespace=namespace):
                # Set the namespace
                self.cron_dispatcher.namespace = namespace
                
                with patch('main.execute_command_with_retry') as mock_execute:
                    mock_execute.return_value = (True, "valid response", "")
                    
                    result = self.cron_dispatcher.validate_configmap_exists(configmap_name)
                    
                    # Verify command was constructed correctly
                    called_command = mock_execute.call_args[0][0]
                    self.assertIn(f"get configmap {configmap_name}", called_command)
                    self.assertIn(f"-n {namespace}", called_command)
                    self.assertTrue(result)
    
    def test_configmap_validation_empty_configmap_name(self):
        """
        Additional test: Verify handling of empty ConfigMap name
        """
        with patch('main.execute_command_with_retry') as mock_execute:
            mock_execute.return_value = (False, "", "Error: configmap name cannot be empty")
            
            with patch('main.logger') as mock_logger:
                result = self.cron_dispatcher.validate_configmap_exists("")
                
                # Assertions
                self.assertFalse(result, "Should return False for empty ConfigMap name")
                mock_logger.warning.assert_called()
    
    def test_configmap_validation_special_characters(self):
        """
        Additional test: Verify handling of ConfigMap names with special characters
        """
        special_names = [
            "configmap-with-dashes",
            "configmap.with.dots",
            "configmap_with_underscores",
            "configmap123with456numbers",
        ]
        
        for configmap_name in special_names:
            with self.subTest(configmap_name=configmap_name):
                with patch('main.execute_command_with_retry') as mock_execute:
                    mock_execute.return_value = (True, "valid response", "")
                    
                    result = self.cron_dispatcher.validate_configmap_exists(configmap_name)
                    
                    # Should handle special characters correctly
                    self.assertTrue(result, f"Should handle special characters in {configmap_name}")
                    
                    # Verify command was constructed correctly
                    called_command = mock_execute.call_args[0][0]
                    self.assertIn(f"get configmap {configmap_name}", called_command)
    
    def test_configmap_validation_retry_mechanism(self):
        """
        Additional test: Verify that execute_command_with_retry is called correctly
        """
        with patch('main.execute_command_with_retry') as mock_execute:
            mock_execute.return_value = (True, "success response", "")
            
            result = self.cron_dispatcher.validate_configmap_exists("retry-test-configmap")
            
            # Should succeed
            self.assertTrue(result, "Should succeed when execute_command_with_retry returns success")
            
            # Should have been called once
            mock_execute.assert_called_once()
            
            # Verify the command was constructed correctly
            called_command = mock_execute.call_args[0][0]
            self.assertIn("get configmap retry-test-configmap", called_command)


if __name__ == '__main__':
    unittest.main() 