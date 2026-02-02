import time
import board
import busio
import numpy as np
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# --- CONFIGURATION ---
# Adjust these based on your calibration tests (Step 2 below)
EMPTY_BED_THRESHOLD = 2.6   # Below this voltage = Bed is Empty (Check your baseline!)
MOVEMENT_THRESHOLD = 0.05   # Std Dev above this = Moving
SLEEP_DELAY_SECONDS = 60    # Time of stillness before considered "Asleep"

SAMPLE_RATE = 0.1           # How often to read sensor (seconds)
WINDOW_SIZE = 20            # How many samples to analyze at once (20 * 0.1 = 2 seconds)

# --- SETUP ---
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
ads.gain = 1
chan = AnalogIn(ads, 0) # FSR on A0

class SleepState:
    EMPTY = "Empty Bed"
    AWAKE = "Present (Awake)"
    ASLEEP = "Asleep"
    MOVING = "Tossing/Turning"

current_state = SleepState.EMPTY
last_move_time = time.time()
data_buffer = []

print(f"Starting Sleep Monitor...")
print(f"{'VOLTAGE':>8} | {'VARIANCE':>8} | {'STATUS':<15}")
print("-" * 45)

while True:
    try:
        # 1. Collect Data
        raw_voltage = chan.voltage
        data_buffer.append(raw_voltage)

        # Only process when we have a full window of data
        if len(data_buffer) >= WINDOW_SIZE:
            
            # 2. Calculate Math Metrics
            avg_voltage = np.mean(data_buffer) # Detects Weight
            std_dev = np.std(data_buffer)      # Detects Movement (Variance)
            
            # Clear buffer for next window
            data_buffer = [] 

            # 3. Determine State
            now = time.time()
            
            # LOGIC TREE
            if avg_voltage < EMPTY_BED_THRESHOLD:
                # If voltage is lower than the weight of a person
                new_state = SleepState.EMPTY
                last_move_time = now # Reset sleep timer
                
            elif std_dev > MOVEMENT_THRESHOLD:
                # High variance means spikes/movement
                new_state = SleepState.MOVING
                last_move_time = now # Reset sleep timer because they moved
                
            else:
                # Person is present but variance is low (Still)
                time_still = now - last_move_time
                if time_still > SLEEP_DELAY_SECONDS:
                    new_state = SleepState.ASLEEP
                else:
                    new_state = SleepState.AWAKE

            # 4. Output Data
            # avg_voltage: Tells us if they are there
            # std_dev: Tells us how much they are moving
            print(f"{avg_voltage:>8.3f}V | {std_dev:>8.3f} | {new_state} ({int(now-last_move_time)}s still)")

        time.sleep(SAMPLE_RATE)

    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f"Error: {e}")
