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

import logging
import signal
import sys
import time
from collections import deque
from pathlib import Path

# Add parent directory to path so we can import firmware modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# === YOUR IMPLEMENTATIONS ===
from firmware.communication.supabase_client import SupabaseClient
from firmware.data.data_manager import DataManager, DataManagerError
from firmware.processing.sleep_detector import SleepDetector, SleepState
from firmware.sensors.ads1115 import ADS1115, ADS1115Error
from firmware.sensors.fsr408 import FSR408, FSR408Error

# === PLACEHOLDERS FOR TEAM MEMBERS ===
try:
    from firmware.sensors.mpu6050 import MPU6050  # Accelerometer team

    MPU6050_AVAILABLE = True
except ImportError:
    MPU6050_AVAILABLE = False
    MPU6050 = None

# MQTT Removed in favor of HTTP/Supabase
MQTT_AVAILABLE = False

# === CONFIGURATION ===
DEVICE_ID = "rpi_node_1"
USER_ID = "user_001"
DB_PATH = "sleepsense.db"
I2C_BUS = 1
ADS1115_ADDRESS = 0x48
FSR_CHANNEL = 0

# SUPABASE CONFIGURATION (Replace with your actual project details)
SUPABASE_URL = "https://sntezuencvibrziosdlr.supabase.co"
SUPABASE_KEY = "sb_publishable_5wIf1WidbsAHePKBkT1qMg_DgNgHVy5"

SAMPLE_RATE = 0.1  # 10 Hz
SYNC_INTERVAL = (
    10  # Check for unsynced data every 10 seconds (more frequent for live feel)
)

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("sleepsense.log")],
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
        components["adc"] = adc
        logger.info(f"✓ ADS1115 initialized on bus {I2C_BUS}")
    except Exception as e:
        logger.error(f"Failed to initialize ADC: {e}")
        raise

    # 2. Initialize data manager
    logger.info("[2/5] Initializing data manager...")
    try:
        data_mgr = DataManager(db_path=DB_PATH, device_id=DEVICE_ID, user_id=USER_ID)
        components["data_manager"] = data_mgr
        logger.info(f"✓ DataManager initialized: {DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize data manager: {e}")
        raise

    # 3. Initialize FSR sensor
    logger.info("[3/5] Initializing FSR408 sensor...")
    try:
        fsr = FSR408(
            adc=components["adc"],
            channel=FSR_CHANNEL,
            data_manager=components["data_manager"],
        )
        components["fsr"] = fsr
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
        detector = SleepDetector(
            {
                "empty_threshold": cal["baseline_voltage"] + 0.2,
                "movement_threshold": cal["movement_threshold"],
                "sleep_delay": 60,
            }
        )
        components["detector"] = detector
        logger.info("✓ SleepDetector initialized")
    except Exception as e:
        logger.error(f"Failed to initialize sleep detector: {e}")
        raise

    # 6. Initialize placeholder components (for team integration)
    logger.info("[6/5] Checking team modules...")
    if MPU6050_AVAILABLE:
        try:
            accelerometer = MPU6050()
            components["accelerometer"] = accelerometer
            logger.info("✓ Accelerometer module loaded")
        except NotImplementedError:
            logger.info("○ Accelerometer placeholder (not yet implemented)")
    else:
        logger.info("○ Accelerometer not available (placeholder)")

    # Initialize Supabase Client
    logger.info("[6/5] Initializing Supabase client...")
    try:
        supabase = SupabaseClient(SUPABASE_URL, SUPABASE_KEY)
        components["supabase"] = supabase
        if supabase.is_configured():
            logger.info("✓ Supabase client configured")
        else:
            logger.warning(
                "! Supabase client has placeholder credentials. Update SUPABASE_URL/KEY."
            )
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")

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
    Sync unsynced data to remote server (Supabase).
    Called periodically to handle offline functionality (spec #23).

    Args:
        components: Dictionary with data_manager and supabase client
    """
    data_mgr = components.get("data_manager")
    supabase = components.get("supabase")

    if not data_mgr or not supabase:
        return

    # Get unsynced readings
    # Increased limit to 100 for better batch efficiency
    unsynced = data_mgr.get_unsynced_readings(limit=100)

    if not unsynced:
        return

    logger.info(f"Found {len(unsynced)} unsynced readings")

    try:
        # Convert sqlite3.Row objects to standard list of dicts for JSON serialization
        # and batch insert via SupabaseClient
        readings_list = [dict(row) for row in unsynced]
        
        # Use insert_batch for network optimization
        if supabase.insert_batch(readings_list):
            # If batch upload succeeds, mark all as synced locally
            ids = [r["id"] for r in readings_list]
            if data_mgr.mark_synced(ids):
                logger.info(f"Successfully synced {len(ids)} readings in batch")
            else:
                logger.error("Batch upload succeeded but failed to mark local records as synced")
        else:
            logger.warning("Batch sync failed (server returned error)")

    except Exception as e:
        logger.error(f"Error during batch sync: {e}")


def main_loop(components):
    """
    Main monitoring loop.

    Runs at 10Hz, collecting sensor data, detecting sleep states,
    and storing to SQLite using Variance-Based Event Logging.
    """
    global _running

    fsr = components["fsr"]
    detector = components["detector"]
    data_mgr = components["data_manager"]
    # supabase client is accessed in sync_unsynced_data

    last_sync = time.time()
    
    # Event Logging State Machine
    # Pre-roll buffer: holds last 0.5s of data (5 samples at 10Hz)
    buffer = deque(maxlen=5)
    is_recording = False
    post_roll_counter = 0
    POST_ROLL_SAMPLES = 5  # 0.5s post-roll

    # Print header
    print(f"\n{'VOLTAGE':>10} | {'FORCE%':>8} | {'STATE':<18} | {'VAR':>6} | {'REC'}")
    print("-" * 70)

    while _running:
        try:
            # 1. Read sensor data
            voltage = fsr.get_voltage()
            force_pct = fsr.get_force_percentage()
            variance = fsr.get_variance()

            # 2. Update sleep state
            state = detector.update(voltage, variance)
            state_val = state.value
            
            # 3. Variance-Based Event Logging Logic
            # Store data in a tuple for buffering
            current_reading = (voltage, force_pct, state_val, variance)
            
            # Threshold from detector config
            movement_threshold = detector.movement_threshold
            
            should_store = False
            
            if variance > movement_threshold:
                # Movement detected!
                if not is_recording:
                    # Start of event: Flush pre-roll buffer first
                    logger.info("Movement detected - Starting Recording")
                    for buffered_reading in buffer:
                        data_mgr.store_reading(*buffered_reading)
                    is_recording = True
                
                # While moving, keep recording and reset post-roll
                should_store = True
                post_roll_counter = POST_ROLL_SAMPLES
                
            else:
                # No movement
                if is_recording:
                    # currently in post-roll phase
                    should_store = True
                    post_roll_counter -= 1
                    if post_roll_counter <= 0:
                        is_recording = False
                        logger.info("Movement stopped - Ending Recording")
                else:
                    # Idle: just buffer
                    buffer.append(current_reading)
            
            # Store if we are recording
            if should_store:
                data_mgr.store_reading(*current_reading)

            # 4. Display status
            rec_status = "REC" if is_recording else "..."
            
            print(
                f"{voltage:>10.3f}V | {force_pct:>7.1f}% | {state_val:<18} | "
                f"{variance:>6.3f} | {rec_status}"
            )

            # 5. Periodic sync check (spec #23 - offline with sync)
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
    if "adc" in components:
        try:
            components["adc"].close()
            logger.info("ADC connection closed")
        except:
            pass

    # Print final stats
    if "data_manager" in components:
        try:
            stats = components["data_manager"].get_stats()
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
