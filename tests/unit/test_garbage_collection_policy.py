#!/usr/bin/env python3
"""
Unit tests for Garbage Collection Policy functionality
Test Cases: TC-4.1, TC-4.2, TC-4.3, TC-4.4, TC-4.5
"""

import unittest
import tempfile
import os
import sys
import yaml
from unittest.mock import patch
from parameterized import parameterized

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from main import CronDispatcher
from pod_cleaner import PodCleaner


class TestGarbageCollectionPolicy(unittest.TestCase):
    """Test cases for garbage collection policy functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.cron_dispatcher = CronDispatcher()
        self.pod_cleaner = PodCleaner(namespace="test", gc_dry_run=False, gc_batch_size=10)
        
        # Sample custom GC policy
        self.custom_gc_policy = {
            'global': {
                'success': 5,
                'failure': 3
            },
            'tasks': [
                {
                    'taskSelector': {
                        'cron-dispatcher.io/task-name': 'critical-task'
                    },
                    'success': 10,
                    'failure': 5
                }
            ],
            'labelSelector': {
                'matchLabels': {
                    'app.kubernetes.io/managed-by': 'cron-dispatcher'
                }
            },
            'cleanupInterval': '30m'
        }
    
    def test_tc_4_1_default_policy_loading(self):
        """
        TC-4.1: Default Policy Loading
        Objective: Verify default policy loading when file is missing
        Input: Missing GC policy file
        Expected Result: Returns default policy (success:3, failure:3)
        Priority: High
        """
        # Set path to non-existent file
        self.cron_dispatcher.gc_policy_file = '/non/existent/path/gc-policy.yaml'
        
        with patch('main.logger') as mock_logger:
            result = self.cron_dispatcher.load_gc_policy_from_file()
            
            # Assertions for default policy
            self.assertIsNotNone(result, "Should return default policy")
            self.assertEqual(result['global']['success'], 3, "Default success retention should be 3")
            self.assertEqual(result['global']['failure'], 3, "Default failure retention should be 3")
            self.assertEqual(result['cleanupInterval'], '5m', "Default cleanup interval should be 5m")
            self.assertIn('labelSelector', result, "Should contain labelSelector")
            self.assertEqual(result['labelSelector']['matchLabels']['app.kubernetes.io/managed-by'], 
                           'cron-dispatcher', "Should have correct managed-by label")
            
            # Verify info log was called
            mock_logger.info.assert_called()
            info_call = mock_logger.info.call_args[0][0]
            self.assertIn("not found", info_call)
            self.assertIn("default policy", info_call)
    
    def test_tc_4_2_custom_policy_loading(self):
        """
        TC-4.2: Custom Policy Loading
        Objective: Verify custom GC policy loading
        Input: Valid custom GC policy ConfigMap
        Expected Result: Successfully loads custom policy values
        Priority: High
        """
        # Create temporary file with custom GC policy
        custom_yaml = yaml.dump(self.custom_gc_policy)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_file:
            temp_file.write(custom_yaml)
            temp_file_path = temp_file.name
        
        try:
            # Update the GC policy file path
            self.cron_dispatcher.gc_policy_file = temp_file_path
            
            # Test loading custom policy
            result = self.cron_dispatcher.load_gc_policy_from_file()
            
            # Assertions
            self.assertIsNotNone(result, "Should load custom policy successfully")
            self.assertEqual(result['global']['success'], 5, "Custom success retention should be 5")
            self.assertEqual(result['global']['failure'], 3, "Custom failure retention should be 3")
            self.assertEqual(result['cleanupInterval'], '30m', "Custom cleanup interval should be 30m")
            self.assertEqual(len(result['tasks']), 1, "Should have 1 task-specific policy")
            self.assertEqual(result['tasks'][0]['success'], 10, "Task-specific success should be 10")
            self.assertEqual(result['tasks'][0]['failure'], 5, "Task-specific failure should be 5")
            
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)
    
    def test_tc_4_3_cleanup_interval_parsing(self):
        """
        TC-4.3: Cleanup Interval Parsing
        Objective: Verify parsing of various interval formats
        Input: Different interval formats (30s, 5m, 1h, 1d, 120)
        Expected Result: Correctly converted to seconds
        Priority: Medium
        """
        test_cases = [
            ("30s", 30),
            ("5m", 300),
            ("1h", 3600),
            ("1d", 86400),
            ("120", 120),  # Raw seconds
            ("2h", 7200),
            ("90m", 5400),
        ]
        
        for interval_str, expected_seconds in test_cases:
            with self.subTest(interval=interval_str):
                result = self.cron_dispatcher._parse_interval_to_seconds(interval_str)
                self.assertEqual(result, expected_seconds, 
                               f"Interval '{interval_str}' should convert to {expected_seconds} seconds")
    
    @parameterized.expand([
        ("negative_value", "-5m", 300),
        ("zero_value", "0s", 30),
        ("below_min_seconds", "25s", 30),
        ("below_min_plain", "25", 30),
        ("above_max_hours", "25h", 86400),
        ("above_max_days", "2d", 86400),
        ("invalid_unit", "1y", 300),
        ("no_unit", "300", 300),
        ("text_only", "abc", 300),
        ("empty_string", "", 300),
        ("whitespace_only", "   ", 300),
    ])
    def test_tc_4_4_invalid_interval_formats(self, name, interval, expected):
        """TC-4.4: Invalid Interval Formats"""
        with patch.object(self.cron_dispatcher, 'DEFAULT_INTERVAL_SECONDS', 300), \
             patch.object(self.cron_dispatcher, 'MIN_INTERVAL_SECONDS', 30), \
             patch.object(self.cron_dispatcher, 'MAX_INTERVAL_SECONDS', 86400):
            
            result = self.cron_dispatcher._parse_interval_to_seconds(interval)
            self.assertEqual(result, expected, 
                             f"Invalid interval '{interval}' should return {expected}")
    
    def test_tc_4_5_task_specific_policy(self):
        """
        TC-4.5: Task-Specific Policy
        Objective: Verify task-specific retention policies override global defaults
        Input: GC policy with task-specific rules
        Expected Result: Correctly applies task-specific values
        Priority: Medium
        """
        # Test with the pod cleaner's task retention policy method
        test_policy = {
            'global': {
                'success': 3,
                'failure': 3
            },
            'tasks': [
                {
                    'taskSelector': {
                        'cron-dispatcher.io/task-name': 'critical-task'
                    },
                    'success': 10,
                    'failure': 5
                },
                {
                    'taskSelector': {
                        'cron-dispatcher.io/task-name': 'regular-task'
                    },
                    'success': 2,
                    'failure': 1
                }
            ]
        }
        
        # Test critical task gets its specific policy
        critical_policy = self.pod_cleaner._get_task_retention_policy('critical-task', test_policy)
        self.assertEqual(critical_policy['success'], 10, "Critical task should have success=10")
        self.assertEqual(critical_policy['failure'], 5, "Critical task should have failure=5")
        
        # Test regular task gets its specific policy
        regular_policy = self.pod_cleaner._get_task_retention_policy('regular-task', test_policy)
        self.assertEqual(regular_policy['success'], 2, "Regular task should have success=2")
        self.assertEqual(regular_policy['failure'], 1, "Regular task should have failure=1")
        
        # Test unknown task gets global policy
        unknown_policy = self.pod_cleaner._get_task_retention_policy('unknown-task', test_policy)
        self.assertEqual(unknown_policy['success'], 3, "Unknown task should use global success=3")
        self.assertEqual(unknown_policy['failure'], 3, "Unknown task should use global failure=3")


if __name__ == '__main__':
    unittest.main() 