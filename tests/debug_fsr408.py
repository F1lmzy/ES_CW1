"""
FSR408 Diagnostic Script
Debugs voltage reading issues by checking hardware connections,
I2C communication, and ADC configuration step-by-step.

Run this on the Raspberry Pi to identify hardware vs software issues.
"""

import logging
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from firmware.sensors.ads1115 import ADS1115, ADS1115Error
from firmware.sensors.fsr408 import FSR408

# Setup logging with detailed output
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def print_header(text):
    """Print formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def test_i2c_bus():
    """Test if I2C bus is accessible"""
    print_header("TEST 1: I2C Bus Accessibility")

    try:
        import smbus2

        bus = smbus2.SMBus(1)
        print("✓ I2C bus 1 is accessible")
        bus.close()
        return True
    except ImportError:
        print("✗ smbus2 library not installed")
        print("  Install with: pip install smbus2")
        return False
    except Exception as e:
        print(f"✗ Cannot access I2C bus 1: {e}")
        print("  Check if I2C is enabled: sudo raspi-config")
        return False


def scan_i2c_devices():
    """Scan for I2C devices on the bus"""
    print_header("TEST 2: I2C Device Scan")

    try:
        import smbus2

        bus = smbus2.SMBus(1)

        print("Scanning I2C bus for devices...")
        devices = []

        for addr in range(0x03, 0x78):
            try:
                bus.read_byte(addr)
                devices.append(addr)
                print(f"  Found device at 0x{addr:02X}")
            except:
                pass

        bus.close()

        if not devices:
            print("✗ No I2C devices found!")
            print("  Check wiring and power connections")
            return False

        if 0x48 in devices:
            print(f"\n✓ ADS1115 found at default address 0x48")
            return True
        else:
            print(f"\n✗ ADS1115 not found at 0x48")
            print(f"  Devices found: {[hex(d) for d in devices]}")
            return False

    except Exception as e:
        print(f"✗ Error scanning I2C bus: {e}")
        return False


def test_ads1115_connection():
    """Test ADS1115 initialization and connection"""
    print_header("TEST 3: ADS1115 Connection")

    try:
        adc = ADS1115(bus=1, address=0x48, mock=False)

        if adc.is_connected():
            print("✓ ADS1115 is responding to I2C commands")
            return adc
        else:
            print("✗ ADS1115 not responding")
            print("  Device may be in wrong mode or not powered")
            return None

    except ADS1115Error as e:
        print(f"✗ ADS1115 initialization failed: {e}")
        return None
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return None


def test_raw_adc_readings(adc):
    """Test raw ADC readings on all channels"""
    print_header("TEST 4: Raw ADC Readings")

    if not adc:
        print("Skipping - ADC not available")
        return False

    print("Reading raw values from all channels...")
    print(f"{'Channel':<10} {'Raw Value':<15} {'Voltage':<15} {'Status'}")
    print("-" * 70)

    all_zero = True

    for channel in range(4):
        try:
            raw = adc.read_raw(channel)
            voltage = adc.read_voltage(channel)

            status = "✓" if abs(raw) > 100 else "⚠"
            if abs(raw) > 100:
                all_zero = False

            print(f"AIN{channel:<9} {raw:<15} {voltage:<15.4f}V {status}")

        except Exception as e:
            print(f"AIN{channel:<9} ERROR: {e}")

    print()

    if all_zero:
        print("✗ All channels reading ~0V")
        print("  Possible causes:")
        print("    - Voltage divider not powered (no VCC)")
        print("    - FSR not connected")
        print("    - Ground not connected")
        return False
    else:
        print("✓ At least one channel has non-zero reading")
        return True


def test_fsr_channel_sweep(adc):
    """Test FSR on all channels to find correct connection"""
    print_header("TEST 5: FSR Channel Detection")

    if not adc:
        print("Skipping - ADC not available")
        return None

    print("Testing FSR on all channels...")
    print("Apply pressure to the FSR sensor now!\n")

    print(
        f"{'Channel':<10} {'Initial':<12} {'After 3s':<12} {'Change':<12} {'Detected?'}"
    )
    print("-" * 70)

    detected_channel = None
    max_change = 0

    for channel in range(4):
        try:
            # Read initial voltage
            initial_v = adc.read_voltage(channel)
            time.sleep(0.1)

            # Wait and read again
            time.sleep(3)

            # Take average of 5 readings
            voltages = []
            for _ in range(5):
                voltages.append(adc.read_voltage(channel))
                time.sleep(0.1)
            final_v = sum(voltages) / len(voltages)

            change = abs(final_v - initial_v)

            detected = "YES ✓" if change > 0.1 else "no"

            print(
                f"AIN{channel:<9} {initial_v:<12.4f} {final_v:<12.4f} {change:<12.4f} {detected}"
            )

            if change > max_change:
                max_change = change
                detected_channel = channel

        except Exception as e:
            print(f"AIN{channel:<9} ERROR: {e}")

    print()

    if detected_channel is not None and max_change > 0.1:
        print(
            f"✓ FSR likely connected to AIN{detected_channel} (change: {max_change:.4f}V)"
        )
        return detected_channel
    else:
        print("✗ No channel showed significant voltage change")
        print("  Possible causes:")
        print("    - FSR not connected to any channel")
        print("    - FSR broken (always high resistance)")
        print("    - Not enough pressure applied")
        return None


def test_continuous_monitoring(adc, channel):
    """Monitor FSR voltage continuously"""
    print_header("TEST 6: Continuous Monitoring")

    if not adc or channel is None:
        print("Skipping - ADC or channel not available")
        return

    print(f"Monitoring AIN{channel} for 10 seconds...")
    print("Apply varying pressure to see voltage changes\n")
    print(f"{'Time':<8} {'Raw':<10} {'Voltage':<12} {'Bar Graph'}")
    print("-" * 70)

    try:
        for i in range(100):  # 10 seconds at 10Hz
            raw = adc.read_raw(channel)
            voltage = adc.read_voltage(channel)

            # Create simple bar graph (0-3.3V range)
            bar_length = int((voltage / 3.3) * 40)
            bar = "█" * bar_length

            print(f"{i * 0.1:<8.1f} {raw:<10} {voltage:<12.4f} {bar}")

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")


def test_fsr408_class(adc, channel):
    """Test FSR408 class functionality"""
    print_header("TEST 7: FSR408 Class Test")

    if not adc or channel is None:
        print("Skipping - ADC or channel not available")
        return

    try:
        fsr = FSR408(adc=adc, channel=channel)

        print(f"Testing FSR408 on channel {channel}...\n")

        for i in range(10):
            voltage = fsr.get_voltage()
            force_pct = fsr.get_force_percentage()
            variance = fsr.get_variance()
            occupied = fsr.is_occupied()

            print(
                f"Sample {i + 1}: {voltage:.4f}V, {force_pct:.1f}%, "
                f"Variance: {variance:.6f}, Occupied: {occupied}"
            )

            time.sleep(0.5)

        print("\n✓ FSR408 class working correctly")

    except Exception as e:
        print(f"✗ FSR408 class error: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Run all diagnostic tests"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║         FSR408 Diagnostic Tool                                    ║
║         Identifies hardware and software issues                   ║
╚══════════════════════════════════════════════════════════════════╝
    """)

    # Test 1: I2C bus
    if not test_i2c_bus():
        print("\n✗ FATAL: Cannot access I2C bus. Stopping diagnostics.")
        return

    # Test 2: Scan for devices
    if not scan_i2c_devices():
        print("\n⚠ WARNING: ADS1115 not detected. Continuing anyway...")

    # Test 3: Connect to ADS1115
    adc = test_ads1115_connection()
    if not adc:
        print("\n✗ FATAL: Cannot connect to ADS1115. Stopping diagnostics.")
        return

    # Test 4: Raw ADC readings
    test_raw_adc_readings(adc)

    # Test 5: Find FSR channel
    detected_channel = test_fsr_channel_sweep(adc)

    if detected_channel is None:
        print("\n⚠ WARNING: Could not detect FSR channel")
        print("Using default channel 0 for remaining tests...\n")
        detected_channel = 0

    # Test 6: Continuous monitoring
    test_continuous_monitoring(adc, detected_channel)

    # Test 7: FSR408 class
    test_fsr408_class(adc, detected_channel)

    # Final summary
    print_header("DIAGNOSTIC SUMMARY")
    print(
        """
If voltage is still 0:

HARDWARE CHECKS:
1. Verify VCC (3.3V or 5V) is connected to voltage divider
2. Verify GND is connected to both ADS1115 and voltage divider
3. Check FSR resistance with multimeter:
   - No pressure: Should be >1MΩ (very high)
   - With pressure: Should drop to 1kΩ-100kΩ
4. Verify 10kΩ pull-down resistor is connected
5. Check voltage divider output with multimeter before connecting to ADC

WIRING DIAGRAM:
    VCC (3.3V)
       |
    [FSR408]
       |
       +------ To ADS1115 AIN0
       |
    [10kΩ]
       |
     GND

SOFTWARE CHECKS:
1. Ensure correct channel number (found: {})
2. Check logs for I2C errors
3. Verify ADS1115 address (default 0x48)

For more help, provide the output of this script to your team.
    """.format(detected_channel)
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDiagnostic interrupted by user")
    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback

        traceback.print_exc()
