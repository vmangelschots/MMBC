import time
import threading
import paho.mqtt.client as mqtt
import os
from dotenv import load_dotenv

load_dotenv()

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "mmbc/virtual")

class MqttPublisher:
    def __init__(self, batteries, interval=10):
        self.batteries = batteries
        self.interval = interval
        self.client = mqtt.Client()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.running = False

    def start(self):
        self.client.connect(MQTT_HOST, MQTT_PORT, 60)
        self.client.loop_start()
        self.running = True
        self.thread.start()

    def stop(self):
        self.running = False
        self.client.loop_stop()
        self.client.disconnect()

    def _run(self):
        while self.running:
            try:
                total_power = 0
                total_soc = 0
                count = 0
                for battery in self.batteries:
                    soc = battery.get_soc()
                    power = battery.get_current_wattage()
                    total_soc += soc
                    total_power += power
                    count += 1

                avg_soc = round(total_soc / count, 2) if count else 0
                state = "idle"
                if total_power > 100:
                    state = "discharging"
                elif total_power < -100:
                    state = "charging"

                self.client.publish(f"{MQTT_TOPIC_PREFIX}/soc", avg_soc)
                self.client.publish(f"{MQTT_TOPIC_PREFIX}/power", total_power)
                self.client.publish(f"{MQTT_TOPIC_PREFIX}/state", state)

            except Exception as e:
                print(f"[MQTT] Error during publish: {e}")

            time.sleep(self.interval)
