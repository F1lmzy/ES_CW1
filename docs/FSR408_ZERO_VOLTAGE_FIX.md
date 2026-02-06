# FSR408 Zero Voltage Issue - Quick Fix Guide

## Problem
The FSR408 force sensor is reading 0V when logging data.

## TL;DR - Most Likely Causes

1. **Hardware Issue (90% probability)**
   - Voltage divider not powered (VCC disconnected)
   - FSR sensor not connected properly
   - Wrong ADC channel selected
   - Ground connection missing

2. **Software Issue (10% probability)**
   - I2C bus not enabled
   - Wrong channel number in code
   - Silent error being caught

## 🚀 Quick Start - Run This First

```bash
cd /Users/kavin/Documents/ES_CW1
python3 tests/debug_fsr408.py
```

This diagnostic script will automatically:
- ✅ Check I2C bus
- ✅ Detect ADS1115 
- ✅ Test all channels
- ✅ Find which channel has the FSR
- ✅ Monitor voltage in real-time

## 🔧 Hardware Checklist

### 1. Verify Power (MOST COMMON)
```
☐ VCC (3.3V or 5V) connected to voltage divider
☐ Measure VCC with multimeter (should read 3.3V or 5V)
☐ Power supply is turned on
```

### 2. Verify FSR Connections
```
☐ FSR top lead connected to VCC
☐ FSR bottom lead connected to ADC input AND 10kΩ resistor
☐ FSR is not damaged (test with multimeter - resistance should change with pressure)
```

### 3. Verify Ground
```
☐ GND connected from Pi to ADS1115
☐ GND connected from ADS1115 to voltage divider
☐ All grounds are common (same rail)
```

### 4. Verify I2C Connections
```
☐ SDA: Pi GPIO 2 (Pin 3) → ADS1115 SDA
☐ SCL: Pi GPIO 3 (Pin 5) → ADS1115 SCL
☐ Both need pull-up resistors (usually built into Pi)
```

## 🔌 Correct Wiring

```
    VCC (3.3V)
       │
    ┌──┴──┐
    │ FSR │  ← Force Sensitive Resistor
    └──┬──┘
       │
       ├────────→ ADS1115 AIN0 (or AIN1/2/3)
       │
    ┌──┴──┐
    │10kΩ │  ← Pull-down resistor
    └──┬──┘
       │
      GND
```

## 💻 Software Checklist

### 1. Enable I2C (if not already enabled)
```bash
sudo raspi-config
# Interface Options → I2C → Enable
sudo reboot
```

### 2. Verify ADS1115 is Detected
```bash
sudo i2cdetect -y 1
```
Should show `48` at address 0x48

### 3. Check Channel Number
In `firmware/main.py`, verify:
```python
FSR_CHANNEL = 0  # Make sure this matches your wiring!
```

## 🧪 Test FSR with Multimeter

1. **Disconnect from circuit**
2. **Measure resistance across FSR:**
   - No pressure: >1MΩ (infinite)
   - Light pressure: 10kΩ - 100kΩ
   - Heavy pressure: 1kΩ - 10kΩ

If resistance doesn't change → **FSR is broken**

3. **Test voltage divider output:**
   - Connect VCC, FSR, 10kΩ resistor, GND
   - Measure voltage at junction (where ADC connects)
   - No pressure: ~0V
   - With pressure: 0.5V - 3.0V (should increase)

## 🐛 Code Changes Made

I've improved the error handling in `fsr408.py`:

### Before:
- Errors were caught silently
- Returned 0.0 on first error with no clear warning

### After:
- **Added warning message when voltage is 0V**
- Shows possible causes in log
- Points to diagnostic script

Now when voltage is 0V, you'll see:
```
WARNING: FSR voltage reading is 0.0000V on channel 0. This may indicate:
  - FSR not connected or broken (open circuit)
  - Voltage divider not powered (VCC disconnected)
  - Wrong channel selected
  - Ground not connected properly
Run tests/debug_fsr408.py for detailed diagnostics.
```

## 📊 Expected Voltage Ranges

| Condition | Voltage | What It Means |
|-----------|---------|---------------|
| **0V - 0.1V** | Empty bed | No force applied |
| 0.5V - 1.5V | Light touch | Slight pressure |
| 1.5V - 2.5V | Person lying | Normal occupancy |
| 2.5V - 3.3V | Heavy pressure | Full force |

**If you're reading exactly 0V → Hardware problem**

## 🎯 Decision Tree

```
Reading 0V?
│
├─ Run: sudo i2cdetect -y 1
│   │
│   ├─ Shows "48"? → ADS1115 OK, check wiring
│   │
│   └─ No "48"? → Check ADS1115 power and I2C wiring
│
├─ Run: tests/debug_fsr408.py
│   │
│   ├─ All channels 0V? → VCC not connected
│   │
│   └─ One channel 0V? → Wrong channel or FSR disconnected
│
└─ Test FSR with multimeter
    │
    ├─ Resistance changes? → FSR good, check wiring
    │
    └─ No change? → FSR broken, replace sensor
```

## 🔍 Common Mistakes

1. **Forgot to power the voltage divider** ← #1 mistake!
2. **Wrong channel number in code** (FSR on AIN1, code says AIN0)
3. **No pull-down resistor** (10kΩ missing)
4. **FSR leads reversed** (shouldn't matter but try swapping)
5. **I2C not enabled** (raspi-config)
6. **No common ground** (Pi GND ≠ circuit GND)

## 📝 Next Steps

1. **Run diagnostic script**: `python3 tests/debug_fsr408.py`
2. **Check output** for which test fails
3. **Fix hardware** based on test results
4. **Verify voltage changes** when applying pressure
5. **Run calibration** once working: `python3 firmware/main.py`

## 💡 Pro Tips

- Use a multimeter to verify voltages at each step
- Test voltage divider BEFORE connecting to ADC
- Apply firm pressure when testing (light touch may not register)
- Check log files: `tail -f sleepsense.log`
- Enable DEBUG logging for more details

## 📚 Related Files

- **Diagnostic Tool**: `tests/debug_fsr408.py`
- **Full Guide**: `docs/FSR408_TROUBLESHOOTING.md`
- **FSR Code**: `firmware/sensors/fsr408.py`
- **ADC Code**: `firmware/sensors/ads1115.py`
- **Main Program**: `firmware/main.py`

## ❓ Still Not Working?

If after all these steps you still read 0V:

1. **Save diagnostic output**: `python3 tests/debug_fsr408.py > output.txt`
2. **Take photos** of your wiring setup
3. **Note exact voltages** measured with multimeter
4. **Check if it's in mock mode**: Look for "ADS1115 running in MOCK mode" in logs

## Summary

**Most likely cause**: Hardware connection issue (VCC not connected or FSR disconnected)

**Quick test**: Measure voltage at ADC input with multimeter while pressing FSR. Should see 0.5V+ with pressure.

**Solution**: Follow wiring diagram, run diagnostic script, verify each connection.