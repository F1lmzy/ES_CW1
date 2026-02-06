# FSR408 Troubleshooting Guide: Zero Voltage Issue

## Problem Description
The FSR408 force sensor is logging voltage as 0V or very close to 0V, indicating either a hardware connection issue or a software configuration problem.

## Quick Diagnostic Steps

### 1. Run the Diagnostic Script
```bash
cd /Users/kavin/Documents/ES_CW1
python3 tests/debug_fsr408.py
```

This script will:
- Check I2C bus accessibility
- Scan for ADS1115 device
- Test all ADC channels
- Detect which channel has the FSR connected
- Monitor voltage in real-time

### 2. Check Logs
Look for these warnings in the logs:
- `"FSR voltage reading is 0.0000V"` - Hardware issue likely
- `"Failed to read FSR voltage"` - I2C communication error
- `"ADS1115 running in MOCK mode"` - I2C bus not accessible

## Common Causes & Solutions

### Hardware Issues (Most Likely)

#### Cause 1: Voltage Divider Not Powered
**Symptom:** All channels read 0V
**Solution:**
- Check that VCC (3.3V or 5V) is connected to the top of the voltage divider
- Verify power supply is on
- Measure VCC with multimeter (should be 3.3V or 5V)

#### Cause 2: FSR Not Connected or Broken
**Symptom:** Single channel reads 0V, others may vary
**Solution:**
- Check FSR connections - should be firmly seated
- Test FSR resistance with multimeter:
  - No pressure: >1MΩ (very high resistance)
  - Light pressure: 10kΩ - 100kΩ
  - Heavy pressure: 1kΩ - 10kΩ
- If resistance doesn't change, FSR is broken

#### Cause 3: Ground Not Connected
**Symptom:** Erratic readings or 0V
**Solution:**
- Verify GND is connected to both ADS1115 and voltage divider
- Check continuity between all ground points

#### Cause 4: Wrong Channel Selected
**Symptom:** One specific channel reads 0V
**Solution:**
- Check which ADS1115 channel the FSR is connected to (AIN0-AIN3)
- Update channel in code: `FSR408(adc, channel=X)`
- Run diagnostic script to auto-detect channel

#### Cause 5: Pull-Down Resistor Missing
**Symptom:** Floating voltage or no reading
**Solution:**
- Verify 10kΩ resistor is connected between ADC input and GND
- Measure resistance with multimeter (should be ~10kΩ)

### Software Issues

#### Cause 6: I2C Bus Not Enabled
**Symptom:** `"I2C bus not accessible"` error
**Solution:**
```bash
sudo raspi-config
# Select: Interface Options -> I2C -> Enable
sudo reboot
```

#### Cause 7: ADS1115 Not Detected
**Symptom:** `"ADS1115 not responding"` warning
**Solution:**
- Check I2C address (default 0x48)
- Scan for devices: `sudo i2cdetect -y 1`
- Verify ADS1115 power (VDD should be 3.3V or 5V)

#### Cause 8: Silent Error Handling
**Symptom:** No error messages but reads 0V
**Solution:**
- Check `_last_reading` initialization (defaults to 0.0)
- If first read fails, will return 0.0 silently
- Enable DEBUG logging to see all errors:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Correct Wiring Diagram

```
Raspberry Pi                    ADS1115
                                 ┌─────┐
VCC (3.3V/5V) ────────────┬──────┤ VDD │
                          │      │     │
                       [FSR408]  │     │
                          │      │     │
                          ├──────┤ AIN0├── FSR Signal
                          │      │     │
                       [10kΩ]    │     │
                          │      │     │
GND ──────────────────────┴──────┤ GND │
                                 └─────┘
                                    │
                       I2C ─────────┤
                       SDA/SCL      │
```

### Pin Connections:
- **VCC:** 3.3V or 5V from Pi
- **GND:** Ground (common between Pi and ADS1115)
- **SDA:** GPIO 2 (Pin 3)
- **SCL:** GPIO 3 (Pin 5)
- **FSR Top:** To VCC
- **FSR Bottom:** To AIN0 and 10kΩ resistor
- **10kΩ Resistor:** Between AIN0 and GND

## Testing Procedure

### Step 1: Verify Hardware Without Pi
1. Disconnect from Raspberry Pi
2. Connect voltage divider to power supply (3.3V)
3. Measure voltage at ADC input with multimeter:
   - No pressure: ~0V (FSR has high resistance)
   - With pressure: Should increase (0.5V - 3.0V typical)
4. If voltage doesn't change, check FSR and resistor

### Step 2: Verify I2C Communication
```bash
# Check if I2C devices are detected
sudo i2cdetect -y 1

# Expected output should show 48 (ADS1115 address):
#      0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
# 00:          -- -- -- -- -- -- -- -- -- -- -- -- -- 
# 10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
# 20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
# 30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
# 40: -- -- -- -- -- -- -- -- 48 -- -- -- -- -- -- -- 
# 50: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
# 60: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
# 70: -- -- -- -- -- -- -- --
```

### Step 3: Test with Python
```python
import sys
sys.path.insert(0, '/Users/kavin/Documents/ES_CW1')

from firmware.sensors.ads1115 import ADS1115

# Test ADC
adc = ADS1115(bus=1, address=0x48)
print(f"Connected: {adc.is_connected()}")

# Test all channels
for ch in range(4):
    v = adc.read_voltage(ch)
    print(f"Channel {ch}: {v:.4f}V")
```

### Step 4: Test FSR Response
1. Run diagnostic script: `python3 tests/debug_fsr408.py`
2. Watch for voltage changes when pressure is applied
3. Identify which channel responds to pressure

## Expected Voltage Ranges

| Condition | Voltage | FSR Resistance |
|-----------|---------|----------------|
| No Force | ~0V - 0.5V | >1MΩ |
| Light Touch | 0.5V - 1.5V | 50kΩ - 200kΩ |
| Medium Pressure | 1.5V - 2.5V | 10kΩ - 50kΩ |
| Heavy Pressure | 2.5V - 3.3V | 1kΩ - 10kΩ |

If sensor reads 0V with heavy pressure, check:
- FSR might be installed backwards (shouldn't matter but try flipping)
- 10kΩ resistor value is correct
- Voltage divider is configured correctly

## Code Configuration

### Verify Channel Number
In `firmware/main.py`:
```python
FSR_CHANNEL = 0  # Change to 0, 1, 2, or 3 based on wiring
```

### Verify I2C Address
In `firmware/sensors/ads1115.py`:
```python
ADS1115_ADDRESS = 0x48  # Default address
```

If you changed the ADDR pin on ADS1115:
- ADDR to GND: 0x48 (default)
- ADDR to VDD: 0x49
- ADDR to SDA: 0x4A
- ADDR to SCL: 0x4B

## Still Not Working?

### Enable Verbose Logging
Edit `firmware/main.py`:
```python
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
```

### Check for Python Errors
```bash
cd /Users/kavin/Documents/ES_CW1
python3 -c "
import sys
sys.path.insert(0, '.')
from firmware.sensors.ads1115 import ADS1115
from firmware.sensors.fsr408 import FSR408
print('Imports successful')
"
```

### Test with Mock Mode
```python
from firmware.sensors.ads1115 import ADS1115
from firmware.sensors.fsr408 import FSR408

# Use mock mode to test software logic
adc = ADS1115(mock=True)
fsr = FSR408(adc)

# Should show random mock values
print(fsr.get_voltage())  # Should NOT be 0.0
```

## Hardware vs Software Decision Tree

```
Voltage = 0V?
│
├─ YES → Run debug_fsr408.py
│   │
│   ├─ I2C bus not accessible?
│   │   └─ Enable I2C in raspi-config (SOFTWARE)
│   │
│   ├─ ADS1115 not found at 0x48?
│   │   ├─ Check power to ADS1115 (HARDWARE)
│   │   └─ Verify I2C wiring (HARDWARE)
│   │
│   ├─ All channels read 0V?
│   │   ├─ VCC not connected (HARDWARE)
│   │   └─ GND not connected (HARDWARE)
│   │
│   └─ One channel reads 0V?
│       ├─ FSR not connected (HARDWARE)
│       ├─ Wrong channel in code (SOFTWARE)
│       └─ FSR broken (HARDWARE)
│
└─ NO → Check if voltage changes with pressure
    │
    ├─ Changes → WORKING! Proceed with calibration
    │
    └─ Doesn't change → FSR broken or not responsive (HARDWARE)
```

## Contact & Support

If none of these steps resolve the issue:
1. Save the output of `debug_fsr408.py`
2. Take photos of your wiring
3. Note the exact voltage readings from multimeter
4. Share with your team or instructor

## References

- FSR408 Datasheet: Force varies resistance (high when empty, low when pressed)
- ADS1115 Datasheet: 16-bit ADC, I2C address 0x48
- Raspberry Pi I2C: GPIO 2 (SDA), GPIO 3 (SCL)