"""
ADS1115 16-bit ADC Driver
Custom I2C implementation using smbus2 (byte-level communication)
Meets specification #10: No existing sensor libraries used

ADS1115 Register Map:
- Pointer Register (8-bit): Selects which register to access
  - 0x00: Conversion register (16-bit result)
  - 0x01: Config register (16-bit configuration)
  - 0x02: Lo_thresh register
  - 0x03: Hi_thresh register

I2C Address: 0x48 (default, can be 0x48-0x4B based on ADDR pin)
"""

import logging
import time
from typing import Optional

try:
    from smbus2 import SMBus
except ImportError:
    SMBus = None
    logging.warning("smbus2 not available. Using mock mode for testing.")

# ADS1115 Constants
ADS1115_ADDRESS = 0x48

# Pointer Register values
POINTER_CONVERSION = 0x00
POINTER_CONFIG = 0x01
POINTER_LO_THRESH = 0x02
POINTER_HI_THRESH = 0x03

# Config Register bit positions
CONFIG_OS = 15  # Operational status/single-shot conversion start
CONFIG_MUX = 12  # Input multiplexer configuration (3 bits)
CONFIG_PGA = 9  # Programmable gain amplifier (3 bits)
CONFIG_MODE = 8  # Device operating mode
CONFIG_DR = 5  # Data rate (3 bits)
CONFIG_COMP_MODE = 4  # Comparator mode
CONFIG_COMP_POL = 3  # Comparator polarity
CONFIG_COMP_LAT = 2  # Latching comparator
CONFIG_COMP_QUE = 0  # Comparator queue (2 bits)

# Configuration values for FSR408
MUX_AIN0_GND = 0x04  # Single-ended AIN0
PGA_4_096V = 0x01  # ±4.096V full scale
MODE_SINGLE = 0x01  # Single-shot mode
DR_128SPS = 0x04  # 128 samples per second

logger = logging.getLogger(__name__)


class ADS1115Error(Exception):
    """Custom exception for ADS1115 errors"""

    pass


class ADS1115:
    """
    ADS1115 16-bit ADC driver with byte-level I2C communication.

    Implements specification #10: Byte-level I2C without existing libraries.
    Uses smbus2 for I2C bus access but implements all register logic manually.
    """

    def __init__(
        self, bus: int = 1, address: int = ADS1115_ADDRESS, mock: bool = False
    ):
        """
        Initialize ADS1115 ADC.

        Args:
            bus: I2C bus number (usually 1 on Raspberry Pi)
            address: I2C address (default 0x48)
            mock: If True, use mock mode for testing without hardware
        """
        self.bus_num = bus
        self.address = address
        self.mock = mock or SMBus is None
        self.bus = None
        self._last_value = 0

        if not self.mock:
            try:
                self.bus = SMBus(self.bus_num)
                logger.info(
                    f"ADS1115 initialized on I2C bus {bus}, address 0x{address:02X}"
                )
            except Exception as e:
                logger.error(f"Failed to open I2C bus: {e}")
                raise ADS1115Error(f"I2C bus {bus} not accessible: {e}")
        else:
            logger.info("ADS1115 running in MOCK mode")

    def _write_register(self, pointer: int, value: int, retries: int = 3) -> None:
        """
        Write 16-bit value to ADS1115 register using byte-level I2C.

        Spec #10: Demonstrates byte-level I2C communication.
        Writes 3 bytes: pointer register + 2 data bytes (MSB first).

        Args:
            pointer: Register address (0x00-0x03)
            value: 16-bit value to write
            retries: Number of retry attempts on failure
        """
        if self.mock:
            return

        # Convert 16-bit value to two bytes (MSB first, as per ADS1115 spec)
        msb = (value >> 8) & 0xFF
        lsb = value & 0xFF

        for attempt in range(retries):
            try:
                # Spec #10: Byte-level write - pointer + 2 data bytes
                self.bus.write_i2c_block_data(self.address, pointer, [msb, lsb])
                return
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning(
                        f"I2C write failed (attempt {attempt + 1}), retrying: {e}"
                    )
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(f"I2C write failed after {retries} attempts: {e}")
                    raise ADS1115Error(f"Failed to write register 0x{pointer:02X}: {e}")

    def _read_register(self, pointer: int, retries: int = 3) -> int:
        """
        Read 16-bit value from ADS1115 register using byte-level I2C.

        Spec #10: Demonstrates byte-level I2C communication.
        Writes pointer, then reads 2 bytes (MSB first) and combines.

        Args:
            pointer: Register address (0x00-0x03)
            retries: Number of retry attempts on failure

        Returns:
            16-bit signed integer value
        """
        if self.mock:
            # Return mock value for testing
            import random

            return random.randint(0, 65535)

        for attempt in range(retries):
            try:
                # Spec #10: Byte-level communication
                # First write pointer register
                self.bus.write_byte(self.address, pointer)

                # Then read 2 bytes (MSB, LSB)
                data = self.bus.read_i2c_block_data(self.address, pointer, 2)

                # Combine bytes: MSB << 8 | LSB
                value = (data[0] << 8) | data[1]

                # Convert to signed 16-bit if necessary (two's complement)
                if value & 0x8000:
                    value -= 65536

                return value

            except Exception as e:
                if attempt < retries - 1:
                    logger.warning(
                        f"I2C read failed (attempt {attempt + 1}), retrying: {e}"
                    )
                    time.sleep(0.1 * (attempt + 1))
                else:
                    logger.error(f"I2C read failed after {retries} attempts: {e}")
                    raise ADS1115Error(f"Failed to read register 0x{pointer:02X}: {e}")

    def _build_config(self, channel: int = 0, continuous: bool = False) -> int:
        """
        Build configuration value for ADS1115.

        Args:
            channel: ADC channel (0-3)
            continuous: True for continuous conversion, False for single-shot

        Returns:
            16-bit configuration value
        """
        # Start with OS bit set (begin conversion)
        config = 1 << CONFIG_OS

        # Set multiplexer for single-ended input
        # MUX: 100 (AIN0), 101 (AIN1), 110 (AIN2), 111 (AIN3)
        mux = 0x04 | (channel & 0x03)
        config |= mux << CONFIG_MUX

        # Set PGA to ±4.096V (suitable for 5V FSR with voltage divider)
        config |= PGA_4_096V << CONFIG_PGA

        # Set mode (single-shot or continuous)
        if continuous:
            config |= 0 << CONFIG_MODE
        else:
            config |= MODE_SINGLE << CONFIG_MODE

        # Set data rate to 128 SPS
        config |= DR_128SPS << CONFIG_DR

        # Disable comparator
        config |= 0x03 << CONFIG_COMP_QUE

        return config

    def read_raw(self, channel: int = 0, timeout: float = 1.0) -> int:
        """
        Read raw 16-bit ADC value from specified channel.

        Spec #10: Byte-level I2C read sequence:
        1. Write config to start conversion
        2. Poll/wait for conversion complete
        3. Read 2 bytes from conversion register

        Args:
            channel: ADC channel (0-3)
            timeout: Maximum time to wait for conversion

        Returns:
            16-bit signed integer (-32768 to 32767)
        """
        if self.mock:
            import random

            # Return realistic mock values for FSR (1.0V to 3.3V range)
            return random.randint(8000, 26000)

        try:
            # Build configuration to start single-shot conversion
            config = self._build_config(channel, continuous=False)

            # Write config register (starts conversion)
            self._write_register(POINTER_CONFIG, config)

            # Wait for conversion to complete (at 128 SPS, takes ~8ms)
            time.sleep(0.01)

            # Poll until conversion complete (OS bit goes to 0)
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = self._read_register(POINTER_CONFIG)
                # OS bit (bit 15) = 0 means conversion in progress
                # OS bit = 1 means conversion complete
                if status & (1 << CONFIG_OS):
                    break
                time.sleep(0.001)  # 1ms polling interval

            # Read conversion result
            raw_value = self._read_register(POINTER_CONVERSION)
            self._last_value = raw_value

            return raw_value

        except ADS1115Error:
            raise
        except Exception as e:
            logger.error(f"Unexpected error reading ADC: {e}")
            # Return last known good value
            return self._last_value

    def read_voltage(self, channel: int = 0, pga: float = 4.096) -> float:
        """
        Read ADC value and convert to voltage.

        Args:
            channel: ADC channel (0-3)
            pga: Programmable gain amplifier voltage (default ±4.096V)

        Returns:
            Voltage in volts
        """
        raw = self.read_raw(channel)

        # Convert to voltage: V = (raw / 32767) * pga
        # ADS1115 is 16-bit signed: -32768 to 32767
        voltage = (raw / 32767.0) * pga

        return voltage

    def is_connected(self) -> bool:
        """Check if ADS1115 is accessible on I2C bus"""
        if self.mock:
            return True

        try:
            # Try to read config register
            self._read_register(POINTER_CONFIG)
            return True
        except:
            return False

    def close(self):
        """Close I2C bus connection"""
        if self.bus and not self.mock:
            try:
                self.bus.close()
                logger.info("ADS1115 I2C bus closed")
            except Exception as e:
                logger.warning(f"Error closing I2C bus: {e}")


# Convenience function for testing
if __name__ == "__main__":
    # Test with mock mode
    logging.basicConfig(level=logging.INFO)

    adc = ADS1115(mock=True)
    print(f"Mock ADS1115 initialized: {adc.is_connected()}")

    # Read a few samples
    for i in range(5):
        raw = adc.read_raw(0)
        voltage = adc.read_voltage(0)
        print(f"Sample {i + 1}: Raw={raw}, Voltage={voltage:.3f}V")
        time.sleep(0.5)
