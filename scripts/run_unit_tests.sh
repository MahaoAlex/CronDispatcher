#!/bin/bash
# Script to run unit tests and generate coverage report inside a Docker container

set -e

echo "--- Running Unit Tests with Coverage ---"

# Run tests using coverage, pointing to the new tests/unit directory
coverage run --source=src -m unittest discover -s tests/unit -p "test_*.py"

echo "--- Coverage Report ---"

# Display the coverage report in the console
coverage report -m 