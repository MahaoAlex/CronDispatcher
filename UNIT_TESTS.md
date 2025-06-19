# Unit Tests Documentation

## Overview

This document provides comprehensive information about the unit tests for the cron-dispatcher project. It's designed for developers who need to run, maintain, or extend the unit test suite.

## Quick Start

### Prerequisites
- Python 3.8+
- All dependencies from `requirements.txt`

### Install Test Dependencies
```bash
pip install -r requirements.txt
```

### Run All Unit Tests
```bash
# Using the custom test runner (recommended)
python tests/test_runner.py

# Using unittest discover
python -m unittest discover -s tests -p "test_*.py" -v

# Using pytest (if installed)
pytest tests/ -v
```

## Test Structure

The unit tests are organized into the following main categories:

| Test File | Modules Tested | Description |
|-----------|----------------|-------------|
| `tests/test_logger_config.py` | `src/logger_config.py` | Validates logging setup, including file and stream handlers. |
| `tests/test_utils.py` | `src/utils.py` | Verifies core utilities like command execution and YAML parsing. |
| `tests/test_cci_auth_manager.py`| `src/cci_auth_manager.py` | Tests CCI credential loading and `ccictl` configuration management. |
| `tests/test_pod_creator.py` | `src/pod_creator.py` | Covers the Pod creation logic from ConfigMap definitions. |
| `tests/test_pod_cleaner.py` | `src/pod_cleaner.py` | Checks the garbage collection logic for completed or expired Pods. |
| `tests/test_main.py` | `src/main.py` | End-to-end tests for the main dispatcher, task processing, and scheduling. |


## Running Specific Tests

### By Test Category
```bash
# Logger config tests
python -m unittest tests.test_logger_config -v

# Utility functions tests
python -m unittest tests.test_utils -v

# CCI Auth Manager tests
python -m unittest tests.test_cci_auth_manager -v

# Pod Creator tests
python -m unittest tests.test_pod_creator -v

# Pod Cleaner tests
python -m unittest tests.test_pod_cleaner -v

# Main dispatcher logic tests
python -m unittest tests.test_main -v
```

### Individual Test Cases
```bash
# Run a specific test method
python -m unittest tests.test_utils.TestUtils.test_execute_command_success -v
```

## Test Coverage

### Generate Coverage Report
```bash
# Install coverage if not already installed
pip install coverage

# Run tests with coverage
coverage run --source=src -m unittest discover -s tests -p "test_*.py"

# Generate HTML coverage report
coverage html

# View coverage report (opens in browser)
open htmlcov/index.html  # macOS/Linux
start htmlcov/index.html # Windows
```

### Expected Coverage
The unit tests cover:
- Configuration loading and validation
- Cron expression parsing and validation
- Kubernetes resource validation
- Garbage collection policy management
- Error handling and edge cases
- Configuration reloading

## Test Features

### Mocking and Isolation
- All external dependencies are mocked (file system, Kubernetes API, ccictl commands)
- Tests run in isolation without requiring actual Kubernetes cluster
- Temporary files are used for file-based tests and cleaned up automatically

### Comprehensive Testing
- **Positive test cases**: Valid inputs and expected behaviors
- **Negative test cases**: Invalid inputs and error conditions
- **Edge cases**: Boundary conditions, empty files, and unusual scenarios
- **Error handling**: Exception scenarios, faulty configurations, and recovery paths
- **Configuration Reloading**: Verifies that the dispatcher correctly reloads configurations when files change

## Adding New Tests

### Test Naming Convention
- Test files: `test_<component_name>.py`
- Test classes: `Test<ComponentName>`
- Test methods: `test_tc_<id>_<description>` for test cases, or `test_<description>` for additional tests

### Example Test Structure
```python
def test_tc_X_Y_description(self):
    """
    TC-X.Y: Test Case Name
    Objective: What this test verifies
    Input: What input is provided
    Expected Result: What should happen
    Priority: High/Medium
    """
    # Test implementation
    pass
```

### Best Practices
1. Use descriptive test names and docstrings
2. Mock all external dependencies
3. Clean up resources (temporary files, etc.)
4. Use `self.subTest()` for parameterized tests
5. Include both positive and negative test cases

## Debugging Tests

### Verbose Output
```bash
# Run with maximum verbosity
python -m unittest tests.test_configuration_loading -v

# Debug specific test failures
python -m unittest tests.test_configuration_loading.TestConfigurationLoading.test_tc_1_1_valid_task_configuration_loading
```

### Common Issues
1. **Import Errors**: Ensure `src` directory is in Python path
2. **Mock Assertion Failures**: Check that mocked methods are called with expected parameters
3. **Temporary File Issues**: Tests clean up temporary files, but manual cleanup may be needed on interruption
4. **Path Issues**: Tests use relative paths; run from project root directory

## Test Data and Fixtures

### Sample Configurations
Tests use realistic sample data including:
- Valid and invalid YAML configurations
- Various cron expression formats (Unix and Quartz)
- ConfigMap definitions with different structures
- GC policies with global and task-specific rules

### Mock Responses
- Simulated ccictl command outputs
- Kubernetes API responses
- File system operations
- Network errors and timeouts

## Continuous Integration

The unit tests are designed for easy CI/CD integration:

```yaml
# Example GitHub Actions configuration
- name: Run Unit Tests
  run: |
    pip install -r requirements.txt
    python tests/test_runner.py
    
- name: Generate Coverage Report
  run: |
    pip install coverage
    coverage run --source=src -m unittest discover -s tests -p "test_*.py"
    coverage xml
    coverage report --fail-under=80
```
