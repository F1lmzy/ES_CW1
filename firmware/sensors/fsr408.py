"""
FSR408 Force Sensitive Resistor Interface
Handles sensor calibration, force calculation, and occupancy detection.
Calibration data persisted to SQLite via DataManager.

FSR408 Characteristics:
- Resistance decreases with applied force
- Connected to ADS1115 via voltage divider circuit
- Optimal range: 0.1N to 10N (10g to 1kg)

SIMULATION MODE:
- Automatically enabled when sensor reads 0V consistently
- Generates realistic sleep pattern data for testing/development
- Simulates: getting in bed, sleeping, tossing/turning, getting up
"""

import logging
import math
import random
import statistics
import time
from collections import deque
from typing import Dict, List, Optional

from .ads1115 import ADS1115, ADS1115Error

logger = logging.getLogger(__name__)


class FSR408Error(Exception):
    """Custom exception for FSR408 errors"""

    pass


class FSR408:
    """
    FSR408 Force Sensitive Resistor interface with simulation fallback.

    Features:
    - Dynamic calibration routine (first-time only, stored in SQLite)
    - Force percentage calculation (0-100%)
    - Occupancy detection with configurable threshold
    - Movement detection via variance calculation
    - Rolling window for noise reduction
    - **SIMULATION MODE** when hardware fails

    Hardware Setup:
    - FSR408 connected in voltage divider with 10kΩ resistor
    - Divider output connected to ADS1115 AIN0
    - ADS1115 PGA set to ±4.096V for optimal resolution
    """

    # Default calibration values (will be overwritten after calibration)
    DEFAULT_BASELINE = 0.5  # Voltage when no force applied (V)
    DEFAULT_OCCUPIED = 2.0  # Voltage when occupied (V)
    DEFAULT_MOVEMENT = 0.05  # Voltage variance threshold for movement

    def __init__(
        self,
        adc: ADS1115,
        channel: int = 0,
        window_size: int = 20,
        data_manager=None,
        simulation_mode: bool = False,
    ):
        """
        Initialize FSR408 sensor.

        Args:
            adc: ADS1115 ADC instance
            channel: ADC channel (0-3, default 0)
            window_size: Rolling window size for variance calculation
            data_manager: DataManager instance for calibration storage (optional)
            simulation_mode: Force simulation mode (auto-enables if sensor broken)
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

        # Simulation mode tracking
        self.simulation_mode = simulation_mode
        self._zero_reading_count = 0
        self._simulation_start_time = None
        self._simulation_state = (
            "empty"  # empty, getting_in, occupied, restless, getting_up
        )
        self._simulation_state_start = time.time()
        self._simulation_base_voltage = 0.5  # Baseline for simulation

        logger.info(f"FSR408 initialized on channel {channel}")
        if simulation_mode:
            logger.warning("FSR408 starting in SIMULATION MODE")
            self._enable_simulation_mode()

    def _check_for_broken_sensor(self, voltage: float) -> None:
        """
        Check if sensor appears to be broken and enable simulation mode.

        Args:
            voltage: Current voltage reading
        """
        if self.simulation_mode:
            return  # Already in simulation mode

        # Check if voltage is consistently 0
        if voltage < 0.01:
            self._zero_reading_count += 1
        else:
            self._zero_reading_count = 0

        # If 10 consecutive zero readings, assume sensor is broken
        if self._zero_reading_count >= 10:
            logger.error("⚠️  FSR SENSOR APPEARS BROKEN - ENABLING SIMULATION MODE ⚠️")
            logger.error("Sensor has read 0V for 10 consecutive readings")
            logger.error("Switching to simulated sleep pattern data")
            logger.error("Replace FSR sensor for real data collection")
            self._enable_simulation_mode()

    def _enable_simulation_mode(self) -> None:
        """Enable simulation mode and initialize simulation state."""
        self.simulation_mode = True
        self._simulation_start_time = time.time()
        self._simulation_state = "empty"
        self._simulation_state_start = time.time()

        logger.warning("=" * 70)
        logger.warning("  SIMULATION MODE ENABLED")
        logger.warning("  Generating realistic sleep pattern data")
        logger.warning("  This is NOT real sensor data!")
        logger.warning("=" * 70)

    def _get_simulated_voltage(self) -> float:
        """
        Generate realistic simulated voltage readings.

        Simulates a complete sleep cycle:
        - Empty bed (0-10min): ~0.5V
        - Getting in bed (10-15min): Rising 0.5V → 2.0V
        - Occupied/sleeping (15-40min): ~2.0V with small variations
        - Restless period (40-45min): Higher variance, 1.5V-2.5V
        - Deep sleep (45-60min): ~2.0V, low variance
        - Getting up (60-65min): Falling 2.0V → 0.5V
        - Empty again: ~0.5V

        Returns:
            Simulated voltage value
        """
        elapsed = time.time() - self._simulation_start_time
        state_time = time.time() - self._simulation_state_start

        # State machine for sleep simulation
        if self._simulation_state == "empty":
            # Empty bed - low voltage with minimal noise
            base = 0.5
            noise = random.gauss(0, 0.02)
            voltage = base + noise

            # Transition: After 10-60 seconds, simulate getting in bed
            if state_time > random.uniform(10, 60):
                self._simulation_state = "getting_in"
                self._simulation_state_start = time.time()
                logger.info("🛏️  SIMULATION: Person getting into bed")

        elif self._simulation_state == "getting_in":
            # Getting in bed - voltage rises
            progress = min(state_time / 5.0, 1.0)  # 5 second transition
            base = 0.5 + (1.5 * progress)  # 0.5 → 2.0V
            noise = random.gauss(0, 0.1)  # Higher noise during movement
            voltage = base + noise

            # Transition: After getting in, become occupied
            if progress >= 1.0:
                self._simulation_state = "occupied"
                self._simulation_state_start = time.time()
                logger.info("😴 SIMULATION: Person settled in bed (sleeping)")

        elif self._simulation_state == "occupied":
            # Occupied/sleeping - stable voltage with breathing variations
            breathing = 0.05 * math.sin(elapsed * 0.3)  # Slow breathing
            noise = random.gauss(0, 0.03)
            voltage = 2.0 + breathing + noise

            # Transition: Random chance of restlessness
            if state_time > 20 and random.random() < 0.02:  # 2% chance per reading
                self._simulation_state = "restless"
                self._simulation_state_start = time.time()
                logger.info("🔄 SIMULATION: Person moving (restless sleep)")

            # Transition: After 30-90 seconds, might get up
            elif state_time > random.uniform(30, 90) and random.random() < 0.05:
                self._simulation_state = "getting_up"
                self._simulation_state_start = time.time()
                logger.info("🚶 SIMULATION: Person getting out of bed")

        elif self._simulation_state == "restless":
            # Restless - higher variance, shifting position
            shift = 0.3 * math.sin(elapsed * 2)  # Faster movement
            noise = random.gauss(0, 0.15)  # High noise
            voltage = 1.8 + shift + noise

            # Transition: Return to stable sleep after 5-10 seconds
            if state_time > random.uniform(5, 10):
                self._simulation_state = "occupied"
                self._simulation_state_start = time.time()
                logger.info("😴 SIMULATION: Person settled again")

        elif self._simulation_state == "getting_up":
            # Getting up - voltage falls
            progress = min(state_time / 5.0, 1.0)  # 5 second transition
            base = 2.0 - (1.5 * progress)  # 2.0 → 0.5V
            noise = random.gauss(0, 0.1)  # Higher noise during movement
            voltage = base + noise

            # Transition: Back to empty
            if progress >= 1.0:
                self._simulation_state = "empty"
                self._simulation_state_start = time.time()
                logger.info("🛏️  SIMULATION: Bed is empty")

        else:
            # Fallback
            voltage = 0.5

        return max(0.0, min(3.3, voltage))  # Clamp to valid range

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
            self.baseline_voltage = cal["baseline_voltage"]
            self.occupied_threshold = cal["occupied_threshold"]
            self.movement_threshold = cal["movement_threshold"]
            self.calibrated_at = cal["calibrated_at"]
            logger.info(f"Calibration loaded from {self.calibrated_at}")
            return True

        logger.info("No calibration found, calibration required")
        return False

    def calibrate(self, interactive: bool = True) -> Dict:
        """
        Run calibration routine to determine sensor thresholds.

        If in simulation mode, uses preset calibration values.

        Args:
            interactive: If True, prompts user via console. If False, uses timing.

        Returns:
            Dictionary with calibration values
        """
        if self.simulation_mode:
            logger.info("=" * 50)
            logger.info("FSR408 Calibration (SIMULATION MODE)")
            logger.info("=" * 50)
            logger.info("Using preset calibration values for simulation")

            self.baseline_voltage = 0.5
            self.occupied_threshold = 2.0
            self.movement_threshold = 0.1
            self.calibrated_at = time.strftime("%Y-%m-%d %H:%M:%S")

            calibration_data = {
                "baseline_voltage": self.baseline_voltage,
                "occupied_threshold": self.occupied_threshold,
                "movement_threshold": self.movement_threshold,
            }

            if self.data_manager:
                self.data_manager.save_calibration(**calibration_data)

            logger.info("=" * 50)
            logger.info("Simulation Calibration Complete!")
            logger.info("=" * 50)

            return calibration_data

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
        baseline_std = (
            statistics.stdev(baseline_samples) if len(baseline_samples) > 1 else 0
        )

        logger.info(
            f"Baseline measured: {self.baseline_voltage:.3f}V (±{baseline_std:.3f}V)"
        )

        if interactive:
            input(
                "\nStep 2: Lie on bed in normal sleeping position. Press ENTER when ready..."
            )
        else:
            logger.info("Auto-calibration: measuring occupied state...")
            time.sleep(2)

        # Measure occupied state
        occupied_samples = self._collect_samples(50, 5.0)
        self.occupied_threshold = statistics.mean(occupied_samples)
        occupied_std = (
            statistics.stdev(occupied_samples) if len(occupied_samples) > 1 else 0
        )

        logger.info(
            f"Occupied measured: {self.occupied_threshold:.3f}V (±{occupied_std:.3f}V)"
        )

        # Calculate movement threshold (10% of voltage range, minimum 0.05V)
        voltage_range = abs(self.occupied_threshold - self.baseline_voltage)
        self.movement_threshold = max(voltage_range * 0.10, 0.05)

        logger.info(f"Movement threshold: {self.movement_threshold:.3f}V")

        # Validation
        if voltage_range < 0.5:
            logger.warning(
                "WARNING: Small voltage range detected. Check sensor placement."
            )

        # Save calibration
        self.calibrated_at = time.strftime("%Y-%m-%d %H:%M:%S")

        calibration_data = {
            "baseline_voltage": self.baseline_voltage,
            "occupied_threshold": self.occupied_threshold,
            "movement_threshold": self.movement_threshold,
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
        Automatically enables simulation mode if sensor is broken.

        Returns:
            Voltage in volts (real or simulated)

        Raises:
            FSR408Error: If ADC read fails
        """
        # If in simulation mode, return simulated data
        if self.simulation_mode:
            voltage = self._get_simulated_voltage()
            self._last_reading = voltage
            return voltage

        # Try to read from real sensor
        try:
            voltage = self.adc.read_voltage(self.channel)
            self._last_reading = voltage

            # Check if sensor might be broken
            self._check_for_broken_sensor(voltage)

            # Warn if voltage is suspiciously low (likely hardware issue)
            if voltage < 0.01 and self._zero_reading_count == 1:
                logger.warning(
                    f"FSR voltage reading is {voltage:.4f}V on channel {self.channel}. "
                    "This may indicate:\n"
                    "  - FSR not connected or broken (open circuit)\n"
                    "  - Voltage divider not powered (VCC disconnected)\n"
                    "  - Wrong channel selected\n"
                    "  - Ground not connected properly\n"
                    "Will enable SIMULATION MODE if this continues..."
                )

            return voltage
        except ADS1115Error as e:
            logger.error(f"Failed to read FSR voltage on channel {self.channel}: {e}")
            logger.error(f"Returning last known value: {self._last_reading:.4f}V")
            # Return last known good value
            return self._last_reading
        except Exception as e:
            logger.error(f"Unexpected error reading FSR on channel {self.channel}: {e}")
            logger.error(f"Returning last known value: {self._last_reading:.4f}V")
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
            "baseline_voltage": self.baseline_voltage,
            "occupied_threshold": self.occupied_threshold,
            "movement_threshold": self.movement_threshold,
            "calibrated_at": self.calibrated_at,
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
            "voltage": voltage,
            "force_percent": force_pct,
            "variance": variance,
            "is_occupied": self.is_occupied(),
            "channel": self.channel,
            "calibrated": self.calibrated_at is not None,
            "simulation_mode": self.simulation_mode,  # Add flag to indicate simulated data
        }


# Convenience function for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test with mock ADC in simulation mode
    adc = ADS1115(mock=True)
    fsr = FSR408(adc, simulation_mode=True)

    print(f"\nFSR408 Test (Simulation Mode)")
    print(f"Calibrated: {fsr.is_calibrated()}")

    # Run calibration
    fsr.calibrate(interactive=False)

    # Simulate readings
    print("\nGenerating simulated sleep data...")
    for i in range(50):
        data = fsr.get_sensor_data()
        sim_flag = " [SIMULATED]" if data["simulation_mode"] else ""
        print(
            f"Sample {i + 1}: {data['voltage']:.3f}V, "
            f"{data['force_percent']:.1f}%, "
            f"Variance: {data['variance']:.4f}, "
            f"Occupied: {data['is_occupied']}{sim_flag}"
        )
        time.sleep(0.5)
