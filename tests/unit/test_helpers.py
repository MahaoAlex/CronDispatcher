#!/usr/bin/env python3
"""
Helper functions and data for unit tests
"""

def create_mock_pod(name, task_name, phase, timestamp):
    """Helper function to create a mock Pod object"""
    return {
        'metadata': {
            'name': name,
            'namespace': 'test-ns',
            'creationTimestamp': timestamp,
            'labels': {
                'app.kubernetes.io/managed-by': 'cron-dispatcher',
                'cron-dispatcher.io/task-name': task_name
            }
        },
        'status': {'phase': phase}
    }

def get_sample_pod_definition():
    """Returns a sample pod definition dictionary."""
    return {
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

def get_sample_configmap_data(configmap_name, pod_definition_yaml):
    """Returns a sample configmap data dictionary."""
    return {
        'apiVersion': 'v1',
        'kind': 'ConfigMap',
        'metadata': {'name': configmap_name},
        'data': {
            'pod.yaml': pod_definition_yaml
        }
    } 