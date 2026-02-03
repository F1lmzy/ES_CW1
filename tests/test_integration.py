"""
Integration tests for SleepSense Pro
Tests end-to-end flow of all FSR408 components
"""

import unittest
import sys
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from firmware.sensors.ads1115 import ADS1115
from firmware.sensors.fsr408 import FSR408
from firmware.processing.sleep_detector import SleepDetector, SleepState
from firmware.data.data_manager import DataManager


class MockADC:
    """Mock ADS1115 for integration testing"""
    def __init__(self):
        self._voltage = 0.5
        self.mock = True
    
    def read_voltage(self, channel):
        return self._voltage
    
    def read_raw(self, channel):
        # Convert voltage to raw value for ±4.096V range
        return int((self._voltage / 4.096) * 32767)
    
    def is_connected(self):
        return True
    
    def close(self):
        pass


class TestFSRIntegration(unittest.TestCase):
    """Integration tests for FSR components"""
    
    def setUp(self):
        """Set up integrated test environment"""
        self.test_db = "test_integration.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        # Create components
        self.adc = MockADC()
        self.dm = DataManager(db_path=self.test_db)
        self.fsr = FSR408(self.adc, channel=0, data_manager=self.dm)
        self.detector = SleepDetector({
            'empty_threshold': 0.8,
            'movement_threshold': 0.05,
            'sleep_delay': 2  # Short for testing
        })
    
    def tearDown(self):
        """Clean up"""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_end_to_end_reading(self):
        """Test complete reading pipeline"""
        # Simulate occupied bed
        self.adc._voltage = 2.5
        
        # Read sensor
        voltage = self.fsr.get_voltage()
        force_pct = self.fsr.get_force_percentage()
        variance = self.fsr.get_variance()
        
        # Update detector
        state = self.detector.update(voltage, variance)
        
        # Store to database
        result = self.dm.store_reading(voltage, force_pct, state.value, variance)
        self.assertTrue(result)
        
        # Verify stored
        unsynced = self.dm.get_unsynced_readings()
        self.assertEqual(len(unsynced), 1)
        self.assertEqual(unsynced[0]['voltage'], 2.5)
    
    def test_calibration_pipeline(self):
        """Test calibration → storage → load pipeline"""
        # Set calibration values
        baseline = 0.5
        occupied = 2.5
        movement = 0.1
        
        # Save to database
        result = self.dm.save_calibration(baseline, occupied, movement)
        self.assertTrue(result)
        
        # Load calibration into FSR
        loaded = self.fsr.load_calibration()
        self.assertTrue(loaded)
        
        # Verify values
        self.assertEqual(self.fsr.baseline_voltage, baseline)
        self.assertEqual(self.fsr.occupied_threshold, occupied)
        self.assertEqual(self.fsr.movement_threshold, movement)
    
    def test_sleep_state_transitions(self):
        """Test complete sleep state machine"""
        # 1. Empty bed
        self.adc._voltage = 0.5
        variance = 0.01
        state = self.detector.update(self.adc._voltage, variance)
        self.assertEqual(state, SleepState.EMPTY)
        
        # Store reading
        self.dm.store_reading(self.adc._voltage, 0.0, state.value, variance)
        
        # 2. Person gets in bed (moving)
        self.adc._voltage = 2.5
        variance = 0.1  # High variance = movement
        state = self.detector.update(self.adc._voltage, variance)
        self.assertEqual(state, SleepState.MOVING)
        
        self.dm.store_reading(self.adc._voltage, 100.0, state.value, variance)
        
        # 3. Person settles (awake but still)
        self.adc._voltage = 2.5
        variance = 0.01  # Low variance = still
        state = self.detector.update(self.adc._voltage, variance)
        self.assertEqual(state, SleepState.AWAKE)
        
        self.dm.store_reading(self.adc._voltage, 100.0, state.value, variance)
        
        # 4. Time passes, falls asleep
        time.sleep(2.5)  # Wait longer than sleep_delay
        self.adc._voltage = 2.5
        variance = 0.01
        state = self.detector.update(self.adc._voltage, variance)
        self.assertEqual(state, SleepState.ASLEEP)
        
        self.dm.store_reading(self.adc._voltage, 100.0, state.value, variance)
        
        # Verify all states stored
        stats = self.dm.get_stats()
        self.assertEqual(stats['total_readings'], 4)
    
    def test_json_generation(self):
        """Test JSON generation for MQTT"""
        # Create reading
        self.adc._voltage = 2.3
        sensor_data = self.fsr.get_sensor_data()
        sensor_data['state'] = 'Asleep'
        
        # Convert to JSON
        json_str = self.dm.to_json(sensor_data)
        
        # Parse and verify
        import json
        parsed = json.loads(json_str)
        
        self.assertEqual(parsed['voltage'], 2.3)
        self.assertEqual(parsed['sensor_type'], 'fsr408')
        self.assertEqual(parsed['device_id'], 'test_device')
        self.assertIn('timestamp', parsed)
    
    def test_batch_processing(self):
        """Test batch of readings"""
        # Simulate 10 readings at 10Hz
        for i in range(10):
            # Varying voltage to simulate breathing/movement
            self.adc._voltage = 2.0 + 0.1 * (i % 3)
            
            voltage = self.fsr.get_voltage()
            force_pct = self.fsr.get_force_percentage()
            variance = self.fsr.get_variance()
            state = self.detector.update(voltage, variance)
            
            # Store
            self.dm.store_reading(voltage, force_pct, state.value, variance)
            
            time.sleep(0.01)  # Fast for testing
        
        # Verify all stored
        stats = self.dm.get_stats()
        self.assertEqual(stats['total_readings'], 10)
        
        # Verify all unsynced
        unsynced = self.dm.get_unsynced_readings()
        self.assertEqual(len(unsynced), 10)
    
    def test_sync_workflow(self):
        """Test complete sync workflow"""
        # Add readings
        for i in range(5):
            self.dm.store_reading(2.0, 50.0, 'Asleep', 0.02)
        
        # Get unsynced
        unsynced = self.dm.get_unsynced_readings()
        self.assertEqual(len(unsynced), 5)
        
        # Simulate MQTT sync by marking as synced
        ids = [r['id'] for r in unsynced]
        result = self.dm.mark_synced(ids)
        self.assertTrue(result)
        
        # Verify all synced
        unsynced = self.dm.get_unsynced_readings()
        self.assertEqual(len(unsynced), 0)
        
        stats = self.dm.get_stats()
        self.assertEqual(stats['unsynced_readings'], 0)
    
    def test_offline_buffering(self):
        """Test offline buffering with SQLite failure"""
        # Simulate SQLite failure by mocking execute
        original_execute = self.dm._execute_with_retry
        
        call_count = [0]
        def failing_execute(operation):
            call_count[0] += 1
            if call_count[0] <= 3:  # Fail first 3 times
                raise Exception("Database locked")
            return original_execute(operation)
        
        self.dm._execute_with_retry = failing_execute
        
        # Try to store readings
        for i in range(3):
            result = self.dm.store_reading(2.0, 50.0, 'Asleep', 0.02)
            # Should fail to store to DB
            self.assertFalse(result)
        
        # Should be in memory queue
        self.assertEqual(len(self.dm._memory_queue), 3)
        
        # Restore and flush
        self.dm._execute_with_retry = original_execute
        self.dm._flush_memory_queue()
        
        # Verify flushed to database
        stats = self.dm.get_stats()
        self.assertEqual(stats['total_readings'], 3)


class TestMainLoopSimulation(unittest.TestCase):
    """Simulate main loop behavior"""
    
    def setUp(self):
        self.test_db = "test_main_loop.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_main_loop_iterations(self):
        """Simulate multiple main loop iterations"""
        # Create components
        adc = MockADC()
        dm = DataManager(db_path=self.test_db)
        fsr = FSR408(adc, channel=0, data_manager=dm)
        
        # Set calibration
        dm.save_calibration(0.5, 2.5, 0.1)
        fsr.load_calibration()
        
        detector = SleepDetector({
            'empty_threshold': 0.7,
            'movement_threshold': 0.05,
            'sleep_delay': 1
        })
        
        # Simulate 20 iterations
        for i in range(20):
            # Simulate person getting in bed
            if i < 5:
                adc._voltage = 0.5  # Empty
            elif i < 10:
                adc._voltage = 2.5  # Getting in (moving)
            else:
                adc._voltage = 2.5  # Sleeping
            
            # Read and process
            voltage = fsr.get_voltage()
            force_pct = fsr.get_force_percentage()
            variance = fsr.get_variance() if i >= 5 else 0.08
            state = detector.update(voltage, variance)
            
            # Store
            dm.store_reading(voltage, force_pct, state.value, variance)
            
            # Get JSON (for MQTT team)
            sensor_data = fsr.get_sensor_data()
            sensor_data['state'] = state.value
            json_data = dm.to_json(sensor_data)
            
            time.sleep(0.01)
        
        # Verify results
        stats = dm.get_stats()
        self.assertEqual(stats['total_readings'], 20)
        
        # Check state transitions recorded
        recent = dm.get_recent_readings(limit=20)
        states = [r['state'] for r in recent]
        
        # Should have empty, moving, and asleep states
        self.assertIn('Empty Bed', states)
        self.assertIn('Tossing/Turning', states)


class TestSpecCompliance(unittest.TestCase):
    """Test specification compliance"""
    
    def test_spec8_main_py_exists(self):
        """Verify main.py entry point exists (spec #8)"""
        main_path = Path(__file__).parent.parent / "firmware" / "main.py"
        self.assertTrue(main_path.exists())
        
        # Verify it has main() function
        content = main_path.read_text()
        self.assertIn("def main():", content)
        self.assertIn('if __name__ == "__main__":', content)
    
    def test_spec10_no_adafruit(self):
        """Verify no adafruit libraries imported (spec #10)"""
        ads1115_path = Path(__file__).parent.parent / "firmware" / "sensors" / "ads1115.py"
        content = ads1115_path.read_text()
        
        # Should not have adafruit imports
        self.assertNotIn("import adafruit", content)
        self.assertNotIn("from adafruit", content)
    
    def test_spec23_offline_storage(self):
        """Verify SQLite storage for offline functionality (spec #23)"""
        test_db = "test_spec23.db"
        if os.path.exists(test_db):
            os.remove(test_db)
        
        dm = DataManager(db_path=test_db)
        
        # Add readings
        for i in range(5):
            dm.store_reading(2.0, 50.0, 'Asleep', 0.02)
        
        # Verify stored
        stats = dm.get_stats()
        self.assertEqual(stats['total_readings'], 5)
        
        # Cleanup
        os.remove(test_db)
    
    def test_json_api_for_mqtt(self):
        """Verify clean JSON API for MQTT team"""
        test_db = "test_json_api.db"
        if os.path.exists(test_db):
            os.remove(test_db)
        
        dm = DataManager(db_path=test_db, device_id="test_dev", user_id="test_user")
        
        # Create test data
        reading = {
            'voltage': 2.5,
            'force_percent': 75.0,
            'state': 'Asleep',
            'variance': 0.02
        }
        
        # Convert to JSON
        json_str = dm.to_json(reading)
        
        # Verify structure
        import json
        parsed = json.loads(json_str)
        
        required_fields = ['timestamp', 'sensor_type', 'channel', 'voltage', 
                          'force_percent', 'state', 'variance', 'device_id', 'user_id']
        
        for field in required_fields:
            self.assertIn(field, parsed)
        
        # Verify values
        self.assertEqual(parsed['sensor_type'], 'fsr408')
        self.assertEqual(parsed['device_id'], 'test_dev')
        self.assertEqual(parsed['user_id'], 'test_user')
        
        os.remove(test_db)


if __name__ == '__main__':
    unittest.main(verbosity=2)
