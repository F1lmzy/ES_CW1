# SleepSense Pro - Smart Bed Monitor
## FSR408 Sensor Component Implementation

### Project Overview
This is the FSR408 (Force Sensitive Resistor) component implementation for the SleepSense Pro smart bed monitoring system. This implementation meets all embedded systems coursework specifications.

---

## ✅ Specifications Compliance

| Spec | Requirement | Implementation |
|------|-------------|----------------|
| **#8** | Entry point in `main.py` | ✅ `firmware/main.py` - Clean entry point with signal handling |
| **#10** | Byte-level I2C, no existing libraries | ✅ `ads1115.py` - Custom smbus2 implementation, no adafruit |
| **#9** | Scalability | ✅ Modular design with JSON API for team integration |
| **#23** | Offline functionality | ✅ SQLite storage with 30-day retention and sync tracking |
| **#14** | Analog electronics | ✅ FSR408 analog sensor with voltage divider |
| **#4** | Appropriate sampling | ✅ 10Hz sampling for bed occupancy detection |

---

## 📁 Project Structure

```
firmware/
├── main.py                      # Entry point (spec #8)
├── sensors/
│   ├── __init__.py
│   ├── ads1115.py              # Custom I2C driver (YOUR CODE - spec #10)
│   ├── fsr408.py               # FSR interface + calibration (YOUR CODE)
│   └── mpu6050.py              # EMPTY - Placeholder for accelerometer team
├── processing/
│   ├── __init__.py
│   └── sleep_detector.py       # State machine logic (refactored from main.py)
├── data/
│   ├── __init__.py
│   └── data_manager.py         # SQLite + JSON for MQTT (YOUR CODE)
└── communication/
    ├── __init__.py
    └── mqtt_client.py          # EMPTY - Placeholder for MQTT team

tests/
├── test_ads1115.py             # Unit tests for I2C driver
├── test_fsr408.py              # Unit tests for FSR interface
├── test_data_manager.py        # Unit tests for data management
└── test_integration.py         # End-to-end integration tests
```

---

## 🔧 Hardware Setup

### Components Required
- **Raspberry Pi 2** (main controller)
- **ADS1115** 16-bit ADC (I2C address: 0x48)
- **FSR408** Force Sensitive Resistor (Interlink Electronics)
- **10kΩ resistor** (voltage divider)
- Breadboard and jumper wires

### Wiring Diagram
```
FSR408 (Force Sensitive Resistor)
    |
    |---[FSR]---+---[10kΩ]--- GND
    |           |
    |          AIN0 (ADS1115)
    |
    +5V (Raspberry Pi)

ADS1115 (I2C ADC)
    VDD  → 3.3V (Pi)
    GND  → GND (Pi)
    SDA  → GPIO 2 (SDA1)
    SCL  → GPIO 3 (SCL1)
    AIN0 → Voltage divider output
```

---

## 🚀 Installation & Setup

### 1. Install Dependencies
```bash
# On Raspberry Pi
sudo apt-get update
sudo apt-get install python3-pip python3-venv i2c-tools

# Enable I2C interface
sudo raspi-config
# Select: Interfacing Options > I2C > Enable

# Install Python packages
pip3 install smbus2
```

### 2. Verify Hardware Connection
```bash
# Check I2C devices
sudo i2cdetect -y 1

# Should show 0x48 (ADS1115)
```

### 3. First-Time Calibration
```bash
cd firmware
python3 main.py
```

The system will:
1. Initialize I2C bus and ADS1115
2. Check for existing calibration in SQLite
3. If not calibrated, run interactive calibration:
   - Prompt: "Remove all weight from bed, press ENTER"
   - Record 50 samples over 5 seconds (baseline)
   - Prompt: "Lie on bed normally, press ENTER"
   - Record 50 samples (occupied threshold)
   - Calculate movement threshold
   - Save to SQLite for future runs

---

## 📊 Features

### 1. Custom I2C Driver (`ads1115.py`)
- **Spec #10 Compliant**: Byte-level I2C using smbus2
- No adafruit libraries used
- Direct register read/write
- 16-bit ADC conversion
- Error retry logic (3 attempts)
- Mock mode for testing without hardware

### 2. FSR408 Interface (`fsr408.py`)
- Dynamic calibration (first-time only, stored in SQLite)
- Force percentage calculation (0-100%)
- Occupancy detection with configurable threshold
- Movement detection via variance calculation
- Rolling window for noise reduction
- Clean `get_sensor_data()` API for MQTT team

### 3. Sleep State Detection (`sleep_detector.py`)
- 4-state state machine:
  - **EMPTY**: No weight detected
  - **AWAKE**: Person present, recently moved
  - **MOVING**: High variance (tossing/turning)
  - **ASLEEP**: Still for >60 seconds
- Time tracking in each state
- Refactored from original main.py logic

### 4. Data Management (`data_manager.py`)
- **SQLite offline storage** (spec #23)
- 30-day automatic data retention
- Sync status tracking for MQTT
- JSON serialization for team integration
- In-memory queue for SQLite failures
- Error handling with retry logic

### 5. Main Entry Point (`main.py`)
- Clean entry point (spec #8)
- Graceful shutdown (Ctrl+C handling)
- 10Hz sampling loop
- Integrated calibration check
- Placeholder modules for team integration
- Real-time status display

---

## 🔌 Clean API for Team Integration

### For MQTT Team
```python
from firmware.data.data_manager import DataManager
from firmware.sensors.fsr408 import FSR408

# Get sensor data
sensor_data = fsr.get_sensor_data()
sensor_data['state'] = detector.get_state_name()

# Convert to JSON for MQTT
json_payload = data_manager.to_json(sensor_data)
# Result: {"timestamp": "...", "voltage": 2.45, "state": "Asleep", ...}

# Get unsynced readings
unsynced = data_manager.get_unsynced_readings()
for reading in unsynced:
    mqtt_client.publish("sleepsense/data", data_manager.to_json(reading))
    # After successful publish:
    data_manager.mark_synced([reading['id']])
```

### For Accelerometer Team
```python
from firmware.sensors.mpu6050 import MPU6050

# MPU6050 placeholder ready for implementation
accelerometer = MPU6050(bus=1, address=0x68)
accel_data = accelerometer.read_acceleration()

# Integration in main.py is ready:
# - Import MPU6050
# - Initialize in component setup
# - Access via components['accelerometer']
```

---

## 🧪 Testing

### Run Unit Tests
```bash
cd tests

# Test I2C driver
python3 test_ads1115.py

# Test FSR interface
python3 test_fsr408.py

# Test data management
python3 test_data_manager.py

# Run all tests
python3 -m unittest discover -v
```

### Test Coverage
- **test_ads1115.py**: 15+ tests for byte-level I2C operations
- **test_fsr408.py**: 20+ tests for calibration and force detection
- **test_data_manager.py**: 20+ tests for SQLite and JSON
- **test_integration.py**: 10+ end-to-end integration tests

---

## 📝 JSON Schema for MQTT

```json
{
  "timestamp": "2026-02-03T14:30:00",
  "sensor_type": "fsr408",
  "channel": 0,
  "voltage": 2.45,
  "force_percent": 67.5,
  "state": "Asleep",
  "variance": 0.02,
  "device_id": "rpi_node_1",
  "user_id": "user_001"
}
```

---

## ⚙️ Configuration

Edit these values in `firmware/main.py`:

```python
# Device identification
DEVICE_ID = "rpi_node_1"
USER_ID = "user_001"

# Hardware settings
I2C_BUS = 1
ADS1115_ADDRESS = 0x48
FSR_CHANNEL = 0

# Sampling
SAMPLE_RATE = 0.1  # 10 Hz
SYNC_INTERVAL = 60  # Check for unsynced data every 60s

# Database
DB_PATH = "sleepsense.db"
```

---

## 🔍 Debugging

### Enable Debug Logging
```python
# In main.py or your test script
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Database Contents
```bash
# Using sqlite3 CLI
sqlite3 sleepsense.db "SELECT * FROM readings LIMIT 10;"
sqlite3 sleepsense.db "SELECT * FROM calibration;"
```

### Monitor I2C Bus
```bash
# Real-time I2C monitoring
sudo i2cdetect -y 1

# Test with bus pirate or similar
```

---

## 📚 Documentation References

- **ADS1115 Datasheet**: [Texas Instruments](https://www.ti.com/lit/ds/symlink/ads1115.pdf)
- **FSR408 Datasheet**: Interlink Electronics Force Sensing Resistor
- **Raspberry Pi I2C**: [Official Documentation](https://www.raspberrypi.org/documentation/hardware/raspberrypi/i2c/README.md)

---

## 👥 Team Integration Notes

### For Your Group Project

**Your Responsibilities (COMPLETE):**
- ✅ FSR408 sensor interface
- ✅ ADS1115 custom I2C driver (spec #10 compliant)
- ✅ SQLite offline storage (spec #23)
- ✅ JSON API for data transmission
- ✅ Sleep state detection logic
- ✅ First-time calibration system
- ✅ Main.py entry point (spec #8)

**Accelerometer Team (TO DO):**
- Implement `firmware/sensors/mpu6050.py`
- Use byte-level I2C (no adafruit libraries)
- Provide `read_acceleration()` and `read_gyro()` methods
- Follow the placeholder structure provided

**MQTT/Communication Team (TO DO):**
- Implement `firmware/communication/mqtt_client.py`
- Connect to MQTT broker
- Use `data_manager.get_unsynced_readings()` for sync
- Call `data_manager.to_json()` for payload format
- Mark readings synced via `data_manager.mark_synced()`

---

## 🎓 Advanced Features (Optional)

To achieve "Advanced Functionality" marks, consider implementing:

1. **Multiple FSRs**: Add 2nd FSR on AIN1 for pressure distribution
2. **Analog filtering**: Hardware low-pass filter on FSR signal
3. **Sleep quality scoring**: Algorithm based on movement patterns
4. **REST API**: Local HTTP endpoint for debugging
5. **Mechanical enclosure**: 3D printable case design

---

## 📄 License

This implementation is for educational purposes as part of an embedded systems coursework project.

---

## 🆘 Troubleshooting

### "No module named 'smbus2'"
```bash
pip3 install smbus2
```

### "I2C bus not accessible"
```bash
# Enable I2C in raspi-config
sudo raspi-config
# Then reboot
sudo reboot
```

### "ADS1115 not detected"
```bash
# Check wiring
sudo i2cdetect -y 1
# Verify 0x48 appears in the grid
```

### "Calibration failed"
- Ensure FSR is properly positioned under mattress
- Check voltage divider wiring (10kΩ resistor)
- Verify ADS1115 PGA setting (±4.096V)
- Run with `interactive=True` for guided calibration

---

## 📊 Expected Output

When running `python3 firmware/main.py`:

```
============================================================
SleepSense Pro - Smart Bed Monitor
============================================================
[1/5] Initializing I2C bus and ADS1115 ADC...
✓ ADS1115 initialized on bus 1
[2/5] Initializing data manager...
✓ DataManager initialized: sleepsense.db
[3/5] Initializing FSR408 sensor...
✓ FSR408 initialized on channel 0
[4/5] Checking calibration...
! No calibration found - running calibration routine
Please follow the prompts...
Step 1: Remove all weight from bed, press ENTER
...
✓ Calibration Complete!
[5/5] Initializing sleep detector...
✓ SleepDetector initialized

Database Status:
  Total readings: 0
  Unsynced readings: 0
  Database size: 0.01 MB

============================================================
System Ready - Starting Monitoring Loop
============================================================

   VOLTAGE |  FORCE% | STATE              |    VAR | INFO
----------------------------------------------------------------------
    2.456V |   75.0% | Present (Awake)    |  0.023 |
    2.452V |   74.8% | Present (Awake)    |  0.018 |
    2.458V |   75.1% | Asleep             |  0.015 | (65s still)
```

---

**Implementation complete and ready for testing on Raspberry Pi 2!**

For questions or issues, refer to the test files or add logging to debug specific components.
