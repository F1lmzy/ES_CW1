import time
import json
import random
import sys

# Try to import paho-mqtt
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt library is required.")
    print("Please install it using: pip install paho-mqtt")
    sys.exit(1)

# Configuration
BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "sleepsense/user_001/rpi_node_1/sensors/fsr408"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT Broker: {BROKER}")
    else:
        print(f"Failed to connect, return code {rc}")

def generate_data(cycle_pos):
    """
    Generate mock sensor data simulating the actual firmware states.
    cycle_pos: 0.0 to 1.0 representing progress through a sleep cycle
    """
    
    # Logic to simulate the firmware states
    if cycle_pos < 0.1:
        # DOZING (Awake)
        state = "Present (Awake)"
        variance = random.uniform(0.02, 0.1)
        force = random.uniform(10, 30)
    elif cycle_pos < 0.2:
        # DOZING (Moving to sleep)
        state = "Tossing/Turning"
        variance = random.uniform(0.1, 0.5)
        force = random.uniform(20, 40)
    elif cycle_pos < 0.4:
        # SNOOZING (Light Sleep)
        state = "Asleep"
        variance = random.uniform(0.01, 0.04) # > 0.008
        force = random.uniform(40, 60)
    elif cycle_pos < 0.7:
        # SLUMBERING (Deep Sleep)
        state = "Asleep"
        variance = random.uniform(0.001, 0.007) # < 0.008
        force = random.uniform(50, 60)
    elif cycle_pos < 0.9:
        # SNOOZING (Light Sleep)
        state = "Asleep"
        variance = random.uniform(0.01, 0.04)
        force = random.uniform(40, 60)
    else:
        # Waking up
        state = "Present (Awake)"
        variance = random.uniform(0.05, 0.2)
        force = random.uniform(10, 30)

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sensor_type": "fsr408",
        "channel": 0,
        "voltage": force / 20.0,
        "force_percent": force,
        "state": state,
        "variance": variance,
        "device_id": "rpi_node_1",
        "user_id": "user_001"
    }

def main():
    client = mqtt.Client()
    client.on_connect = on_connect

    print(f"Connecting to {BROKER}...")
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    print(f"Publishing to topic: {TOPIC}")
    print("Press Ctrl+C to stop...")

    cycle_duration = 60 # seconds for a full cycle
    start_time = time.time()

    try:
        while True:
            # Calculate position in the cycle (0.0 to 1.0)
            elapsed = time.time() - start_time
            cycle_pos = (elapsed % cycle_duration) / cycle_duration
            
            data = generate_data(cycle_pos)
            payload = json.dumps(data)
            
            client.publish(TOPIC, payload)
            
            # Simple log
            var_status = "Deep" if data['variance'] < 0.008 else "Light"
            print(f"Sent: {data['state']:<16} | Var: {data['variance']:.4f} ({var_status})")
            
            time.sleep(1) # Publish every second
            
    except KeyboardInterrupt:
        print("\nStopping...")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
