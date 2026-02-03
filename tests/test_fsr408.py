"""
Unit tests for FSR408 sensor interface
Tests calibration, force calculation, and occupancy detection
"""

import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from firmware.sensors.fsr408 import FSR408, FSR408Error
from firmware.sensors.ads1115 import ADS1115
from firmware.data.data_manager import DataManager


class MockADC:
    """Mock ADS1115 for testing"""
    def __init__(self):
        self.voltage = 0.5  # Default baseline
    
    def read_voltage(self, channel):
        return self.voltage
    
    def is_connected(self):
        return True


class TestFSR408(unittest.TestCase):
    """Test cases for FSR408 interface"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_adc = MockADC()
        self.fsr = FSR408(self.mock_adc, channel=0)
    
    def test_init(self):
        """Test initialization"""
        self.assertEqual(self.fsr.channel, 0)
        self.assertEqual(self.fsr.adc, self.mock_adc)
        self.assertIsNone(self.fsr.data_manager)
    
    def test_get_voltage(self):
        """Test voltage reading"""
        self.mock_adc.voltage = 2.5
        voltage = self.fsr.get_voltage()
        
        self.assertEqual(voltage, 2.5)
    
    def test_get_force_percentage_baseline(self):
        """Test force calculation at baseline"""
        # At baseline (default 0.5V), should be 0%
        self.mock_adc.voltage = 0.5
        self.fsr.baseline_voltage = 0.5
        self.fsr.occupied_threshold = 2.5
        
        pct = self.fsr.get_force_percentage()
        self.assertEqual(pct, 0.0)
    
    def test_get_force_percentage_occupied(self):
        """Test force calculation at occupied threshold"""
        # At occupied threshold, should be 100%
        self.mock_adc.voltage = 2.5
        self.fsr.baseline_voltage = 0.5
        self.fsr.occupied_threshold = 2.5
        
        pct = self.fsr.get_force_percentage()
        self.assertEqual(pct, 100.0)
    
    def test_get_force_percentage_mid_range(self):
        """Test force calculation at midpoint"""
        # At midpoint (1.5V), should be 50%
        self.mock_adc.voltage = 1.5
        self.fsr.baseline_voltage = 0.5
        self.fsr.occupied_threshold = 2.5
        
        pct = self.fsr.get_force_percentage()
        self.assertEqual(pct, 50.0)
    
    def test_get_force_percentage_clamping(self):
        """Test force percentage clamping"""
        self.fsr.baseline_voltage = 0.5
        self.fsr.occupied_threshold = 2.5
        
        # Below baseline
        self.mock_adc.voltage = 0.0
        pct = self.fsr.get_force_percentage()
        self.assertEqual(pct, 0.0)
        
        # Above occupied
        self.mock_adc.voltage = 3.0
        pct = self.fsr.get_force_percentage()
        self.assertEqual(pct, 100.0)
    
    def test_is_occupied_true(self):
        """Test occupancy detection (occupied)"""
        self.mock_adc.voltage = 2.5
        self.fsr.baseline_voltage = 0.5
        self.fsr.occupied_threshold = 2.5
        
        occupied = self.fsr.is_occupied(threshold_percent=20.0)
        self.assertTrue(occupied)
    
    def test_is_occupied_false(self):
        """Test occupancy detection (empty)"""
        self.mock_adc.voltage = 0.6
        self.fsr.baseline_voltage = 0.5
        self.fsr.occupied_threshold = 2.5
        
        occupied = self.fsr.is_occupied(threshold_percent=20.0)
        self.assertFalse(occupied)
    
    def test_get_variance_initial(self):
        """Test variance with insufficient data"""
        variance = self.fsr.get_variance()
        self.assertEqual(variance, 0.0)
    
    def test_get_variance_with_data(self):
        """Test variance calculation"""
        # Add some readings
        voltages = [1.0, 1.1, 1.2, 1.1, 1.0]
        for v in voltages:
            self.mock_adc.voltage = v
            self.fsr.get_variance()
        
        variance = self.fsr.get_variance()
        self.assertGreater(variance, 0.0)
    
    def test_get_sensor_data(self):
        """Test sensor data dictionary generation"""
        self.mock_adc.voltage = 2.0
        self.fsr.baseline_voltage = 0.5
        self.fsr.occupied_threshold = 2.5
        self.fsr.calibrated_at = "2026-02-03 12:00:00"
        
        data = self.fsr.get_sensor_data()
        
        self.assertIn('voltage', data)
        self.assertIn('force_percent', data)
        self.assertIn('variance', data)
        self.assertIn('is_occupied', data)
        self.assertIn('channel', data)
        self.assertIn('calibrated', data)
        
        self.assertEqual(data['voltage'], 2.0)
        self.assertEqual(data['channel'], 0)
        self.assertTrue(data['calibrated'])


class TestFSR408Calibration(unittest.TestCase):
    """Test calibration functionality"""
    
    def setUp(self):
        """Set up with mock data manager"""
        self.mock_adc = MockADC()
        self.mock_dm = Mock()
        self.fsr = FSR408(self.mock_adc, channel=0, data_manager=self.mock_dm)
    
    def test_is_calibrated_true(self):
        """Test calibration check (calibrated)"""
        self.mock_dm.load_calibration.return_value = {
            'baseline_voltage': 0.5,
            'occupied_threshold': 2.5,
            'movement_threshold': 0.1
        }
        
        result = self.fsr.is_calibrated()
        self.assertTrue(result)
    
    def test_is_calibrated_false(self):
        """Test calibration check (not calibrated)"""
        self.mock_dm.load_calibration.return_value = None
        
        result = self.fsr.is_calibrated()
        self.assertFalse(result)
    
    def test_load_calibration(self):
        """Test loading calibration"""
        cal_data = {
            'baseline_voltage': 0.5,
            'occupied_threshold': 2.5,
            'movement_threshold': 0.1,
            'calibrated_at': '2026-02-03 12:00:00'
        }
        self.mock_dm.load_calibration.return_value = cal_data
        
        result = self.fsr.load_calibration()
        
        self.assertTrue(result)
        self.assertEqual(self.fsr.baseline_voltage, 0.5)
        self.assertEqual(self.fsr.occupied_threshold, 2.5)
        self.assertEqual(self.fsr.movement_threshold, 0.1)
    
    @patch('builtins.input', return_value='')
    def test_calibrate(self, mock_input):
        """Test calibration routine"""
        # Simulate baseline reading (no force)
        def voltage_sequence():
            values = [0.5] * 50 + [2.5] * 50  # First 50 = baseline, next 50 = occupied
            for v in values:
                yield v
        
        voltages = voltage_sequence()
        self.mock_adc.read_voltage = lambda channel: next(voltages)
        
        result = self.fsr.calibrate(interactive=False)
        
        self.assertIn('baseline_voltage', result)
        self.assertIn('occupied_threshold', result)
        self.assertIn('movement_threshold', result)
        
        # Verify saved to data manager
        self.mock_dm.save_calibration.assert_called_once()
    
    def test_get_calibration(self):
        """Test getting calibration data"""
        self.fsr.baseline_voltage = 0.5
        self.fsr.occupied_threshold = 2.5
        self.fsr.movement_threshold = 0.1
        self.fsr.calibrated_at = '2026-02-03 12:00:00'
        
        cal = self.fsr.get_calibration()
        
        self.assertEqual(cal['baseline_voltage'], 0.5)
        self.assertEqual(cal['occupied_threshold'], 2.5)
        self.assertEqual(cal['movement_threshold'], 0.1)


class TestFSR408ErrorHandling(unittest.TestCase):
    """Test error handling"""
    
    def setUp(self):
        self.mock_adc = MockADC()
        self.fsr = FSR408(self.mock_adc, channel=0)
        self.fsr._last_reading = 2.0
    
    def test_adc_error_returns_last_value(self):
        """Test that ADC errors return last known value"""
        from firmware.sensors.ads1115 import ADS1115Error
        
        # Make ADC raise error
        def raise_error(channel):
            raise ADS1115Error("Test error")
        
        self.mock_adc.read_voltage = raise_error
        
        voltage = self.fsr.get_voltage()
        
        # Should return last known value (2.0)
        self.assertEqual(voltage, 2.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
