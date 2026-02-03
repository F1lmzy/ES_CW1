"""
FSR408 Force Sensitive Resistor Interface
Handles sensor calibration, force calculation, and occupancy detection.
Calibration data persisted to SQLite via DataManager.

FSR408 Characteristics:
- Resistance decreases with applied force
- Connected to ADS1115 via voltage divider circuit
- Optimal range: 0.1N to 10N (10g to 1kg)
"""

import time
import logging
from typing import Optional, Dict, List
from collections import deque
import statistics

from .ads1115 import ADS1115, ADS1115Error

logger = logging.getLogger(__name__)


class FSR408Error(Exception):
    """Custom exception for FSR408 errors"""
    pass


class FSR408:
    """
    FSR408 Force Sensitive Resistor interface.
    
    Features:
    - Dynamic calibration routine (first-time only, stored in SQLite)
    - Force percentage calculation (0-100%)
    - Occupancy detection with configurable threshold
    - Movement detection via variance calculation
    - Rolling window for noise reduction
    
    Hardware Setup:
    - FSR408 connected in voltage divider with 10kΩ resistor
    - Divider output connected to ADS1115 AIN0
    - ADS1115 PGA set to ±4.096V for optimal resolution
    """
    
    # Default calibration values (will be overwritten after calibration)
    DEFAULT_BASELINE = 0.5      # Voltage when no force applied (V)
    DEFAULT_OCCUPIED = 2.0      # Voltage when occupied (V)
    DEFAULT_MOVEMENT = 0.05     # Voltage variance threshold for movement
    
    def __init__(self, adc: ADS1115, channel: int = 0, 
                 window_size: int = 20, data_manager=None):
        """
        Initialize FSR408 sensor.
        
        Args:
            adc: ADS1115 ADC instance
            channel: ADC channel (0-3, default 0)
            window_size: Rolling window size for variance calculation
            data_manager: DataManager instance for calibration storage (optional)
        """
        self.adc = adc
        self.channel = channel
        self.data_manager = data_manager
        self.window_size = window_size
        
        # Calibration values
        self.baseline_voltage = self.DEFAULT_BASELINE
        self.occupied_threshold = self.DEFAULT_OCCUPIED
        self.movement_threshold = self.DEFAULT_MOVEMENT
        self.calibrated_at = None
        
        # Data buffers
        self.voltage_buffer = deque(maxlen=window_size)
        self._last_reading = 0.0
        
        logger.info(f"FSR408 initialized on channel {channel}")
    
    def is_calibrated(self) -> bool:
        """
        Check if sensor has valid calibration data.
        
        Returns:
            True if calibration data exists, False otherwise
        """
        if self.data_manager:
            cal = self.data_manager.load_calibration()
            if cal:
                return True
        return False
    
    def load_calibration(self) -> bool:
        """
        Load calibration from SQLite storage.
        
        Returns:
            True if calibration loaded successfully, False otherwise
        """
        if not self.data_manager:
            logger.warning("No data manager available, using default calibration")
            return False
        
        cal = self.data_manager.load_calibration()
        if cal:
            self.baseline_voltage = cal['baseline_voltage']
            self.occupied_threshold = cal['occupied_threshold']
            self.movement_threshold = cal['movement_threshold']
            self.calibrated_at = cal['calibrated_at']
            logger.info(f"Calibration loaded from {self.calibrated_at}")
            return True
        
        logger.info("No calibration found, calibration required")
        return False
    
    def calibrate(self, interactive: bool = True) -> Dict:
        """
        Run calibration routine to determine sensor thresholds.
        
        First-time calibration routine:
        1. Measure baseline (no weight on bed)
        2. Measure occupied threshold (person lying on bed)
        3. Calculate movement threshold
        4. Save to SQLite via data_manager
        
        Args:
            interactive: If True, prompts user via console. If False, uses timing.
            
        Returns:
            Dictionary with calibration values
        """
        logger.info("=" * 50)
        logger.info("FSR408 Calibration Routine")
        logger.info("=" * 50)
        
        if interactive:
            input("\nStep 1: Ensure bed is EMPTY (no weight). Press ENTER to start...")
        else:
            logger.info("Auto-calibration: measuring baseline in 5 seconds...")
            time.sleep(5)
        
        # Measure baseline (no force)
        baseline_samples = self._collect_samples(50, 5.0)
        self.baseline_voltage = statistics.mean(baseline_samples)
        baseline_std = statistics.stdev(baseline_samples) if len(baseline_samples) > 1 else 0
        
        logger.info(f"Baseline measured: {self.baseline_voltage:.3f}V (±{baseline_std:.3f}V)")
        
        if interactive:
            input("\nStep 2: Lie on bed in normal sleeping position. Press ENTER when ready...")
        else:
            logger.info("Auto-calibration: measuring occupied state...")
            time.sleep(2)
        
        # Measure occupied state
        occupied_samples = self._collect_samples(50, 5.0)
        self.occupied_threshold = statistics.mean(occupied_samples)
        occupied_std = statistics.stdev(occupied_samples) if len(occupied_samples) > 1 else 0
        
        logger.info(f"Occupied measured: {self.occupied_threshold:.3f}V (±{occupied_std:.3f}V)")
        
        # Calculate movement threshold (10% of voltage range, minimum 0.05V)
        voltage_range = abs(self.occupied_threshold - self.baseline_voltage)
        self.movement_threshold = max(voltage_range * 0.10, 0.05)
        
        logger.info(f"Movement threshold: {self.movement_threshold:.3f}V")
        
        # Validation
        if voltage_range < 0.5:
            logger.warning("WARNING: Small voltage range detected. Check sensor placement.")
        
        # Save calibration
        self.calibrated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        
        calibration_data = {
            'baseline_voltage': self.baseline_voltage,
            'occupied_threshold': self.occupied_threshold,
            'movement_threshold': self.movement_threshold,
            'calibrated_at': self.calibrated_at
        }
        
        if self.data_manager:
            self.data_manager.save_calibration(**calibration_data)
            logger.info("Calibration saved to SQLite")
        
        logger.info("=" * 50)
        logger.info("Calibration Complete!")
        logger.info("=" * 50)
        
        return calibration_data
    
    def _collect_samples(self, count: int, duration: float) -> List[float]:
        """
        Collect multiple voltage samples over time.
        
        Args:
            count: Number of samples to collect
            duration: Total duration for collection (seconds)
            
        Returns:
            List of voltage readings
        """
        samples = []
        interval = duration / count
        
        for i in range(count):
            try:
                voltage = self.get_voltage()
                samples.append(voltage)
            except FSR408Error:
                # Skip failed readings
                pass
            time.sleep(interval)
        
        return samples
    
    def get_voltage(self) -> float:
        """
        Read current voltage from FSR sensor.
        
        Returns:
            Voltage in volts
            
        Raises:
            FSR408Error: If ADC read fails
        """
        try:
            voltage = self.adc.read_voltage(self.channel)
            self._last_reading = voltage
            return voltage
        except ADS1115Error as e:
            logger.error(f"Failed to read FSR voltage: {e}")
            # Return last known good value
            return self._last_reading
        except Exception as e:
            logger.error(f"Unexpected error reading FSR: {e}")
            return self._last_reading
    
    def get_force_percentage(self) -> float:
        """
        Calculate force as percentage of calibrated range.
        
        Returns:
            Force percentage (0-100%)
            - 0%: No force (baseline)
            - 100%: Full occupied threshold
        """
        voltage = self.get_voltage()
        
        # Calculate percentage
        voltage_range = self.occupied_threshold - self.baseline_voltage
        
        if voltage_range <= 0:
            return 0.0
        
        percentage = ((voltage - self.baseline_voltage) / voltage_range) * 100.0
        
        # Clamp to 0-100%
        return max(0.0, min(100.0, percentage))
    
    def is_occupied(self, threshold_percent: float = 20.0) -> bool:
        """
        Check if bed is occupied based on force threshold.
        
        Args:
            threshold_percent: Force percentage threshold for occupancy (default 20%)
            
        Returns:
            True if occupied, False otherwise
        """
        force_pct = self.get_force_percentage()
        return force_pct > threshold_percent
    
    def get_variance(self, window_size: Optional[int] = None) -> float:
        """
        Calculate variance of recent readings for movement detection.
        
        Args:
            window_size: Number of samples to use (default: self.window_size)
            
        Returns:
            Variance of voltage readings (0.0 if insufficient data)
        """
        size = window_size or self.window_size
        
        # Add current reading to buffer
        voltage = self.get_voltage()
        self.voltage_buffer.append(voltage)
        
        # Need at least 2 samples for variance
        if len(self.voltage_buffer) < 2:
            return 0.0
        
        # Calculate variance using recent samples
        recent = list(self.voltage_buffer)[-size:]
        
        if len(recent) < 2:
            return 0.0
        
        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        
        return variance
    
    def get_calibration(self) -> Dict:
        """
        Get current calibration values.
        
        Returns:
            Dictionary with calibration data
        """
        return {
            'baseline_voltage': self.baseline_voltage,
            'occupied_threshold': self.occupied_threshold,
            'movement_threshold': self.movement_threshold,
            'calibrated_at': self.calibrated_at
        }
    
    def get_sensor_data(self) -> Dict:
        """
        Get complete sensor data for MQTT transmission.
        
        Returns:
            Dictionary with all sensor readings and metadata
            Format matches data_manager.to_json() expectations
        """
        voltage = self.get_voltage()
        force_pct = self.get_force_percentage()
        variance = self.get_variance()
        
        return {
            'voltage': voltage,
            'force_percent': force_pct,
            'variance': variance,
            'is_occupied': self.is_occupied(),
            'channel': self.channel,
            'calibrated': self.calibrated_at is not None
        }


# Convenience function for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test with mock ADC
    adc = ADS1115(mock=True)
    fsr = FSR408(adc)
    
    print(f"\nFSR408 Test (Mock Mode)")
    print(f"Calibrated: {fsr.is_calibrated()}")
    
    # Simulate readings
    for i in range(10):
        data = fsr.get_sensor_data()
        print(f"Sample {i+1}: {data['voltage']:.3f}V, "
              f"{data['force_percent']:.1f}%, "
              f"Occupied: {data['is_occupied']}")
        time.sleep(0.5)
