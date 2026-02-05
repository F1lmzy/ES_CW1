import time
import json
import paho.mqtt.client as mqtt


class MQTTSyncService:
    """
    Periodically sends unsynced readings from DataManager via MQTT.
    Marks rows as synced ONLY when publish succeeds.
    """

    def __init__(
        self,
        data_manager,
        broker="test.mosquitto.org",
        port=1883,
        group="SleepSensePro",
        user_id="test_user",
        device_id="test_node",
        interval_sec=30,
        batch_size=20,
        delay_between_msgs=2
    ):
        self.dm = data_manager
        self.broker = broker
        self.port = port
        self.group = group
        self.user_id = user_id
        self.device_id = device_id
        self.interval_sec = interval_sec
        self.batch_size = batch_size
        self.delay_between_msgs = delay_between_msgs

        self.topic = f"IC.embedded/{group}/{user_id}/{device_id}/sensors/fsr408"

        self.client = mqtt.Client()
        self.connected = False

    def _connect_if_needed(self):
        if self.connected:
            return True
        rc = self.client.connect(self.broker, self.port)
        self.connected = (rc == 0)
        return self.connected

    def sync_once(self):
        rows = self.dm.get_unsynced_readings(limit=self.batch_size)
        if not rows:
            return 0

        if not self._connect_if_needed():
            return 0

        sent = 0
        for r in rows:
            payload = self.dm.to_json(r)

            try:
                json.loads(payload)
            except Exception:
                continue

            info = self.client.publish(self.topic, payload)

            if info.rc == 0:
                self.dm.mark_synced([r["id"]])
                sent += 1
            else:
                break

            time.sleep(self.delay_between_msgs)

        return sent

    def run_forever(self):
        print(f"[MQTT Sync] topic={self.topic}")
        while True:
            sent = self.sync_once()
            if sent > 0:
                print(f"[MQTT Sync] sent {sent} readings")
            time.sleep(self.interval_sec)
