import unittest
import os
import sys
import time
from unittest.mock import patch, MagicMock, call

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))

# We must patch setup_logger here, where it's defined, before main imports it.
with patch('logger_config.setup_logger'):
    from main import CronDispatcher

class TestCronDispatcherMain(unittest.TestCase):
    """Test cases for the main CronDispatcher class"""

    def setUp(self):
        """Set up test fixtures"""
        with patch('main.PodCleaner'), patch('main.CCIAuthManager'), patch('main.CronTab'):
            self.dispatcher = CronDispatcher()

        self.valid_task = {
            'name': 'test-job',
            'schedule': '*/5 * * * *',
            'podDefinitionConfigmap': 'test-job-configmap',
            'state': 'on'
        }

    @patch.object(CronDispatcher, 'update_crontab')
    @patch.object(CronDispatcher, 'update_cleanup_interval')
    @patch.object(CronDispatcher, 'load_tasks_config_from_file')
    @patch.object(CronDispatcher, 'load_gc_policy_from_file')
    def test_load_and_apply_config(self, mock_load_gc, mock_load_tasks, mock_update_cleanup, mock_update_crontab):
        """Test the initial loading and application of configurations"""
        mock_load_tasks.return_value = [self.valid_task]
        mock_load_gc.return_value = {'cleanupInterval': '10m'}
        self.dispatcher._load_and_apply_config()
        mock_load_tasks.assert_called_once()
        mock_update_crontab.assert_called_once_with([self.valid_task])
        mock_load_gc.assert_called_once()
        mock_update_cleanup.assert_called_once_with({'cleanupInterval': '10m'})

    @patch('main.os.path.getmtime')
    @patch('main.os.path.exists', return_value=True)
    def test_watch_config_change(self, mock_exists, mock_getmtime):
        """Test the file change watching mechanism"""
        mock_getmtime.return_value = 100
        self.assertTrue(self.dispatcher.watch_tasks_config_change())
        self.assertFalse(self.dispatcher.watch_tasks_config_change())
        mock_getmtime.return_value = 200
        self.assertTrue(self.dispatcher.watch_tasks_config_change())

    @patch('main.time.time')
    def test_run_cleanup_logic(self, mock_time):
        """Test the logic for running the cleanup job based on interval"""
        self.dispatcher.cleanup_interval_seconds = 60
        self.dispatcher.pod_cleaner.cleanup_pods = MagicMock()
        mock_time.return_value = 100
        self.dispatcher._run_cleanup()
        self.dispatcher.pod_cleaner.cleanup_pods.assert_called_once()
        mock_time.return_value = 150
        self.dispatcher._run_cleanup()
        self.dispatcher.pod_cleaner.cleanup_pods.assert_called_once()
        mock_time.return_value = 170
        self.dispatcher._run_cleanup()
        self.assertEqual(self.dispatcher.pod_cleaner.cleanup_pods.call_count, 2)

    @patch('main.time.sleep', side_effect=KeyboardInterrupt)
    @patch.object(CronDispatcher, 'initialize_cci_authentication', return_value=True)
    @patch.object(CronDispatcher, '_load_and_apply_config')
    @patch.object(CronDispatcher, 'watch_tasks_config_change', return_value=False)
    @patch.object(CronDispatcher, 'watch_gc_policy_change', return_value=False)
    @patch.object(CronDispatcher, '_run_cleanup')
    def test_run_main_loop(self, mock_run_cleanup, mock_watch_gc, mock_watch_tasks, mock_load_apply, mock_init_auth, mock_sleep):
        """Test one iteration of the main run loop"""
        self.dispatcher.run()
        mock_init_auth.assert_called_once()
        mock_load_apply.assert_called_once()
        mock_watch_tasks.assert_called_once()
        mock_watch_gc.assert_called_once()
        mock_run_cleanup.assert_called_once()
        mock_sleep.assert_called_once_with(30)

    def test_process_task_success(self):
        """Test successful processing of a valid task"""
        self.dispatcher.validate_cron_expression = MagicMock(return_value=True)
        self.dispatcher.validate_configmap_exists = MagicMock(return_value=True)
        self.dispatcher.cron.new = MagicMock()
        result = self.dispatcher._process_task(self.valid_task)
        self.assertTrue(result)
        self.dispatcher.validate_cron_expression.assert_called_once_with('*/5 * * * *')
        self.dispatcher.validate_configmap_exists.assert_called_once_with('test-job-configmap')
        self.dispatcher.cron.new.assert_called_once()

    def test_process_task_disabled(self):
        """Test processing of a disabled task"""
        task = self.valid_task.copy()
        task['state'] = 'off'
        self.dispatcher.validate_cron_expression = MagicMock()
        result = self.dispatcher._process_task(task)
        self.assertFalse(result)
        self.dispatcher.validate_cron_expression.assert_not_called()

    def test_process_task_invalid_schedule(self):
        """Test processing of a task with an invalid cron schedule"""
        self.dispatcher.validate_cron_expression = MagicMock(return_value=False)
        self.dispatcher.validate_configmap_exists = MagicMock()
        result = self.dispatcher._process_task(self.valid_task)
        self.assertFalse(result)
        self.dispatcher.validate_cron_expression.assert_called_once()
        self.dispatcher.validate_configmap_exists.assert_not_called()

    def test_process_task_missing_configmap(self):
        """Test processing of a task with a non-existent configmap"""
        self.dispatcher.validate_cron_expression = MagicMock(return_value=True)
        self.dispatcher.validate_configmap_exists = MagicMock(return_value=False)
        self.dispatcher.cron.new = MagicMock()
        result = self.dispatcher._process_task(self.valid_task)
        self.assertFalse(result)
        self.dispatcher.validate_cron_expression.assert_called_once()
        self.dispatcher.validate_configmap_exists.assert_called_once()
        self.dispatcher.cron.new.assert_not_called()

    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="key: value")
    @patch('main.os.path.exists', return_value=True)
    def test_load_tasks_config_success(self, mock_exists, mock_open):
        """Test successful loading of task configuration"""
        tasks = self.dispatcher.load_tasks_config_from_file()
        self.assertIsNotNone(tasks)
        self.assertEqual(mock_exists.call_count, 1)
        mock_exists.assert_called_once_with(self.dispatcher.tasks_config_file)
        mock_open.assert_called_once_with(self.dispatcher.tasks_config_file, 'r', encoding='utf-8')

    @patch('main.os.path.exists', return_value=False)
    def test_load_tasks_config_not_found(self, mock_exists):
        """Test task config loading when file does not exist"""
        tasks = self.dispatcher.load_tasks_config_from_file()
        self.assertIsNone(tasks)

    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="invalid-yaml")
    @patch('main.os.path.exists', return_value=True)
    def test_load_tasks_config_invalid_yaml(self, mock_exists, mock_open):
        """Test task config loading with invalid YAML content"""
        tasks = self.dispatcher.load_tasks_config_from_file()
        self.assertIsNone(tasks)

    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="global: {success: 1}")
    @patch('main.os.path.exists', return_value=True)
    def test_load_gc_policy_success(self, mock_exists, mock_open):
        """Test successful loading of GC policy"""
        policy = self.dispatcher.load_gc_policy_from_file()
        self.assertEqual(policy['global']['success'], 1)

    @patch('main.os.path.exists', return_value=False)
    def test_load_gc_policy_not_found_uses_default(self, mock_exists):
        """Test that default GC policy is used when file not found"""
        policy = self.dispatcher.load_gc_policy_from_file()
        self.assertIn('global', policy)
        self.assertEqual(policy['global']['success'], 3)

    def test_validate_cron_expression(self):
        """Test cron expression validation"""
        self.assertTrue(self.dispatcher.validate_cron_expression('* * * * *'))
        self.assertTrue(self.dispatcher.validate_cron_expression('0 0 1 1 *'))
        self.assertTrue(self.dispatcher.validate_cron_expression('0 * * * * *'))
        self.assertFalse(self.dispatcher.validate_cron_expression('not a cron'))
        self.assertFalse(self.dispatcher.validate_cron_expression('@daily'))

    @patch('main.execute_command_with_retry')
    def test_validate_configmap_exists(self, mock_execute):
        """Test ConfigMap existence validation"""
        mock_execute.return_value = (True, "output", "")
        self.assertTrue(self.dispatcher.validate_configmap_exists("cm-exists"))
        mock_execute.return_value = (False, "", "not found")
        self.assertFalse(self.dispatcher.validate_configmap_exists("cm-not-found"))
        mock_execute.side_effect = Exception("command failed")
        self.assertFalse(self.dispatcher.validate_configmap_exists("cm-error"))

    def test_parse_interval_to_seconds(self):
        """Test parsing of cleanup interval strings"""
        self.assertEqual(self.dispatcher._parse_interval_to_seconds("60s"), 60)
        self.assertEqual(self.dispatcher._parse_interval_to_seconds("2m"), 120)
        self.assertEqual(self.dispatcher._parse_interval_to_seconds("3h"), 10800)
        self.assertEqual(self.dispatcher._parse_interval_to_seconds("1d"), 86400)
        self.assertEqual(self.dispatcher._parse_interval_to_seconds("abc"), self.dispatcher.DEFAULT_INTERVAL_SECONDS)
        self.assertEqual(self.dispatcher._parse_interval_to_seconds("10s"), self.dispatcher.MIN_INTERVAL_SECONDS)
        self.assertEqual(self.dispatcher._parse_interval_to_seconds("2d"), self.dispatcher.MAX_INTERVAL_SECONDS)

    @patch('main.CronDispatcher')
    def test_main_function_entrypoint(self, mock_dispatcher_class):
        """Test the main function entrypoint"""
        from main import main
        main()
        mock_dispatcher_class.assert_called_once()
        mock_dispatcher_class.return_value.run.assert_called_once()

    def test_process_task_missing_fields(self):
        """Test processing of a task with missing required fields"""
        # Test missing 'name'
        task_no_name = self.valid_task.copy()
        del task_no_name['name']
        self.assertFalse(self.dispatcher._process_task(task_no_name))

        # Test missing 'schedule'
        task_no_schedule = self.valid_task.copy()
        del task_no_schedule['schedule']
        self.assertFalse(self.dispatcher._process_task(task_no_schedule))

        # Test missing 'podDefinitionConfigmap'
        task_no_configmap = self.valid_task.copy()
        del task_no_configmap['podDefinitionConfigmap']
        self.assertFalse(self.dispatcher._process_task(task_no_configmap))

    def test_process_task_invalid_fields(self):
        """Test processing of a task with invalid field values"""
        # Test empty 'name'
        task_empty_name = self.valid_task.copy()
        task_empty_name['name'] = ''
        self.assertFalse(self.dispatcher._process_task(task_empty_name))

        # Test invalid 'schedule'
        task_invalid_schedule = self.valid_task.copy()
        task_invalid_schedule['schedule'] = 'invalid-schedule'
        self.dispatcher.validate_cron_expression = MagicMock(return_value=False)
        self.assertFalse(self.dispatcher._process_task(task_invalid_schedule))
        
    def test_initialize_cci_auth_failure(self):
        """Test CCI authentication initialization failure"""
        with patch('main.CCIAuthManager', side_effect=Exception("CCI Auth Error")):
            self.assertIsNone(self.dispatcher._initialize_cci_auth())
            
    @patch.dict(os.environ, {"GC_DRY_RUN": "true", "GC_BATCH_SIZE": "100"})
    def test_init_with_env_vars(self):
        """Test dispatcher initialization with environment variables"""
        with patch('main.PodCleaner'), patch('main.CCIAuthManager'), patch('main.CronTab'):
            dispatcher = CronDispatcher()
            self.assertTrue(dispatcher.gc_dry_run)
            self.assertEqual(dispatcher.gc_batch_size, 100)

    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="")
    @patch('main.os.path.exists', return_value=True)
    def test_load_tasks_config_empty_file(self, mock_exists, mock_open):
        """Test task config loading with an empty file"""
        tasks = self.dispatcher.load_tasks_config_from_file()
        self.assertIsNone(tasks)

    @patch('main.os.path.exists', side_effect=Exception("os.path.exists error"))
    def test_watch_tasks_config_change_exception(self, mock_exists):
        """Test exception handling in watch_tasks_config_change"""
        self.assertFalse(self.dispatcher.watch_tasks_config_change())

    @patch('main.os.path.exists', side_effect=Exception("os.path.exists error"))
    def test_watch_gc_policy_change_exception(self, mock_exists):
        """Test exception handling in watch_gc_policy_change"""
        self.assertFalse(self.dispatcher.watch_gc_policy_change())

    @patch.object(CronDispatcher, '_process_task', side_effect=Exception("Processing error"))
    def test_update_crontab_exception(self, mock_process_task):
        """Test exception handling in update_crontab"""
        self.dispatcher.update_crontab([self.valid_task])
        # We expect this to not raise an exception, but log an error
        mock_process_task.assert_called_once()
        
    def test_run_main_loop_with_config_changes(self):
        """Test the main run loop with configuration changes"""
        # Mock the instance methods directly instead of the class
        with patch.object(self.dispatcher, 'watch_tasks_config_change', side_effect=[True, False, False]), \
             patch.object(self.dispatcher, 'watch_gc_policy_change', side_effect=[False, True, False]), \
             patch.object(self.dispatcher, 'load_tasks_config_from_file', return_value=[self.valid_task]), \
             patch.object(self.dispatcher, 'update_crontab'), \
             patch.object(self.dispatcher, 'load_gc_policy_from_file', return_value={'cleanupInterval': '1h'}), \
             patch.object(self.dispatcher, 'update_cleanup_interval'), \
             patch.object(self.dispatcher, '_run_cleanup'), \
             patch.object(self.dispatcher, 'initialize_cci_authentication', return_value=True), \
             patch.object(self.dispatcher, '_load_and_apply_config'), \
             patch('main.time.sleep', side_effect=[None, None, KeyboardInterrupt()]):
            
            self.dispatcher.run()

            # Verify initial load is called once during initialization
            self.dispatcher._load_and_apply_config.assert_called_once()
            
            # Verify tasks config is reloaded on first loop iteration
            self.dispatcher.update_crontab.assert_called_once_with([self.valid_task])
            
            # Verify gc policy is reloaded on second loop iteration
            self.dispatcher.update_cleanup_interval.assert_called_once_with({'cleanupInterval': '1h'})

    @patch('main.os.path.exists', return_value=True)
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data=":")
    def test_load_gc_policy_invalid_yaml(self, mock_open, mock_exists):
        """Test GC policy loading with invalid YAML content"""
        policy = self.dispatcher.load_gc_policy_from_file()
        # Should return default policy
        self.assertIn('global', policy)
        self.assertEqual(policy['global']['success'], 3)

    @patch('builtins.open', side_effect=IOError("File not readable"))
    @patch('main.os.path.exists', return_value=True)
    def test_load_config_io_error(self, mock_exists, mock_open):
        """Test config loading with an IOError"""
        self.assertIsNone(self.dispatcher.load_tasks_config_from_file())

if __name__ == '__main__':
    unittest.main()