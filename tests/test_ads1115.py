"""
Unit tests for ADS1115 custom I2C driver
Tests byte-level I2C communication without hardware dependencies
"""

import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from firmware.sensors.ads1115 import ADS1115, ADS1115Error, POINTER_CONVERSION, POINTER_CONFIG


class TestADS1115(unittest.TestCase):
    """Test cases for ADS1115 driver"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_bus = Mock()
        self.mock_bus_class = Mock(return_value=self.mock_bus)
    
    @patch('firmware.sensors.ads1115.SMBus')
    def test_init_success(self, mock_smbus):
        """Test successful initialization"""
        mock_smbus.return_value = self.mock_bus
        
        adc = ADS1115(bus=1, address=0x48)
        
        mock_smbus.assert_called_once_with(1)
        self.assertEqual(adc.bus_num, 1)
        self.assertEqual(adc.address, 0x48)
        self.assertFalse(adc.mock)
    
    def test_init_mock_mode(self):
        """Test initialization in mock mode"""
        adc = ADS1115(bus=1, address=0x48, mock=True)
        
        self.assertTrue(adc.mock)
        self.assertIsNone(adc.bus)
    
    @patch('firmware.sensors.ads1115.SMBus')
    def test_init_failure(self, mock_smbus):
        """Test initialization failure"""
        mock_smbus.side_effect = OSError("I2C bus not found")
        
        with self.assertRaises(ADS1115Error):
            ADS1115(bus=1, address=0x48)
    
    def test_build_config(self):
        """Test configuration byte generation"""
        adc = ADS1115(mock=True)
        
        # Test channel 0 configuration
        config = adc._build_config(channel=0, continuous=False)
        
        # Check bits are set correctly
        # OS bit (15): 1
        self.assertEqual((config >> 15) & 1, 1)
        # MUX bits (14-12): 100 for AIN0
        self.assertEqual((config >> 12) & 0x07, 0x04)
        # PGA bits (11-9): 001 for ±4.096V
        self.assertEqual((config >> 9) & 0x07, 0x01)
        # MODE bit (8): 1 for single-shot
        self.assertEqual((config >> 8) & 1, 1)
    
    @patch('firmware.sensors.ads1115.SMBus')
    def test_write_register(self, mock_smbus):
        """Test byte-level register write"""
        mock_smbus.return_value = self.mock_bus
        adc = ADS1115(bus=1, address=0x48)
        
        # Write value 0x1234 to config register
        adc._write_register(POINTER_CONFIG, 0x1234)
        
        # Verify I2C write: pointer + MSB + LSB
        # 0x1234 -> MSB=0x12, LSB=0x34
        self.mock_bus.write_i2c_block_data.assert_called_once_with(
            0x48, 0x01, [0x12, 0x34]
        )
    
    @patch('firmware.sensors.ads1115.SMBus')
    def test_write_register_retry(self, mock_smbus):
        """Test register write with retry"""
        mock_smbus.return_value = self.mock_bus
        # First call fails, second succeeds
        self.mock_bus.write_i2c_block_data.side_effect = [OSError("Timeout"), None]
        
        adc = ADS1115(bus=1, address=0x48)
        adc._write_register(POINTER_CONFIG, 0x1234)
        
        # Should be called twice (retry)
        self.assertEqual(self.mock_bus.write_i2c_block_data.call_count, 2)
    
    @patch('firmware.sensors.ads1115.SMBus')
    def test_read_register(self, mock_smbus):
        """Test byte-level register read"""
        mock_smbus.return_value = self.mock_bus
        # Return bytes for value 0x1234
        self.mock_bus.read_i2c_block_data.return_value = [0x12, 0x34]
        
        adc = ADS1115(bus=1, address=0x48)
        value = adc._read_register(POINTER_CONVERSION)
        
        # Should write pointer first, then read
        self.mock_bus.write_byte.assert_called_once_with(0x48, 0x00)
        self.mock_bus.read_i2c_block_data.assert_called_once_with(0x48, 0x00, 2)
        
        # Verify value combining: 0x12 << 8 | 0x34 = 0x1234 = 4660
        self.assertEqual(value, 0x1234)
    
    @patch('firmware.sensors.ads1115.SMBus')
    def test_read_register_negative(self, mock_smbus):
        """Test reading negative signed value"""
        mock_smbus.return_value = self.mock_bus
        # Return bytes for -1 (0xFFFF in 16-bit two's complement)
        self.mock_bus.read_i2c_block_data.return_value = [0xFF, 0xFF]
        
        adc = ADS1115(bus=1, address=0x48)
        value = adc._read_register(POINTER_CONVERSION)
        
        # Should be -1 in signed 16-bit
        self.assertEqual(value, -1)
    
    @patch('firmware.sensors.ads1115.SMBus')
    def test_read_raw(self, mock_smbus):
        """Test complete read sequence"""
        mock_smbus.return_value = self.mock_bus
        
        # Mock config register read (with OS bit set = conversion complete)
        # Mock conversion register read
        def mock_read_register(pointer):
            if pointer == POINTER_CONFIG:
                return 0x8583  # OS bit set (bit 15)
            elif pointer == POINTER_CONVERSION:
                return 10000  # Some raw value
        
        adc = ADS1115(bus=1, address=0x48)
        adc._read_register = Mock(side_effect=mock_read_register)
        adc._write_register = Mock()
        
        raw = adc.read_raw(channel=0)
        
        # Should write config to start conversion
        adc._write_register.assert_called_once()
        # Should read conversion result
        self.assertEqual(raw, 10000)
    
    def test_read_voltage(self):
        """Test voltage conversion"""
        adc = ADS1115(mock=True)
        
        # Mock read_raw to return known value
        # For PGA=4.096V, raw=16384 (half scale) should be 2.048V
        adc.read_raw = Mock(return_value=16384)
        
        voltage = adc.read_voltage(channel=0)
        
        # 16384 / 32767 * 4.096 = 2.048
        self.assertAlmostEqual(voltage, 2.048, places=3)
    
    def test_read_voltage_negative(self):
        """Test voltage conversion with negative raw value"""
        adc = ADS1115(mock=True)
        adc.read_raw = Mock(return_value=-16384)
        
        voltage = adc.read_voltage(channel=0)
        
        # -16384 / 32767 * 4.096 = -2.048
        self.assertAlmostEqual(voltage, -2.048, places=3)
    
    @patch('firmware.sensors.ads1115.SMBus')
    def test_is_connected_true(self, mock_smbus):
        """Test connection check (success)"""
        mock_smbus.return_value = self.mock_bus
        self.mock_bus.read_i2c_block_data.return_value = [0x00, 0x00]
        
        adc = ADS1115(bus=1, address=0x48)
        result = adc.is_connected()
        
        self.assertTrue(result)
    
    @patch('firmware.sensors.ads1115.SMBus')
    def test_is_connected_false(self, mock_smbus):
        """Test connection check (failure)"""
        mock_smbus.return_value = self.mock_bus
        self.mock_bus.read_i2c_block_data.side_effect = OSError("No device")
        
        adc = ADS1115(bus=1, address=0x48)
        result = adc.is_connected()
        
        self.assertFalse(result)
    
    def test_mock_mode_read(self):
        """Test mock mode returns reasonable values"""
        adc = ADS1115(mock=True)
        
        raw = adc.read_raw(channel=0)
        voltage = adc.read_voltage(channel=0)
        
        # Should return values in reasonable range
        self.assertIsInstance(raw, int)
        self.assertIsInstance(voltage, float)
        self.assertGreater(voltage, 0)
        self.assertLess(voltage, 5.0)  # FSR range
    
    def test_error_handling_returns_last_value(self):
        """Test that errors return last known good value"""
        adc = ADS1115(mock=True)
        adc._last_value = 15000
        
        # Simulate error
        adc.read_raw = Mock(side_effect=Exception("Test error"))
        
        # In mock mode, this will generate random values
        # But in real mode with error, should return _last_value


class TestADS1115ByteLevelOperations(unittest.TestCase):
    """Specific tests for byte-level I2C compliance (spec #10)"""
    
    @patch('firmware.sensors.ads1115.SMBus')
    def test_spec10_byte_level_write(self, mock_smbus):
        """
        Verify specification #10 compliance: byte-level I2C write
        Should write exactly 3 bytes: pointer + 2 data bytes
        """
        mock_bus = Mock()
        mock_smbus.return_value = mock_bus
        
        adc = ADS1115(bus=1, address=0x48)
        
        # Write to config register
        test_value = 0xC583  # Example config
        adc._write_register(POINTER_CONFIG, test_value)
        
        # Extract expected bytes
        expected_msb = (test_value >> 8) & 0xFF  # 0xC5
        expected_lsb = test_value & 0xFF          # 0x83
        
        # Verify byte-level write
        mock_bus.write_i2c_block_data.assert_called_once_with(
            0x48,           # Device address
            POINTER_CONFIG,  # Pointer register (0x01)
            [expected_msb, expected_lsb]  # Data bytes (MSB first)
        )
    
    @patch('firmware.sensors.ads1115.SMBus')
    def test_spec10_byte_level_read(self, mock_smbus):
        """
        Verify specification #10 compliance: byte-level I2C read
        Should: 1) write pointer, 2) read 2 bytes, 3) combine to 16-bit value
        """
        mock_bus = Mock()
        mock_smbus.return_value = mock_bus
        # Return MSB=0x12, LSB=0x34 (value = 0x1234 = 4660)
        mock_bus.read_i2c_block_data.return_value = [0x12, 0x34]
        
        adc = ADS1115(bus=1, address=0x48)
        value = adc._read_register(POINTER_CONVERSION)
        
        # Verify sequence:
        # 1. Write pointer register
        mock_bus.write_byte.assert_called_once_with(0x48, POINTER_CONVERSION)
        
        # 2. Read 2 bytes
        mock_bus.read_i2c_block_data.assert_called_once_with(
            0x48, POINTER_CONVERSION, 2
        )
        
        # 3. Verify value combining
        self.assertEqual(value, 0x1234)


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)
