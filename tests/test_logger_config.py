#!/usr/bin/env python3
"""
Unit tests for logger_config module
"""

import unittest
import os
import sys
import logging
import tempfile
import shutil

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from logger_config import setup_logger

class TestLoggerConfig(unittest.TestCase):
    """Test cases for logger configuration"""

    def setUp(self):
        """Set up a temporary directory for logs"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up the temporary directory"""
        shutil.rmtree(self.temp_dir)

    def test_logger_with_file_output(self):
        """Test logger setup with a file handler"""
        log_file = os.path.join(self.temp_dir, 'test.log')
        logger = setup_logger('test_file_logger', log_file)
        
        self.assertEqual(len(logger.handlers), 2) # stdout + file handler
        
        # Check if the file was created
        logger.info("This is a test message.")
        self.assertTrue(os.path.exists(log_file))
        with open(log_file, 'r') as f:
            self.assertIn("This is a test message.", f.read())

    def test_logger_without_file_output(self):
        """Test logger setup without a file handler"""
        logger = setup_logger('test_stdout_logger')
        
        self.assertEqual(len(logger.handlers), 1)
        self.assertIsInstance(logger.handlers[0], logging.StreamHandler)

    def test_logger_creates_directory(self):
        """Test that the logger creates the log directory if it doesn't exist"""
        log_dir = os.path.join(self.temp_dir, 'non_existent_dir')
        log_file = os.path.join(log_dir, 'test.log')
        
        # Ensure directory does not exist
        self.assertFalse(os.path.exists(log_dir))
        
        # Setup logger
        setup_logger('test_dir_creation', log_file)
        
        # Check if directory was created
        self.assertTrue(os.path.exists(log_dir))

if __name__ == '__main__':
    unittest.main() 