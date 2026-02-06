#!/usr/bin/env python3
"""
Quick FSR408 Hardware vs Software Test
Run this 30-second test to identify if the issue is hardware or software.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_result(test_name, passed, message=""):
    """Print test result with emoji"""
    status = "✓" if passed else "✗"
    color = "\033[92m" if passed else "\033[91m"
    reset = "\033[0m"
    print(f"{color}{status}{reset} {test_name}")
    if message:
        print(f"  → {message}")


def main():
    print("\n" + "=" * 60)
    print("  FSR408 Quick Test (30 seconds)")
    print("=" * 60 + "\n")

    # Test 1: Python imports
    print("[1/5] Testing Python imports...")
    try:
        from firmware.sensors.ads1115 import ADS1115
        from firmware.sensors.fsr408 import FSR408

        print_result("Python imports", True)
    except Exception as e:
        print_result("Python imports", False, str(e))
        print("\n✗ SOFTWARE ISSUE: Cannot import modules")
        return

    # Test 2: I2C availability
    print("\n[2/5] Testing I2C bus...")
    try:
        import smbus2

        bus = smbus2.SMBus(1)
        bus.close()
        print_result("I2C bus accessible", True)
    except ImportError:
        print_result("I2C bus accessible", False, "smbus2 not installed")
        print("\n✗ SOFTWARE ISSUE: Install smbus2")
        print("  Run: pip3 install smbus2")
        return
    except Exception as e:
        print_result("I2C bus accessible", False, str(e))
        print("\n✗ SOFTWARE ISSUE: I2C not enabled")
        print("  Run: sudo raspi-config → Interface Options → I2C → Enable")
        return

    # Test 3: ADS1115 detection
    print("\n[3/5] Testing ADS1115 connection...")
    try:
        adc = ADS1115(bus=1, address=0x48, mock=False)
        if adc.is_connected():
            print_result("ADS1115 detected", True, "Found at address 0x48")
        else:
            print_result("ADS1115 detected", False, "Not responding")
            print("\n✗ HARDWARE ISSUE: ADS1115 not detected")
            print("  Check:")
            print("    - Power to ADS1115 (VDD = 3.3V or 5V)")
            print("    - I2C wiring (SDA/SCL)")
            print("  Run: sudo i2cdetect -y 1")
            return
    except Exception as e:
        print_result("ADS1115 detected", False, str(e))
        print("\n✗ HARDWARE ISSUE: Cannot communicate with ADS1115")
        return

    # Test 4: Voltage readings
    print("\n[4/5] Testing voltage readings on all channels...")
    print("  Press FSR now if you want to test it!\n")

    import time

    channels_with_signal = []

    for channel in range(4):
        try:
            # Take average of 3 readings
            voltages = []
            for _ in range(3):
                v = adc.read_voltage(channel)
                voltages.append(v)
                time.sleep(0.1)

            avg_voltage = sum(voltages) / len(voltages)

            # Check if there's a signal (>0.1V)
            has_signal = avg_voltage > 0.1

            print(f"  AIN{channel}: {avg_voltage:.4f}V", end="")
            if has_signal:
                print(" ← Signal detected!")
                channels_with_signal.append(channel)
            else:
                print()

        except Exception as e:
            print(f"  AIN{channel}: ERROR - {e}")

    print()

    if not channels_with_signal:
        print_result("Voltage readings", False, "All channels read ~0V")
        print("\n✗ HARDWARE ISSUE: No voltage on any channel")
        print("  Check:")
        print("    - VCC connected to voltage divider (3.3V or 5V)")
        print("    - FSR connected properly")
        print("    - 10kΩ pull-down resistor in place")
        print("    - Ground connected")
        print("\n  Test with multimeter:")
        print("    1. Measure VCC (should be 3.3V or 5V)")
        print("    2. Measure voltage at ADC input while pressing FSR")
        print("    3. Should see 0.5V - 3.0V with pressure")
        return
    else:
        print_result(
            "Voltage readings",
            True,
            f"Signal on channel(s): {', '.join(map(str, channels_with_signal))}",
        )

    # Test 5: FSR class functionality
    print("\n[5/5] Testing FSR408 class...")
    test_channel = channels_with_signal[0]

    try:
        fsr = FSR408(adc=adc, channel=test_channel)

        # Take 5 readings
        voltages = []
        for i in range(5):
            v = fsr.get_voltage()
            voltages.append(v)
            time.sleep(0.2)

        avg = sum(voltages) / len(voltages)
        variance = sum((v - avg) ** 2 for v in voltages) / len(voltages)

        print(f"  Channel: {test_channel}")
        print(f"  Average voltage: {avg:.4f}V")
        print(f"  Variance: {variance:.6f}")

        if avg < 0.01:
            print_result("FSR408 class", False, "Still reading ~0V")
            print("\n⚠ POSSIBLE ISSUE: Wrong channel or timing issue")
        else:
            print_result("FSR408 class", True, "Working correctly!")

            # Show interpretation
            print("\n" + "=" * 60)
            print("  ✓ SUCCESS - System is working!")
            print("=" * 60)
            print(f"\nFSR is connected to channel AIN{test_channel}")
            print(f"Current reading: {avg:.4f}V")

            if avg < 0.5:
                print("Status: Empty (no pressure)")
            elif avg < 1.5:
                print("Status: Light pressure")
            elif avg < 2.5:
                print("Status: Medium pressure (occupied)")
            else:
                print("Status: Heavy pressure")

            print("\nNext steps:")
            print("  1. Update firmware/main.py if needed:")
            print(f"     FSR_CHANNEL = {test_channel}")
            print("  2. Run calibration: python3 firmware/main.py")
            print("  3. Follow prompts to calibrate sensor")
            return

    except Exception as e:
        print_result("FSR408 class", False, str(e))
        print("\n✗ SOFTWARE ISSUE: FSR408 class error")
        return

    print("\n" + "=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback

        traceback.print_exc()

    print("\nFor detailed diagnostics, run:")
    print("  python3 tests/debug_fsr408.py")
    print("\nFor full troubleshooting guide, see:")
    print("  docs/FSR408_TROUBLESHOOTING.md\n")
