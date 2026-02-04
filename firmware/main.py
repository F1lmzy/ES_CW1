"""
SleepSense Pro - Smart Bed Monitor
Main Entry Point (Specification #8)

This is the point of entry for code on the embedded device.
Integrates FSR408 sensor, sleep detection, and data management.
Provides placeholder modules for team integration.

Architecture:
- I2C sensors: Custom byte-level drivers (no existing libraries)
- Data storage: SQLite with 30-day retention
- Communication: JSON API for MQTT team
- Offline functionality: Local storage with sync tracking
"""

import time
import sys
import signal
import logging
from pathlib import Path

# Add parent directory to path so we can import firmware modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# === YOUR IMPLEMENTATIONS ===
from firmware.sensors.ads1115 import ADS1115, ADS1115Error
from firmware.sensors.fsr408 import FSR408, FSR408Error
from firmware.processing.sleep_detector import SleepDetector, SleepState
from firmware.data.data_manager import DataManager, DataManagerError

# === PLACEHOLDERS FOR TEAM MEMBERS ===
try:
    from firmware.sensors.mpu6050 import MPU6050  # Accelerometer team
    MPU6050_AVAILABLE = True
except ImportError:
    MPU6050_AVAILABLE = False
    MPU6050 = None

try:
    from firmware.communication.mqtt_client import MQTTClient  # MQTT team
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    MQTTClient = None

# === CONFIGURATION ===
DEVICE_ID = "rpi_node_1"
USER_ID = "user_001"
DB_PATH = "sleepsense.db"
I2C_BUS = 1
ADS1115_ADDRESS = 0x48
FSR_CHANNEL = 0

SAMPLE_RATE = 0.1  # 10 Hz
SYNC_INTERVAL = 60  # Check for unsynced data every 60 seconds

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('sleepsense.log')
    ]
)
logger = logging.getLogger(__name__)

# === GLOBAL STATE ===
_components = {}
_running = True


def signal_handler(sig, frame):
    """Handle Ctrl+C for graceful shutdown"""
    global _running
    logger.info("Shutdown signal received...")
    _running = False


def initialize_components():
    """
    Initialize all hardware and software components.

    Returns:
        Dictionary with initialized components
    """
    logger.info("=" * 60)
    logger.info("SleepSense Pro - Smart Bed Monitor")
    logger.info("=" * 60)

    components = {}

    # 1. Initialize I2C bus and ADC
    logger.info("[1/5] Initializing I2C bus and ADS1115 ADC...")
    try:
        adc = ADS1115(bus=I2C_BUS, address=ADS1115_ADDRESS)
        if not adc.is_connected():
            logger.warning("ADS1115 not detected! Check I2C connection.")
            logger.info("Continuing in mock mode...")
            adc = ADS1115(bus=I2C_BUS, address=ADS1115_ADDRESS, mock=True)
        components['adc'] = adc
        logger.info(f"✓ ADS1115 initialized on bus {I2C_BUS}")
    except Exception as e:
        logger.error(f"Failed to initialize ADC: {e}")
        raise

    # 2. Initialize data manager
    logger.info("[2/5] Initializing data manager...")
    try:
        data_mgr = DataManager(
            db_path=DB_PATH,
            device_id=DEVICE_ID,
            user_id=USER_ID
        )
        components['data_manager'] = data_mgr
        logger.info(f"✓ DataManager initialized: {DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize data manager: {e}")
        raise

    # 3. Initialize FSR sensor
    logger.info("[3/5] Initializing FSR408 sensor...")
    try:
        fsr = FSR408(
            adc=components['adc'],
            channel=FSR_CHANNEL,
            data_manager=components['data_manager']
        )
        components['fsr'] = fsr
        logger.info(f"✓ FSR408 initialized on channel {FSR_CHANNEL}")
    except Exception as e:
        logger.error(f"Failed to initialize FSR: {e}")
        raise

    # 4. Check/load calibration
    logger.info("[4/5] Checking calibration...")
    try:
        if fsr.is_calibrated():
            fsr.load_calibration()
            logger.info("✓ Calibration loaded from database")
        else:
            logger.info("! No calibration found - running calibration routine")
            logger.info("Please follow the prompts...")
            fsr.calibrate(interactive=True)
    except Exception as e:
        logger.error(f"Calibration failed: {e}")
        raise

    # 5. Initialize sleep detector
    logger.info("[5/5] Initializing sleep detector...")
    try:
        cal = fsr.get_calibration()
        detector = SleepDetector({
            'empty_threshold': cal['baseline_voltage'] + 0.2,
            'movement_threshold': cal['movement_threshold'],
            'sleep_delay': 60
        })
        components['detector'] = detector
        logger.info("✓ SleepDetector initialized")
    except Exception as e:
        logger.error(f"Failed to initialize sleep detector: {e}")
        raise

    # 6. Initialize placeholder components (for team integration)
    logger.info("[6/5] Checking team modules...")
    if MPU6050_AVAILABLE:
        try:
            accelerometer = MPU6050()
            components['accelerometer'] = accelerometer
            logger.info("✓ Accelerometer module loaded")
        except NotImplementedError:
            logger.info("○ Accelerometer placeholder (not yet implemented)")
    else:
        logger.info("○ Accelerometer not available (placeholder)")

    if MQTT_AVAILABLE:
        try:
            mqtt_client = MQTTClient()
            components['mqtt_client'] = mqtt_client
            logger.info("✓ MQTT client loaded")
        except NotImplementedError:
            logger.info("○ MQTT client placeholder (not yet implemented)")
    else:
        logger.info("○ MQTT client not available (placeholder)")

    # Print stats
    stats = data_mgr.get_stats()
    logger.info(f"\nDatabase Status:")
    logger.info(f"  Total readings: {stats.get('total_readings', 0)}")
    logger.info(f"  Unsynced readings: {stats.get('unsynced_readings', 0)}")
    logger.info(f"  Database size: {stats.get('database_size_mb', 0)} MB")

    logger.info("\n" + "=" * 60)
    logger.info("System Ready - Starting Monitoring Loop")
    logger.info("=" * 60)

    return components


def sync_unsynced_data(components):
    """
    Sync unsynced data to remote server.
    Called periodically to handle offline functionality (spec #23).

    Args:
        components: Dictionary with data_manager and optionally mqtt_client
    """
    data_mgr = components.get('data_manager')
    mqtt_client = components.get('mqtt_client')

    if not data_mgr:
        return

    # Get unsynced readings
    unsynced = data_mgr.get_unsynced_readings(limit=50)

    if not unsynced:
        return

    logger.info(f"Found {len(unsynced)} unsynced readings")

    if mqtt_client and MQTT_AVAILABLE:
        try:
            # TODO: MQTT team - implement actual sync logic
            # for reading in unsynced:
            #     json_data = data_mgr.to_json(reading)
            #     mqtt_client.publish("sleepsense/data", json_data)

            # Mark as synced (for now, assume all successful)
            ids = [r['id'] for r in unsynced]
            data_mgr.mark_synced(ids)
            logger.info(f"Synced {len(ids)} readings to remote")

        except Exception as e:
            logger.error(f"Failed to sync data: {e}")
    else:
        logger.debug(f"MQTT not available, {len(unsynced)} readings queued locally")


def main_loop(components):
    """
    Main monitoring loop.

    Runs at 10Hz, collecting sensor data, detecting sleep states,
    storing to SQLite, and preparing JSON for MQTT transmission.
    """
    global _running

    fsr = components['fsr']
    detector = components['detector']
    data_mgr = components['data_manager']
    mqtt_client = components.get('mqtt_client')

    last_sync = time.time()

    # Print header
    print(f"\n{'VOLTAGE':>10} | {'FORCE%':>8} | {'STATE':<18} | {'VAR':>6} | {'INFO'}")
    print("-" * 70)

    while _running:
        try:
            # 1. Read sensor data
            voltage = fsr.get_voltage()
            force_pct = fsr.get_force_percentage()
            variance = fsr.get_variance()

            # 2. Update sleep state
            state = detector.update(voltage, variance)

            # 3. Store to SQLite (offline functionality - spec #23)
            data_mgr.store_reading(
                voltage=voltage,
                force_percent=force_pct,
                state=state.value,
                variance=variance
            )

            # 4. Get JSON for MQTT team (clean API)
            sensor_data = fsr.get_sensor_data()
            sensor_data['state'] = state.value
            json_payload = data_mgr.to_json(sensor_data)

            # TODO: MQTT team - publish here
            # if mqtt_client and MQTT_AVAILABLE:
            #     mqtt_client.publish("sleepsense/data", json_payload)

            # 5. Display status
            time_still = detector.get_time_since_last_movement()
            info = f"({int(time_still)}s still)" if state == SleepState.ASLEEP else ""

            print(f"{voltage:>10.3f}V | {force_pct:>7.1f}% | {state.value:<18} | "
                  f"{variance:>6.3f} | {info}")

            # 6. Periodic sync check (spec #23 - offline with sync)
            now = time.time()
            if now - last_sync > SYNC_INTERVAL:
                sync_unsynced_data(components)
                last_sync = now

            # 7. Sleep until next sample
            time.sleep(SAMPLE_RATE)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(1)  # Brief pause before retry


def shutdown(components):
    """Graceful shutdown and cleanup"""
    logger.info("\nShutting down...")

    # Try to sync any remaining data
    try:
        sync_unsynced_data(components)
    except Exception as e:
        logger.error(f"Error during final sync: {e}")

    # Close hardware connections
    if 'adc' in components:
        try:
            components['adc'].close()
            logger.info("ADC connection closed")
        except:
            pass

    # Print final stats
    if 'data_manager' in components:
        try:
            stats = components['data_manager'].get_stats()
            logger.info(f"Final database stats: {stats}")
        except:
            pass

    logger.info("Shutdown complete. Goodbye!")


def main():
    """
    Main entry point (Specification #8)

    Initializes all components and runs the monitoring loop.
    Handles graceful shutdown on Ctrl+C.
    """
    global _components

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize all components
        _components = initialize_components()

        # Run main loop
        main_loop(_components)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        shutdown(_components)


if __name__ == "__main__":
    main()
