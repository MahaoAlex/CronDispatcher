#!/usr/bin/env python3
"""
Unit tests for Cron Expression Validation functionality
Test Cases: TC-2.1, TC-2.2, TC-2.3, TC-2.4
"""

import unittest
import os
import sys
from unittest.mock import patch

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from main import CronDispatcher


class TestCronExpressionValidation(unittest.TestCase):
    """Test cases for cron expression validation functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.cron_dispatcher = CronDispatcher()
    
    def test_tc_2_1_valid_unix_cron_expression(self):
        """
        TC-2.1: Valid Unix Cron Expression
        Objective: Verify standard Unix cron expressions
        Input: "0 */6 * * *"
        Expected Result: Validation passes, returns True
        Priority: High
        """
        valid_unix_expressions = [
            "0 */6 * * *",  # Every 6 hours
            "*/5 * * * *",  # Every 5 minutes
            "30 2 * * *",   # Daily at 2:30 AM
            "0 0 * * 0",    # Weekly on Sunday
            "0 0 1 * *",    # Monthly on 1st
            "15 14 1 * *",  # Monthly on 1st at 2:15 PM
            "0 22 * * 1-5", # Weekdays at 10 PM
            "23 0-20/2 * * *", # Every 2 hours from 0-20, at 23 minutes
        ]
        
        for expression in valid_unix_expressions:
            with self.subTest(expression=expression):
                result = self.cron_dispatcher.validate_cron_expression(expression)
                self.assertTrue(result, f"Expression '{expression}' should be valid")
    
    def test_tc_2_2_valid_quartz_cron_expression(self):
        """
        TC-2.2: Valid Quartz Cron Expression
        Objective: Verify Quartz format conversion
        Input: "0 0 */6 * * *"
        Expected Result: Validation passes, correctly converted to Unix format
        Priority: High
        """
        quartz_to_unix_mapping = [
            ("0 0 */6 * * *", "0 */6 * * *"),    # Every 6 hours
            ("0 */5 * * * *", "*/5 * * * *"),    # Every 5 minutes
            ("0 30 2 * * *", "30 2 * * *"),     # Daily at 2:30 AM
            ("0 0 0 * * 0", "0 0 * * 0"),       # Weekly on Sunday
            ("0 0 0 1 * *", "0 0 1 * *"),       # Monthly on 1st
            ("0 15 14 1 * *", "15 14 1 * *"),   # Monthly on 1st at 2:15 PM
        ]
        
        for quartz_expr, expected_unix in quartz_to_unix_mapping:
            with self.subTest(quartz=quartz_expr, unix=expected_unix):
                # Test validation passes
                result = self.cron_dispatcher.validate_cron_expression(quartz_expr)
                self.assertTrue(result, f"Quartz expression '{quartz_expr}' should be valid")
                
                # Test conversion is correct
                converted = self.cron_dispatcher._convert_quartz_to_cron(quartz_expr)
                self.assertEqual(converted, expected_unix, 
                               f"Quartz '{quartz_expr}' should convert to '{expected_unix}'")
    
    def test_tc_2_3_invalid_cron_expression(self):
        """
        TC-2.3: Invalid Cron Expression
        Objective: Verify rejection of malformed expressions
        Input: "invalid cron"
        Expected Result: Validation fails, error logged
        Priority: High
        """
        invalid_expressions = [
            "invalid cron",           # Completely invalid
            "60 * * * *",            # Invalid minute (>59)
            "* 25 * * *",            # Invalid hour (>23)
            "* * 32 * *",            # Invalid day (>31)
            "* * * 13 *",            # Invalid month (>12)
            "* * * * 8",             # Invalid day of week (>7)
            "* * * *",               # Too few fields
            "* * * * * * *",         # Too many fields for Unix
            "",                      # Empty string
            "*/61 * * * *",          # Invalid step value
            "0-70 * * * *",          # Invalid range
            "a b c d e",             # Non-numeric values
            "* * * * MON-FRI-SAT",   # Invalid range format
        ]
        
        for expression in invalid_expressions:
            with self.subTest(expression=expression):
                with patch('main.logger') as mock_logger:
                    result = self.cron_dispatcher.validate_cron_expression(expression)
                    self.assertFalse(result, f"Expression '{expression}' should be invalid")
                    mock_logger.error.assert_called()
    
    def test_tc_2_4_edge_case_expressions(self):
        """
        TC-2.4: Edge Case Expressions
        Objective: Verify handling of edge case expressions
        Input: Various edge case expressions
        Expected Result: Correctly validated based on validity
        Priority: Medium
        """
        edge_cases = [
            # (expression, should_be_valid, description)
            ("* * * * *", True, "All wildcards"),
            ("0 0 * * *", True, "Midnight daily"),
            ("59 23 * * *", True, "Last minute of day"),
            ("0 0 31 * *", True, "31st of month (valid for some months)"),
            ("0 0 29 2 *", True, "Feb 29th (valid for leap years)"),
            ("0 0 1 1 *", True, "New Year's Day"),
            ("*/1 * * * *", True, "Every minute"),
            ("0-59 * * * *", True, "Full minute range"),
            ("0 0-23 * * *", True, "Full hour range"),
            ("0 0 1-31 * *", True, "Full day range"),
            ("0 0 * 1-12 *", True, "Full month range"),
            ("0 0 * * 0-7", True, "Full day-of-week range (0-7 for Sunday)"),
            ("0 0 * * SUN", True, "Named day of week"),
            ("0 0 * JAN *", True, "Named month"),
            ("@yearly", False, "Special string (not supported in standard cron)"),
            ("@daily", False, "Special string (not supported in standard cron)"),
            ("H H * * *", False, "Jenkins-style hash (not standard cron)"),
        ]
        
        for expression, should_be_valid, description in edge_cases:
            with self.subTest(expression=expression, description=description):
                result = self.cron_dispatcher.validate_cron_expression(expression)
                if should_be_valid:
                    self.assertTrue(result, f"{description}: '{expression}' should be valid")
                else:
                    self.assertFalse(result, f"{description}: '{expression}' should be invalid")
    
    def test_quartz_conversion_edge_cases(self):
        """
        Additional test: Verify edge cases in Quartz to Unix conversion
        """
        edge_cases = [
            # Already Unix format (5 fields) - should return as-is
            ("*/5 * * * *", "*/5 * * * *"),
            ("0 0 * * 0", "0 0 * * 0"),
            
            # Quartz format (6 fields) - should convert
            ("0 */5 * * * *", "*/5 * * * *"),
            ("0 0 0 * * 0", "0 0 * * 0"),
            
            # Invalid formats
            ("* * *", "* * *"),  # Too few fields - return as-is
            ("* * * * * * * *", "* * * * * * * *"),  # Too many fields - return as-is
        ]
        
        for input_expr, expected_output in edge_cases:
            with self.subTest(input=input_expr):
                result = self.cron_dispatcher._convert_quartz_to_cron(input_expr)
                self.assertEqual(result, expected_output, 
                               f"Input '{input_expr}' should convert to '{expected_output}'")
    
    def test_cron_validation_with_crontab_library_exception(self):
        """
        Additional test: Verify handling when crontab library raises exceptions
        """
        # Test with expression that might cause crontab library to raise exception
        with patch('main.CronTab') as mock_crontab:
            mock_crontab.side_effect = Exception("Crontab library error")
            
            with patch('main.logger') as mock_logger:
                result = self.cron_dispatcher.validate_cron_expression("0 0 * * *")
                
                self.assertFalse(result, "Should return False when crontab library raises exception")
                mock_logger.error.assert_called()
    
    def test_cron_validation_performance(self):
        """
        Additional test: Verify reasonable performance for validation
        """
        import time
        
        expressions = [
            "*/5 * * * *",
            "0 */6 * * *",
            "30 2 * * *",
            "0 0 * * 0",
            "invalid expression",
        ] * 20  # Test with 100 expressions
        
        start_time = time.time()
        for expression in expressions:
            self.cron_dispatcher.validate_cron_expression(expression)
        end_time = time.time()
        
        elapsed_time = end_time - start_time
        self.assertLess(elapsed_time, 5.0, 
                       f"Validating {len(expressions)} expressions should take less than 5 seconds")


if __name__ == '__main__':
    unittest.main() 