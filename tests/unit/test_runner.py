#!/usr/bin/env python3
"""
Test runner for CronDispatcher unit tests
Executes all unit tests and provides detailed reporting
"""

import unittest
import sys
import os

def create_test_suite():
    """
    Create a test suite by discovering all tests in the 'tests' directory
    """
    # Get the directory of the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Create a test loader
    loader = unittest.TestLoader()
    
    # Discover tests in the current directory (matching 'test_*.py' pattern)
    suite = loader.discover(start_dir=current_dir, pattern='test_*.py')
    
    return suite


def run_tests():
    """Run all unit tests with detailed output"""
    # Create test suite
    suite = create_test_suite()
    
    # Create test runner with verbosity
    runner = unittest.TextTestRunner(
        verbosity=2,
        stream=sys.stdout,
        descriptions=True,
        failfast=False
    )
    
    # Run tests
    print("="*70)
    print("CronDispatcher Unit Tests")
    print("="*70)
    
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("Test Summary:")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
    
    if result.failures:
        print(f"\nFailures:")
        for test, traceback in result.failures:
            print(f"  - {test}")
    
    if result.errors:
        print(f"\nErrors:")
        for test, traceback in result.errors:
            print(f"  - {test}")
    
    print("="*70)
    
    # Return exit code based on test results
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    # Add the parent directory ('CronDispatcher') to the path to find the 'src' module
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    sys.exit(run_tests()) 