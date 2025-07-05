import time
import threading
import paho.mqtt.client as mqtt
import os
import json
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "mmbc/virtual")

MQTT_HA_DISCOVERY = os.getenv("MQTT_HA_DISCOVERY", "true").lower() == "true"

HA_DISCOVERY_PREFIX = "homeassistant"
DEVICE_ID = "MMBC_Combined_Battery"
DEVICE_NAME = "MMBC Combined Battery"

class MqttPublisher:
    def __init__(self,controller, batteries, interval=10):
        self.controller = controller
        self.batteries = batteries
        self.interval = interval
        self.client = mqtt.Client()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.running = False
        self.logger = get_logger('MqttPublisher')

    def on_mqtt_message(self,client, userdata, msg):
        if msg.topic == "mmbc/control/batterymode":
            payload = msg.payload.decode().strip().lower()
            if payload in ["normal", "hold", "charge"]:
                if payload == "normal":
                    mode = 1  # Normal mode
                elif payload == "hold":
                    mode = 2  # Hold mode
                elif payload == "charge":
                    mode = 3  # Charge mode
                else:
                    mode = 1  # Default to normal if invalid
                    self.logger.warning(f"[MQTT] Invalid battery mode received: {payload}. Defaulting to 'normal'.")
                    payload = "normal"
            self.controller.set_battery_mode(mode)
            self.client.publish("mmbc/status/batterymode", str(payload).lower(), retain=True)
            self.logger.info(f"[MQTT] Batterymode set to: {payload}")
    def start(self):
        try:
            self.client.connect(MQTT_HOST, MQTT_PORT, 60)
            self.client.on_message = self.on_mqtt_message
            self.client.loop_start()
            if MQTT_HA_DISCOVERY:
                self.publish_discovery_config()
            self.client.subscribe("mmbc/control/batterymode")
            self.running = True
            self.thread.start()
        except Exception as e:
            self.logger.error(f"[MQTT] Failed to connect: {e}")

    def stop(self):
        self.running = False
        self.client.loop_stop()
        self.client.disconnect()
    def publish_discovery_config(self):
        sensors = [
            {
                "name": "SoC",
                "key": "soc",
                "unit": "%",
                "device_class": "battery"
            },
            {
                "name": "Power",
                "key": "power",
                "unit": "W",
                "device_class": "power"
            },
            {
                "name": "State",
                "key": "state",
                "unit": "",
                "device_class": None
            },
            {
                "name": "Charged Energy",
                "key": "charged_energy",
                "unit": "kWh",
                "device_class": "energy",
                "state_class": "total_increasing"
            },
            {
                "name": "Discharged Energy",
                "key": "discharged_energy",
                "unit": "kWh",
                "device_class": "energy",
                "state_class": "total_increasing"
            }
        ]

        for sensor in sensors:
            topic = f"{HA_DISCOVERY_PREFIX}/sensor/{DEVICE_ID}_{sensor['key']}/config"
            payload = {
                "name": f"{sensor['name']}",
                "state_topic": f"{MQTT_TOPIC_PREFIX}/{sensor['key']}",
                "unique_id": f"{DEVICE_ID}_{sensor['key']}",
                "device": {
                    "identifiers": [DEVICE_ID],
                    "name": DEVICE_NAME,
                    "manufacturer": "MMBC",
                    "model": "VirtualBattery"
                }
            }
            if sensor["unit"]:
                payload["unit_of_measurement"] = sensor["unit"]
            if sensor["device_class"]:
                payload["device_class"] = sensor["device_class"]
                payload["state_class"] = sensor.get("state_class", "measurement")
            
            self.client.publish(topic, json.dumps(payload), retain=True)
        #publish the discovery payload for discharge blocked switch
        switch_payload = {
            "name": "MMBC Battery Mode",
            "unique_id": "mmbc_batterymode_select",
            "state_topic": "mmbc/status/batterymode",
            "command_topic": "mmbc/control/batterymode",
            "options": ["Normal", "Hold", "Charge"],
            "icon": "mdi:battery-settings",
            "device": {
                "identifiers": [DEVICE_ID],
                "name": DEVICE_NAME,
                "manufacturer": "MMBC",
                "model": "VirtualBattery"
            }
        }
        self.client.publish(
            "homeassistant/select/mmbc_batterymode/config",
            json.dumps(switch_payload),
            retain=True
        )
    def _run(self):
        while self.running:
            try:
                total_power = 0
                total_soc = 0
                count = 0
                total_charged = 0
                total_discharged = 0
                for battery in self.batteries:
                    soc = battery.get_soc()
                    power = battery.get_current_wattage()
                    charged = battery.get_total_charged_kwh()
                    discharged = battery.get_total_discharged_kwh()
                    total_soc += soc
                    total_power += power
                    total_charged += charged
                    total_discharged += discharged
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
                self.client.publish(f"{MQTT_TOPIC_PREFIX}/charged_energy", round(total_charged, 3))
                self.client.publish(f"{MQTT_TOPIC_PREFIX}/discharged_energy", round(total_discharged, 3))

            except Exception as e:
                print(f"[MQTT] Error during publish: {e}")

            time.sleep(self.interval)
