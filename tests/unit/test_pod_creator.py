#!/usr/bin/env python3
"""
Unit tests for Pod Creator functionality
"""

import unittest
import os
import sys
from unittest.mock import patch, MagicMock
import yaml

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from pod_creator import PodCreator

class TestPodCreator(unittest.TestCase):
    """Test cases for Pod Creator functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.pod_creator = PodCreator()
        self.task_name = "test-task"
        self.configmap_name = "test-pod-configmap"
        self.pod_definition = {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {'name': 'test-pod'},
            'spec': {
                'containers': [{
                    'name': 'nginx',
                    'image': 'nginx:latest'
                }]
            }
        }
        self.configmap_data = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {'name': self.configmap_name},
            'data': {
                'pod.yaml': yaml.dump(self.pod_definition)
            }
        }

    @patch('pod_creator.execute_command_with_retry')
    def test_get_pod_definition_success(self, mock_execute):
        """Test successful retrieval of Pod definition from ConfigMap"""
        mock_execute.return_value = (True, yaml.dump(self.configmap_data), "")
        
        pod_def = self.pod_creator.get_pod_definition_from_configmap(self.configmap_name)
        
        self.assertIsNotNone(pod_def)
        self.assertEqual(pod_def['kind'], 'Pod')
        mock_execute.assert_called_once()
        called_command = mock_execute.call_args[0][0]
        self.assertIn(f"get configmap {self.configmap_name} -o yaml", called_command)

    @patch('pod_creator.execute_command_with_retry')
    def test_get_pod_definition_cm_not_found(self, mock_execute):
        """Test failure when ConfigMap is not found"""
        mock_execute.return_value = (False, "", "Error: ConfigMap not found")
        
        pod_def = self.pod_creator.get_pod_definition_from_configmap(self.configmap_name)
        
        self.assertIsNone(pod_def)

    @patch('pod_creator.execute_command_with_retry')
    def test_get_pod_definition_no_data(self, mock_execute):
        """Test failure when ConfigMap has no data section"""
        invalid_cm = {'apiVersion': 'v1', 'kind': 'ConfigMap'}
        mock_execute.return_value = (True, yaml.dump(invalid_cm), "")
        
        pod_def = self.pod_creator.get_pod_definition_from_configmap(self.configmap_name)
        
        self.assertIsNone(pod_def)

    @patch('pod_creator.execute_command_with_retry')
    def test_get_pod_definition_no_pod_yaml(self, mock_execute):
        """Test failure when ConfigMap data does not contain pod.yaml"""
        invalid_cm = {'data': {'other.yaml': ''}}
        mock_execute.return_value = (True, yaml.dump(invalid_cm), "")
        
        pod_def = self.pod_creator.get_pod_definition_from_configmap(self.configmap_name)
        
        self.assertIsNone(pod_def)

    @patch('pod_creator.safe_yaml_dump')
    @patch('pod_creator.cleanup_temp_file')
    @patch('pod_creator.execute_command_with_retry')
    @patch.object(PodCreator, 'get_pod_definition_from_configmap')
    def test_create_pod_success(self, mock_get_def, mock_execute, mock_cleanup, mock_dump):
        """Test successful Pod creation"""
        mock_get_def.return_value = self.pod_definition
        mock_execute.return_value = (True, "pod/test-task-abcdef123 created", "")
        mock_dump.return_value = True

        result = self.pod_creator.create_pod(self.task_name, self.configmap_name)

        self.assertTrue(result)
        mock_get_def.assert_called_once_with(self.configmap_name)
        mock_dump.assert_called_once()
        mock_execute.assert_called_once()
        mock_cleanup.assert_called_once()
        
        # Check that metadata is correctly added
        pod_template_arg = mock_dump.call_args[0][0]
        self.assertIn('app.kubernetes.io/managed-by', pod_template_arg['metadata']['labels'])
        self.assertEqual(pod_template_arg['metadata']['labels']['cron-dispatcher.io/task-name'], self.task_name)
        self.assertIn('cron-dispatcher.io/creation-time', pod_template_arg['metadata']['annotations'])


    @patch.object(PodCreator, 'get_pod_definition_from_configmap')
    def test_create_pod_fail_get_definition(self, mock_get_def):
        """Test Pod creation failure when getting definition fails"""
        mock_get_def.return_value = None
        
        result = self.pod_creator.create_pod(self.task_name, self.configmap_name)

        self.assertFalse(result)

    @patch('pod_creator.safe_yaml_dump')
    @patch.object(PodCreator, 'get_pod_definition_from_configmap')
    def test_create_pod_fail_dump_yaml(self, mock_get_def, mock_dump):
        """Test Pod creation failure when writing to temp file fails"""
        mock_get_def.return_value = self.pod_definition
        mock_dump.return_value = False

        result = self.pod_creator.create_pod(self.task_name, self.configmap_name)

        self.assertFalse(result)
        
    @patch('pod_creator.safe_yaml_dump')
    @patch('pod_creator.cleanup_temp_file')
    @patch('pod_creator.execute_command_with_retry')
    @patch.object(PodCreator, 'get_pod_definition_from_configmap')
    def test_create_pod_fail_apply(self, mock_get_def, mock_execute, mock_cleanup, mock_dump):
        """Test Pod creation failure when ccictl apply fails"""
        mock_get_def.return_value = self.pod_definition
        mock_dump.return_value = True
        mock_execute.return_value = (False, "", "Error: failed to apply")

        result = self.pod_creator.create_pod(self.task_name, self.configmap_name)

        self.assertFalse(result)
        mock_cleanup.assert_called_once() # Ensure cleanup is called even on failure
        
    @patch('pod_creator.sys')
    def test_main_function_success(self, mock_sys):
        """Test main function with correct arguments"""
        mock_sys.argv = ['pod_creator.py', self.task_name, self.configmap_name]
        mock_sys.exit.side_effect = lambda code: __import__('sys').exit(code)
        with patch.object(PodCreator, 'create_pod', return_value=True) as mock_create_pod:
            from pod_creator import main
            with self.assertRaises(SystemExit) as e:
                main()
            self.assertEqual(e.exception.args[0], 0)
            mock_create_pod.assert_called_once_with(self.task_name, self.configmap_name)
            mock_sys.exit.assert_called_once_with(0)

    @patch('pod_creator.sys')
    def test_main_function_failure(self, mock_sys):
        """Test main function with correct arguments when pod creation fails"""
        mock_sys.argv = ['pod_creator.py', self.task_name, self.configmap_name]
        mock_sys.exit.side_effect = lambda code: __import__('sys').exit(code)
        with patch.object(PodCreator, 'create_pod', return_value=False) as mock_create_pod:
            from pod_creator import main
            with self.assertRaises(SystemExit) as e:
                main()
            self.assertEqual(e.exception.args[0], 1)
            mock_create_pod.assert_called_once_with(self.task_name, self.configmap_name)
            mock_sys.exit.assert_called_once_with(1)

    @patch('pod_creator.sys')
    def test_main_function_invalid_args(self, mock_sys):
        """Test main function with incorrect arguments"""
        mock_sys.argv = ['pod_creator.py']
        mock_sys.exit.side_effect = lambda code: __import__('sys').exit(code)
        with patch('pod_creator.logger') as mock_logger:
            from pod_creator import main
            with self.assertRaises(SystemExit) as e:
                main()
            self.assertEqual(e.exception.args[0], 1)
            mock_logger.error.assert_called_once_with("Usage: python3 pod_creator.py <task_name> <configmap_name>")
            mock_sys.exit.assert_called_once_with(1)

if __name__ == '__main__':
    unittest.main()