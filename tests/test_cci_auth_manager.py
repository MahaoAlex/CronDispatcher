#!/usr/bin/env python3
"""
Unit tests for CCI Authentication Manager
"""

import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cci_auth_manager import CCIAuthManager

class TestCCIAuthManager(unittest.TestCase):
    """Test cases for CCI Authentication Manager"""

    def setUp(self):
        """Set up test fixtures"""
        self.auth_manager = CCIAuthManager()
        self.credentials = {
            'CCI_ACCESS_KEY': 'test_access_key',
            'CCI_SECRET_KEY': 'test_secret_key',
            'CCI_DOMAIN_NAME': 'test_domain_name',
            'CCI_PROJECT_NAME': 'test_project_name'
        }

    @patch.dict(os.environ, {})
    def test_load_credentials_success(self):
        """Test successful loading of credentials from environment variables"""
        os.environ.update(self.credentials)
        result = self.auth_manager.load_credentials_from_env()
        self.assertTrue(result)
        self.assertEqual(self.auth_manager.credentials['access_key'], 'test_access_key')

    @patch.dict(os.environ, {})
    def test_load_credentials_missing_required(self):
        """Test failure when required environment variables are missing"""
        os.environ['CCI_ACCESS_KEY'] = 'test_key'
        with patch('cci_auth_manager.logger') as mock_logger:
            result = self.auth_manager.load_credentials_from_env()
            self.assertFalse(result)
            mock_logger.error.assert_called_once()
            self.assertIn('CCI_SECRET_KEY', mock_logger.error.call_args[0][0])

    def test_configure_ccictl_no_credentials(self):
        """Test configuration failure when no credentials have been loaded"""
        with patch('cci_auth_manager.logger') as mock_logger:
            result = self.auth_manager.configure_ccictl()
            self.assertFalse(result)
            mock_logger.error.assert_called_with("No credentials loaded. Call load_credentials_from_env() first")

    @patch('cci_auth_manager.execute_command_with_retry')
    def test_configure_ccictl_success(self, mock_execute):
        """Test successful configuration of ccictl"""
        self.auth_manager.credentials = {
            'access_key': 'test_access_key',
            'secret_key': 'test_secret_key',
            'domain_name': 'test_domain_name',
        }
        mock_execute.return_value = (True, "Success", "")
        
        result = self.auth_manager.configure_ccictl(region="test-region")

        self.assertTrue(result)
        self.assertEqual(mock_execute.call_count, 4)

    @patch('cci_auth_manager.execute_command_with_retry')
    def test_configure_ccictl_command_failure(self, mock_execute):
        """Test configuration failure when a ccictl command fails"""
        self.auth_manager.credentials = {
            'access_key': 'test_access_key',
            'secret_key': 'test_secret_key',
            'domain_name': 'test_domain_name',
        }
        # Simulate failure on the second command
        mock_execute.side_effect = [(True, "Success", ""), (False, "", "Error")]

        with patch('cci_auth_manager.logger') as mock_logger:
            result = self.auth_manager.configure_ccictl(region="test-region")
            self.assertFalse(result)
            self.assertEqual(mock_execute.call_count, 2)
            mock_logger.error.assert_called_with("Failed to set-credentials: Error")

if __name__ == '__main__':
    unittest.main() 