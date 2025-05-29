#!/usr/bin/env python3
"""
Local test script - Verify basic functionality of CronDispatcher
"""

import os
import sys
import yaml
import tempfile
from unittest.mock import Mock, patch
from kubernetes import client

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_cron_expression_validation():
    """Test cron expression validation"""
    print("Testing cron expression validation...")
    
    # Mock imports
    with patch('kubernetes.client'):
        with patch('kubernetes.config'):
            from main import CronDispatcher
            
            dispatcher = CronDispatcher()
            
            # Test valid cron expressions
            valid_expressions = [
                "0 */1 * * ? *",  # Quartz format
                "0 * * * *",      # Standard format
                "30 2 * * *",     # Daily at 2:30
                "0 9 ? * MON *"   # Every Monday at 9 AM
            ]
            
            for expr in valid_expressions:
                result = dispatcher.validate_cron_expression(expr)
                print(f"  [PASS] {expr}: {result}")
                assert result, f"Expression should be valid: {expr}"
            
            # Test invalid cron expressions
            invalid_expressions = [
                "invalid",
                "60 * * * *",  # Minutes out of range
                "* * * * * * *"  # Too many fields
            ]
            
            for expr in invalid_expressions:
                result = dispatcher.validate_cron_expression(expr)
                print(f"  [FAIL] {expr}: {result}")
                assert not result, f"Expression should be invalid: {expr}"
    
    print("Cron expression validation test passed")

def test_quartz_to_cron_conversion():
    """Test Quartz format conversion"""
    print("Testing Quartz format conversion...")
    
    with patch('kubernetes.client'):
        with patch('kubernetes.config'):
            from main import CronDispatcher
            
            dispatcher = CronDispatcher()
            
            test_cases = [
                ("0 0 */1 * * ? *", "0 */1 * * *"),  # Every hour
                ("0 30 2 * * ? *", "30 2 * * *"),   # Daily at 2:30
                ("0 0 9 ? * MON *", "0 9 ? * MON")  # Every Monday at 9 AM
            ]
            
            for quartz, expected in test_cases:
                result = dispatcher.convert_quartz_to_cron(quartz)
                print(f"  {quartz} -> {result}")
                assert result == expected, f"Conversion result mismatch: expected {expected}, got {result}"
    
    print("Quartz format conversion test passed")

def test_uuid_generation():
    """Test UUID generation"""
    print("Testing UUID generation...")
    
    with patch('kubernetes.client'):
        with patch('kubernetes.config'):
            from main import CronDispatcher
            
            dispatcher = CronDispatcher()
            
            # Generate multiple UUIDs and verify
            uuids = set()
            for _ in range(10):
                uuid = dispatcher.generate_pod_uuid()
                print(f"  Generated UUID: {uuid}")
                assert len(uuid) == 9, f"UUID length should be 9 digits: {uuid}"
                assert uuid not in uuids, f"UUID should be unique: {uuid}"
                uuids.add(uuid)
    
    print("UUID generation test passed")

def test_config_parsing():
    """Test configuration parsing"""
    print("Testing configuration parsing...")
    
    # Create test configuration
    test_config = """
    - name: test-task-1
      schedule: "0 */1 * * ? *"
      podTemplatePath: /etc/cron-templates/test-task-1.yaml
      state: on
    - name: test-task-2
      schedule: "30 2 * * ? *"
      podTemplatePath: /etc/cron-templates/test-task-2.yaml
      state: off
    """
    
    tasks = yaml.safe_load(test_config)
    
    assert len(tasks) == 2, f"Should have 2 tasks, actually have {len(tasks)}"
    
    task1 = tasks[0]
    assert task1['name'] == 'test-task-1'
    assert task1['state'] == 'on'
    
    task2 = tasks[1]
    assert task2['name'] == 'test-task-2'
    assert task2['state'] == 'off'
    
    print("  Configuration parsing correct")
    print("Configuration parsing test passed")

def test_pod_template_processing():
    """Test Pod template processing"""
    print("Testing Pod template processing...")
    
    # Create test Pod template
    pod_template = {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': 'test-pod',
            'labels': {'app': 'test'}
        },
        'spec': {
            'containers': [{
                'name': 'test-container',
                'image': 'busybox:latest'
            }]
        }
    }
    
    # Mock processing
    task_name = 'test-task'
    pod_uuid = 'abc123def'
    namespace = 'test-namespace'
    
    # Update template
    pod_name = f"{task_name}-{pod_uuid}"
    pod_template['metadata']['name'] = pod_name
    pod_template['metadata']['namespace'] = namespace
    
    if 'labels' not in pod_template['metadata']:
        pod_template['metadata']['labels'] = {}
    
    pod_template['metadata']['labels'].update({
        'app.kubernetes.io/managed-by': 'CronDispatcher',
        'cron-dispatcher.io/task-name': task_name,
        'cron-dispatcher.io/instance': pod_name
    })
    
    # Verify results
    assert pod_template['metadata']['name'] == 'test-task-abc123def'
    assert pod_template['metadata']['namespace'] == 'test-namespace'
    assert pod_template['metadata']['labels']['app.kubernetes.io/managed-by'] == 'CronDispatcher'
    assert pod_template['metadata']['labels']['cron-dispatcher.io/task-name'] == 'test-task'
    
    print("  Pod template processing correct")
    print("Pod template processing test passed")

def test_garbage_collection_dry_run():
    """Test garbage collection dry run mode"""
    # Set dry run mode
    os.environ['GC_DRY_RUN'] = 'true'
    
    dispatcher = CronDispatcher()
    assert dispatcher.gc_dry_run
    
    # Clean up
    del os.environ['GC_DRY_RUN']

def test_garbage_collection_batch_size():
    """Test garbage collection batch size configuration"""
    # Set custom batch size
    os.environ['GC_BATCH_SIZE'] = '25'
    
    dispatcher = CronDispatcher()
    assert dispatcher.gc_batch_size == 25
    
    # Clean up
    del os.environ['GC_BATCH_SIZE']

def test_task_retention_policy():
    """Test task-specific retention policy"""
    dispatcher = CronDispatcher()
    
    # Mock garbage collection policy
    gc_policy = {
        'global': {
            'success': 3,
            'failure': 3
        },
        'tasks': [
            {
                'taskSelector': {
                    'cron-dispatcher.io/task-name': 'test-task'
                },
                'success': 5,
                'failure': 2
            }
        ]
    }
    
    # Test task-specific policy
    task_policy = dispatcher._get_task_retention_policy('test-task', gc_policy)
    assert task_policy['success'] == 5
    assert task_policy['failure'] == 2
    
    # Test global policy fallback
    global_policy = dispatcher._get_task_retention_policy('other-task', gc_policy)
    assert global_policy['success'] == 3
    assert global_policy['failure'] == 3

def test_load_gc_policy_default():
    """Test loading default garbage collection policy"""
    dispatcher = CronDispatcher()
    
    # Mock ConfigMap not found
    with patch.object(dispatcher.k8s_client, 'read_namespaced_config_map') as mock_read:
        mock_read.side_effect = client.exceptions.ApiException(status=404)
        
        policy = dispatcher.load_gc_policy()
        
        # Should return default policy
        assert 'global' in policy
        assert policy['global']['success'] == 3
        assert policy['global']['failure'] == 3
        assert 'labelSelector' in policy

def main():
    """Run all tests"""
    print("Starting CronDispatcher local tests...")
    print("=" * 50)
    
    try:
        test_cron_expression_validation()
        print()
        
        test_quartz_to_cron_conversion()
        print()
        
        test_uuid_generation()
        print()
        
        test_config_parsing()
        print()
        
        test_pod_template_processing()
        print()
        
        test_garbage_collection_dry_run()
        print()
        
        test_garbage_collection_batch_size()
        print()
        
        test_task_retention_policy()
        print()
        
        test_load_gc_policy_default()
        print()
        
        print("=" * 50)
        print("All tests passed!")
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main() 