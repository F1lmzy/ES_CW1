"""
Sleep State Detection and Processing
Implements sleep state machine for occupancy and sleep quality monitoring.
Extracted and refactored from main.py to meet specification #8 code structure.
"""

import time
import logging
from typing import Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class SleepState(Enum):
    """Sleep state enumeration"""
    EMPTY = "Empty Bed"
    AWAKE = "Present (Awake)"
    ASLEEP = "Asleep"
    MOVING = "Tossing/Turning"


class SleepDetector:
    """
    Sleep state detector using FSR sensor data.
    
    Implements state machine logic:
    1. EMPTY: No weight detected (voltage below baseline threshold)
    2. MOVING: High variance indicates movement
    3. AWAKE: Person present but recently moved
    4. ASLEEP: Person still for > sleep_delay seconds
    
    Based on original implementation from main.py
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize sleep detector.
        
        Args:
            config: Configuration dictionary with thresholds:
                - empty_threshold: Voltage below which bed is empty
                - movement_threshold: Variance above which indicates movement
                - sleep_delay: Seconds of stillness before considered asleep
        """
        # Default configuration (will be overridden by calibration)
        self.config = config or {}
        
        # Thresholds
        self.empty_threshold = self.config.get('empty_threshold', 0.8)
        self.movement_threshold = self.config.get('movement_threshold', 0.05)
        self.sleep_delay = self.config.get('sleep_delay', 60)  # seconds
        
        # State tracking
        self.current_state = SleepState.EMPTY
        self.last_move_time = time.time()
        self.state_start_time = time.time()
        self.last_voltage = 0.0
        self.last_variance = 0.0
        
        logger.info(f"SleepDetector initialized")
        logger.info(f"  Empty threshold: {self.empty_threshold:.3f}V")
        logger.info(f"  Movement threshold: {self.movement_threshold:.3f}V")
        logger.info(f"  Sleep delay: {self.sleep_delay}s")
    
    def update(self, voltage: float, variance: float) -> SleepState:
        """
        Update sleep state based on new sensor readings.
        
        Args:
            voltage: Current voltage reading from FSR
            variance: Current variance (movement indicator)
            
        Returns:
            Current sleep state
        """
        self.last_voltage = voltage
        self.last_variance = variance
        
        now = time.time()
        
        # Logic tree (from original main.py)
        if voltage < self.empty_threshold:
            # Bed is empty (voltage too low for occupied state)
            new_state = SleepState.EMPTY
            self.last_move_time = now  # Reset sleep timer
            
        elif variance > self.movement_threshold:
            # High variance means movement detected
            new_state = SleepState.MOVING
            self.last_move_time = now  # Reset sleep timer
            
        else:
            # Person is present but variance is low (still)
            time_still = now - self.last_move_time
            
            if time_still > self.sleep_delay:
                # Been still long enough to be asleep
                new_state = SleepState.ASLEEP
            else:
                # Present but recently moved or not still long enough
                new_state = SleepState.AWAKE
        
        # Track state changes
        if new_state != self.current_state:
            time_in_prev_state = now - self.state_start_time
            logger.info(f"State change: {self.current_state.value} -> {new_state.value} "
                       f"(was {time_in_prev_state:.1f}s in previous state)")
            self.current_state = new_state
            self.state_start_time = now
        
        return self.current_state
    
    def get_state(self) -> SleepState:
        """Get current sleep state"""
        return self.current_state
    
    def get_state_name(self) -> str:
        """Get current sleep state as string"""
        return self.current_state.value
    
    def get_time_in_state(self) -> float:
        """Get seconds spent in current state"""
        return time.time() - self.state_start_time
    
    def get_time_since_last_movement(self) -> float:
        """Get seconds since last detected movement"""
        return time.time() - self.last_move_time
    
    def is_occupied(self) -> bool:
        """Check if bed is currently occupied (any state except EMPTY)"""
        return self.current_state != SleepState.EMPTY
    
    def is_sleeping(self) -> bool:
        """Check if person is currently asleep"""
        return self.current_state == SleepState.ASLEEP
    
    def get_stats(self) -> Dict:
        """
        Get current detection statistics.
        
        Returns:
            Dictionary with current state information
        """
        return {
            'state': self.current_state.value,
            'state_code': self.current_state.name,
            'time_in_state': self.get_time_in_state(),
            'time_since_movement': self.get_time_since_last_movement(),
            'last_voltage': self.last_voltage,
            'last_variance': self.last_variance,
            'is_occupied': self.is_occupied(),
            'is_sleeping': self.is_sleeping()
        }
    
    def reset(self):
        """Reset detector to initial state"""
        self.current_state = SleepState.EMPTY
        self.last_move_time = time.time()
        self.state_start_time = time.time()
        logger.info("SleepDetector reset")


# Convenience function for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("\nSleepDetector Test")
    
    # Create detector with test thresholds
    detector = SleepDetector({
        'empty_threshold': 1.0,
        'movement_threshold': 0.05,
        'sleep_delay': 3  # Short for testing
    })
    
    # Simulate different scenarios
    test_scenarios = [
        # (voltage, variance, description)
        (0.5, 0.01, "Empty bed (low voltage)"),
        (2.5, 0.08, "Person moving"),
        (2.5, 0.02, "Person still (awake)"),
        (2.5, 0.02, "Person still (transition to asleep)"),
        (2.5, 0.02, "Person asleep"),
        (2.5, 0.10, "Person woke up"),
        (0.6, 0.01, "Person left bed"),
    ]
    
    for voltage, variance, desc in test_scenarios:
        state = detector.update(voltage, variance)
        print(f"{desc:30s} -> {state.value} (still for {detector.get_time_since_last_movement():.1f}s)")
        time.sleep(1)
