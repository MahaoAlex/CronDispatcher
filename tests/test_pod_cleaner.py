#!/usr/bin/env python3
"""
Unit tests for Pod Cleaner functionality
"""

import unittest
import os
import sys
from unittest.mock import patch
import yaml

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from pod_cleaner import PodCleaner
from tests.test_helpers import create_mock_pod


class TestPodCleaner(unittest.TestCase):
    """Test cases for Pod Cleaner functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.pod_cleaner = PodCleaner(namespace="test-ns", gc_dry_run=False)
        self.gc_policy = {
            'global': {'success': 2, 'failure': 1},
            'tasks': [{
                'taskSelector': {'cron-dispatcher.io/task-name': 'special-task'},
                'success': 1,
                'failure': 0
            }]
        }
        self.pods = [
            # Regular task pods
            create_mock_pod("task1-succ-1", "task1", "Succeeded", "2023-01-01T12:00:00Z"),
            create_mock_pod("task1-succ-2", "task1", "Succeeded", "2023-01-01T13:00:00Z"),
            create_mock_pod("task1-succ-3", "task1", "Succeeded", "2023-01-01T14:00:00Z"), # should be deleted
            create_mock_pod("task1-fail-1", "task1", "Failed", "2023-01-01T15:00:00Z"),
            create_mock_pod("task1-fail-2", "task1", "Failed", "2023-01-01T16:00:00Z"), # should be deleted
            # Special task pods
            create_mock_pod("special-succ-1", "special-task", "Succeeded", "2023-01-02T12:00:00Z"),
            create_mock_pod("special-succ-2", "special-task", "Succeeded", "2023-01-02T13:00:00Z"), # should be deleted
            create_mock_pod("special-fail-1", "special-task", "Failed", "2023-01-02T14:00:00Z"), # should be deleted
        ]

    def test_group_pods_by_task(self):
        """Test grouping of pods by task name and status"""
        grouped_pods = self.pod_cleaner._group_pods_by_task(self.pods)
        self.assertIn("task1", grouped_pods)
        self.assertIn("special-task", grouped_pods)
        self.assertEqual(len(grouped_pods["task1"]["success"]), 3)
        self.assertEqual(len(grouped_pods["task1"]["failed"]), 2)
        self.assertEqual(len(grouped_pods["special-task"]["success"]), 2)
        self.assertEqual(len(grouped_pods["special-task"]["failed"]), 1)

    def test_get_task_retention_policy(self):
        """Test retrieval of retention policies for tasks"""
        # Test task with specific policy
        special_policy = self.pod_cleaner._get_task_retention_policy("special-task", self.gc_policy)
        self.assertEqual(special_policy['success'], 1)
        self.assertEqual(special_policy['failure'], 0)
        # Test task using global policy
        global_policy = self.pod_cleaner._get_task_retention_policy("task1", self.gc_policy)
        self.assertEqual(global_policy['success'], 2)
        self.assertEqual(global_policy['failure'], 1)

    @patch('pod_cleaner.execute_command_with_retry')
    def test_delete_pod(self, mock_execute):
        """Test the deletion of a single pod"""
        mock_execute.return_value = (True, "pod deleted", "")
        result = self.pod_cleaner._delete_pod("test-pod", "test-ns", "testing")
        self.assertTrue(result)
        mock_execute.assert_called_once()

    @patch.object(PodCleaner, '_delete_pod')
    def test_delete_pods_batch(self, mock_delete):
        """Test batch deletion of pods"""
        mock_delete.return_value = True
        pods_to_delete = self.pods[:3]
        deleted_count = self.pod_cleaner._delete_pods_batch(pods_to_delete, "testing batch")
        self.assertEqual(deleted_count, 3)
        self.assertEqual(mock_delete.call_count, 3)
        
    @patch.object(PodCleaner, '_delete_pods_batch')
    def test_cleanup_task_pods(self, mock_delete_batch):
        """Test cleanup logic for a single task's pods"""
        grouped_pods = self.pod_cleaner._group_pods_by_task(self.pods)
        
        # Test regular task cleanup
        self.pod_cleaner._cleanup_task_pods("task1", grouped_pods["task1"], self.gc_policy)
        # 2 calls: one for successful, one for failed
        self.assertEqual(mock_delete_batch.call_count, 2)
        # Check pods passed for deletion
        # success pods to delete
        self.assertEqual(len(mock_delete_batch.call_args_list[0].args[0]), 1)
        self.assertEqual(mock_delete_batch.call_args_list[0].args[0][0]['metadata']['name'], 'task1-succ-1')
        # failed pods to delete
        self.assertEqual(len(mock_delete_batch.call_args_list[1].args[0]), 1)
        self.assertEqual(mock_delete_batch.call_args_list[1].args[0][0]['metadata']['name'], 'task1-fail-1')
    
    @patch('pod_cleaner.execute_command_with_retry')
    def test_cleanup_pods_main_flow(self, mock_execute_get):
        """Test the main cleanup_pods flow"""
        pod_list_yaml = yaml.dump({'items': self.pods})
        # First call is to get pods, subsequent are deletes
        mock_execute_get.side_effect = [(True, pod_list_yaml, "")] + ([(True, "deleted", "")] * 4)

        deleted_count = self.pod_cleaner.cleanup_pods(self.gc_policy)
        
        self.assertEqual(deleted_count, 4)
        # 1 get pods + 4 delete calls
        self.assertEqual(mock_execute_get.call_count, 5)

    @patch('pod_cleaner.execute_command_with_retry')
    def test_cleanup_pods_dry_run(self, mock_execute):
        """Test cleanup_pods in dry run mode"""
        self.pod_cleaner.gc_dry_run = True
        pod_list_yaml = yaml.dump({'items': self.pods})
        mock_execute.return_value = (True, pod_list_yaml, "")
        
        with patch('pod_cleaner.logger') as mock_logger:
            deleted_count = self.pod_cleaner.cleanup_pods(self.gc_policy)
            self.assertEqual(deleted_count, 4)
            # Only get pods should be called, no deletes
            mock_execute.assert_called_once()
            self.assertIn("[DRY RUN]", mock_logger.info.call_args_list[4].args[0])


if __name__ == '__main__':
    unittest.main() 