#!/usr/bin/env python3
"""
Unit tests for Pod Cleaner functionality
"""

import unittest
import os
import sys
from unittest.mock import patch
import yaml
import json

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))

from pod_cleaner import PodCleaner

# Import test_helpers with correct path
try:
    from tests.test_helpers import create_mock_pod
except ImportError:
    # Fallback for container environment
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    from test_helpers import create_mock_pod


class TestPodCleaner(unittest.TestCase):
    """Test cases for Pod Cleaner functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.gc_policy = {
            'global': {'success': 2, 'failure': 1},
            'tasks': [{
                'taskSelector': {'cron-dispatcher.io/task-name': 'special-task'},
                'success': 1,
                'failure': 0
            }]
        }
        self.pods = [
            # Regular task pods (oldest first)
            create_mock_pod("task1-succ-1", "task1", "Succeeded", "2023-01-01T12:00:00Z"),
            create_mock_pod("task1-succ-2", "task1", "Succeeded", "2023-01-01T13:00:00Z"),
            create_mock_pod("task1-succ-3", "task1", "Succeeded", "2023-01-01T14:00:00Z"),  # should be kept
            create_mock_pod("task1-fail-1", "task1", "Failed", "2023-01-01T15:00:00Z"),
            create_mock_pod("task1-fail-2", "task1", "Failed", "2023-01-01T16:00:00Z"),  # should be kept
            
            # Special task pods (oldest first)
            create_mock_pod("special-succ-1", "special-task", "Succeeded", "2023-01-02T12:00:00Z"),  # should be kept
            create_mock_pod("special-succ-2", "special-task", "Succeeded", "2023-01-02T13:00:00Z"),  # should be deleted
            create_mock_pod("special-fail-1", "special-task", "Failed", "2023-01-02T14:00:00Z"),  # should be deleted
        ]

    def test_group_pods_by_task(self):
        """Test grouping of pods by task name and status"""
        pod_cleaner = PodCleaner(namespace="test-ns", gc_dry_run=False)
        grouped_pods = pod_cleaner._group_pods_by_task(self.pods)
        
        self.assertIn("task1", grouped_pods)
        self.assertIn("special-task", grouped_pods)
        self.assertEqual(len(grouped_pods["task1"]["success"]), 3)
        self.assertEqual(len(grouped_pods["task1"]["failed"]), 2)
        self.assertEqual(len(grouped_pods["special-task"]["success"]), 2)
        self.assertEqual(len(grouped_pods["special-task"]["failed"]), 1)

    def test_get_task_retention_policy(self):
        """Test retrieval of retention policies for tasks"""
        pod_cleaner = PodCleaner(namespace="test-ns", gc_dry_run=False)
        
        # Test task with specific policy
        special_policy = pod_cleaner._get_task_retention_policy("special-task", self.gc_policy)
        self.assertEqual(special_policy['success'], 1)
        self.assertEqual(special_policy['failure'], 0)
        
        # Test task using global policy
        global_policy = pod_cleaner._get_task_retention_policy("task1", self.gc_policy)
        self.assertEqual(global_policy['success'], 2)
        self.assertEqual(global_policy['failure'], 1)

    @patch('pod_cleaner.execute_command_with_retry')
    def test_delete_pod(self, mock_execute):
        """Test the deletion of a single pod"""
        mock_execute.return_value = (True, "pod deleted", "")
        pod_cleaner = PodCleaner(namespace="test-ns", gc_dry_run=False)
        result = pod_cleaner._delete_pod("test-pod", "test-ns", "testing")
        
        self.assertTrue(result)
        mock_execute.assert_called_once()

    @patch.object(PodCleaner, '_delete_pod')
    def test_delete_pods_batch(self, mock_delete):
        """Test batch deletion of pods"""
        mock_delete.return_value = True
        pod_cleaner = PodCleaner(namespace="test-ns", gc_dry_run=False)
        pods_to_delete = self.pods[:3]
        
        deleted_count = pod_cleaner._delete_pods_batch(pods_to_delete, "testing batch")
        self.assertEqual(deleted_count, 3)
        self.assertEqual(mock_delete.call_count, 3)
        
    def test_cleanup_task_pods(self):
        """Test cleanup logic for a single task's pods"""
        pod_cleaner = PodCleaner(namespace="test-ns", gc_dry_run=False)
        task1_pods = {
            'success': [
                create_mock_pod("task1-succ-1", "task1", "Succeeded", "2023-01-01T12:00:00Z"),
                create_mock_pod("task1-succ-2", "task1", "Succeeded", "2023-01-01T13:00:00Z"),
                create_mock_pod("task1-succ-3", "task1", "Succeeded", "2023-01-01T14:00:00Z"),  # newest
            ],
            'failed': [
                create_mock_pod("task1-fail-1", "task1", "Failed", "2023-01-01T15:00:00Z"),
                create_mock_pod("task1-fail-2", "task1", "Failed", "2023-01-01T16:00:00Z"),  # newest
            ]
        }
        
        with patch.object(pod_cleaner, '_delete_pods_batch') as mock_delete_batch:
            mock_delete_batch.return_value = 1  # Each call deletes one pod
            
            result = pod_cleaner._cleanup_task_pods("task1", task1_pods, self.gc_policy)
            
            # Should make two calls: one for success pods, one for failed pods
            self.assertEqual(mock_delete_batch.call_count, 2)
            
            # Check success pods deletion
            success_call_args = mock_delete_batch.call_args_list[0][0]
            self.assertEqual(len(success_call_args[0]), 1)  # One pod to delete
            self.assertEqual(success_call_args[0][0]['metadata']['name'], "task1-succ-1")  # Oldest success pod
            
            # Check failed pods deletion
            failed_call_args = mock_delete_batch.call_args_list[1][0]
            self.assertEqual(len(failed_call_args[0]), 1)  # One pod to delete
            self.assertEqual(failed_call_args[0][0]['metadata']['name'], "task1-fail-1")  # Oldest failed pod
            
            self.assertEqual(result, 2)  # Total two pods deleted

    @patch('pod_cleaner.execute_command_with_retry')
    def test_cleanup_pods_main_flow(self, mock_execute_get):
        """Test the main cleanup_pods flow"""
        pod_cleaner = PodCleaner(namespace="test-ns", gc_dry_run=False)
        
        # Prepare pod list response
        pod_list_yaml = yaml.dump({'items': self.pods})
        
        # First call is to get pods, subsequent are deletes
        mock_execute_get.side_effect = [
            (True, pod_list_yaml, ""),  # get pods call
            (True, "deleted", ""),  # delete special-succ-2
            (True, "deleted", ""),  # delete special-fail-1
            (True, "deleted", ""),  # delete task1-succ-1
            (True, "deleted", "")   # delete task1-fail-1
        ]

        deleted_count = pod_cleaner.cleanup_pods(self.gc_policy)
        self.assertEqual(deleted_count, 4)
        self.assertEqual(mock_execute_get.call_count, 5)

    @patch('pod_cleaner.execute_command_with_retry')
    def test_cleanup_pods_dry_run(self, mock_execute):
        """Test cleanup_pods in dry run mode"""
        pod_cleaner = PodCleaner(namespace="test-ns", gc_dry_run=True)
        pod_list_yaml = yaml.dump({'items': self.pods})
        mock_execute.return_value = (True, pod_list_yaml, "")
        
        with patch('pod_cleaner.logger') as mock_logger:
            deleted_count = pod_cleaner.cleanup_pods(self.gc_policy)
            self.assertEqual(deleted_count, 4)
            
            # Only get pods should be called, no deletes
            mock_execute.assert_called_once()
            
            # Verify that logger.info was called (dry run mode logs instead of deleting)
            self.assertGreater(mock_logger.info.call_count, 0)

    def test_retention_logic(self):
        """Test the retention logic directly"""
        # Test data: 3 success pods, 2 failed pods (oldest first)
        success_pods = [
            create_mock_pod("task1-succ-1", "task1", "Succeeded", "2023-01-01T12:00:00Z"),  # oldest
            create_mock_pod("task1-succ-2", "task1", "Succeeded", "2023-01-01T13:00:00Z"),
            create_mock_pod("task1-succ-3", "task1", "Succeeded", "2023-01-01T14:00:00Z"),  # newest
        ]
        failed_pods = [
            create_mock_pod("task1-fail-1", "task1", "Failed", "2023-01-01T15:00:00Z"),  # oldest
            create_mock_pod("task1-fail-2", "task1", "Failed", "2023-01-01T16:00:00Z"),  # newest
        ]
        
        # Sort by creation timestamp (newest first) as in production code
        success_pods_sorted = sorted(
            success_pods,
            key=lambda p: p['metadata']['creationTimestamp'],
            reverse=True
        )
        failed_pods_sorted = sorted(
            failed_pods,
            key=lambda p: p['metadata']['creationTimestamp'],
            reverse=True
        )
        
        # With retention policy: success=2, failure=1
        max_success = 2
        max_failed = 1
        
        # Pods to delete should be the oldest ones (after the kept ones)
        success_to_delete = success_pods_sorted[max_success:]  # Should be 1 pod
        failed_to_delete = failed_pods_sorted[max_failed:]     # Should be 1 pod
        
        self.assertEqual(len(success_to_delete), 1)
        self.assertEqual(len(failed_to_delete), 1)
        
        # Verify correct pods are marked for deletion
        self.assertEqual(success_to_delete[0]['metadata']['name'], "task1-succ-1")
        self.assertEqual(failed_to_delete[0]['metadata']['name'], "task1-fail-1")


if __name__ == '__main__':
    unittest.main()