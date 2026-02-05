import time
import threading
import numpy as np
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

from firmware.data.data_manager import DataManager
from mqtt_sync_service import MQTTSyncService


# ===================== CONFIG =====================

EMPTY_BED_THRESHOLD = 2.6
MOVEMENT_THRESHOLD = 0.05
SLEEP_DELAY_SECONDS = 60

SAMPLE_RATE = 0.1
WINDOW_SIZE = 20

DB_PATH = "sleepsense.db"
DEVICE_ID = "test_node"
USER_ID = "test_user"
MQTT_GROUP = "SleepSensePro"

# If you do not have sensor connected yet, set this to False
USE_REAL_SENSOR = True

# ================================================


class SleepState:
    EMPTY = "Empty Bed"
    AWAKE = "Present (Awake)"
    ASLEEP = "Asleep"
    MOVING = "Tossing/Turning"


def main():

    print("Starting SleepSense Pro Monitor")

    # ---------- Data Manager ----------
    dm = DataManager(
        db_path=DB_PATH,
        device_id=DEVICE_ID,
        user_id=USER_ID
    )

    # ---------- MQTT Auto Sync ----------
    sync_service = MQTTSyncService(
        data_manager=dm,
        group=MQTT_GROUP,
        user_id=USER_ID,
        device_id=DEVICE_ID
    )

    sync_thread = threading.Thread(
        target=sync_service.run_forever,
        daemon=True
    )
    sync_thread.start()

    print("MQTT auto-sync started")

    # ---------- Sensor Setup ----------
    if USE_REAL_SENSOR:
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)
        ads.gain = 1
        chan = AnalogIn(ads, 0)
        print("Using real ADS1115 sensor")
    else:
        import random
        print("Using simulated sensor values")

    # ---------- Variables ----------
    last_move_time = time.time()
    data_buffer = []

    print(f"{'VOLTAGE':>8} | {'VAR':>6} | {'STATE':<20}")
    print("-" * 45)

    # ---------- Main Loop ----------
    while True:
        try:

            if USE_REAL_SENSOR:
                raw_voltage = chan.voltage
            else:
                raw_voltage = random.uniform(2.0, 3.2)

            data_buffer.append(raw_voltage)

            if len(data_buffer) >= WINDOW_SIZE:

                avg_voltage = float(np.mean(data_buffer))
                std_dev = float(np.std(data_buffer))
                data_buffer.clear()

                now = time.time()

                if avg_voltage < EMPTY_BED_THRESHOLD:
                    new_state = SleepState.EMPTY
                    last_move_time = now

                elif std_dev > MOVEMENT_THRESHOLD:
                    new_state = SleepState.MOVING
                    last_move_time = now

                else:
                    time_still = now - last_move_time
                    if time_still > SLEEP_DELAY_SECONDS:
                        new_state = SleepState.ASLEEP
                    else:
                        new_state = SleepState.AWAKE

                dm.store_reading(
                    voltage=avg_voltage,
                    force_percent=0.0,
                    state=new_state,
                    variance=std_dev
                )

                print(
                    f"{avg_voltage:>8.3f} | "
                    f"{std_dev:>6.3f} | "
                    f"{new_state:<20}"
                )

            time.sleep(SAMPLE_RATE)

        except KeyboardInterrupt:
            print("Shutting down...")
            break

        except Exception as e:
            print("Runtime error:", e)
            time.sleep(1)


if __name__ == "__main__":
    main()
