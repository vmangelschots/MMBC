import time
import threading
import paho.mqtt.client as mqtt
from core.config_loader import get_config_value
from core.controller import BATTERY_EVCC
import os
import json
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()

MQTT_HOST = get_config_value("MQTT_HOST","localhost")
MQTT_PORT = int(get_config_value("MQTT_PORT", 1883))
MQTT_TOPIC_PREFIX = get_config_value("MQTT_TOPIC_PREFIX","mmbc/virtual")

MQTT_HA_DISCOVERY = True #get_config_value("MQTT_HA_DISCOVERY", "true").lower() == "true" TODO: Fix this in the future
MQTT_USERNAME = get_config_value("MQTT_USERNAME")
MQTT_PASSWORD = get_config_value("MQTT_PASSWORD")

HA_DISCOVERY_PREFIX = "homeassistant"
DEVICE_ID = "MMBC_Combined_Battery"
DEVICE_NAME = "MMBC Combined Battery"
EVCC_DEVICE_ID = "MMBC_EVCC"
EVCC_DEVICE_NAME = "MMBC EVCC Optimizer"

class MqttPublisher:
    def __init__(self,controller, batteries, interval=10):
        self.controller = controller
        self.batteries = batteries
        self.interval = interval
        self.client = mqtt.Client(client_id=f"mmbc-pub-{os.getpid()}")

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.running = False
        self.logger = get_logger('MqttPublisher')

    MODE_LABELS = {1: "Normal", 2: "Hold", 3: "Charge", 4: "Selfcontrol", 5: "Evcc"}
    MODE_VALUES = {label.lower(): value for value, label in MODE_LABELS.items()}

    def _publish_initial_mode(self):
        label = self.MODE_LABELS.get(self.controller.mode, "Selfcontrol")
        self.client.publish("mmbc/status/batterymode", label, retain=True)
        self.logger.info(f"[MQTT] Initial battery mode published: {label}")

    def on_mqtt_message(self,client, userdata, msg):
        if msg.topic == "mmbc/control/batterymode":
            payload = msg.payload.decode().strip().lower()
            if payload in self.MODE_VALUES:
                mode = self.MODE_VALUES[payload]
            elif payload.isdigit() and int(payload) in self.MODE_LABELS:
                mode = int(payload)
            else:
                mode = 1  # Default to normal if invalid
                self.logger.warning(f"[MQTT] Invalid battery mode received: {payload}. Defaulting to 'normal'.")

            self.controller.set_battery_mode(mode)
            # The controller can refuse a mode (e.g. selfcontrol or evcc when unavailable),
            # so report back what it actually runs instead of what was requested.
            label = self.MODE_LABELS.get(self.controller.mode, "Normal")
            self.client.publish("mmbc/status/batterymode", label, retain=True)
            self.logger.info(f"[MQTT] Batterymode set to: {label}")
    def start(self):
        try:
            if MQTT_USERNAME and MQTT_PASSWORD:
                self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
            self.client.connect(MQTT_HOST, MQTT_PORT, 60)
            self.client.on_message = self.on_mqtt_message
            self.client.loop_start()
            if MQTT_HA_DISCOVERY:
                self.publish_discovery_config()
            self.client.subscribe("mmbc/control/batterymode")
            self._publish_initial_mode()
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
                "device_class": None,
                "combined_only": True
            },
            {
                "name": "Target Action",
                "key": "target_action",
                "unit": "",
                "device_class": None,
                "combined_only": True
            },
            {
                "name": "Target Power",
                "key": "target_power",
                "unit": "W",
                "device_class": "power",
                "combined_only": True
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

        # Combined metrics
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

        # Per-battery metrics
        for index, battery in enumerate(self.batteries, start=1):
            device_id = f"MMBC_Battery_{index}"
            device_name = f"MMBC Battery {index} ({battery.name})"
            for sensor in sensors:
                if sensor.get("combined_only"):
                    continue  # these only exist for the combined battery

                topic = f"{HA_DISCOVERY_PREFIX}/sensor/{device_id}_{sensor['key']}/config"
                payload = {
                    "name": f"{device_name} {sensor['name']}",
                    "state_topic": f"{MQTT_TOPIC_PREFIX}/battery{index}/{sensor['key']}",
                    "unique_id": f"{device_id}_{sensor['key']}",
                    "device": {
                        "identifiers": [device_id],
                        "name": device_name,
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

        # Battery mode switch
        switch_payload = {
            "name": "MMBC Battery Mode",
            "unique_id": "mmbc_batterymode_select",
            "state_topic": "mmbc/status/batterymode",
            "command_topic": "mmbc/control/batterymode",
            "options": ["Normal", "Hold", "Charge"]
                       + (["Selfcontrol"] if self.controller.self_control_available else [])
                       + (["Evcc"] if self.controller.evcc_available else []),
            "icon": "mdi:battery-settings",
            "device": {
                "identifiers": [DEVICE_ID],
                "name": DEVICE_NAME,
                "manufacturer": "MMBC",
                "model": "VirtualBattery"
            }
        }
        self.client.publish(
            f"{HA_DISCOVERY_PREFIX}/select/mmbc_batterymode/config",
            json.dumps(switch_payload),
            retain=True
        )

        self.publish_evcc_discovery_config()

    def publish_evcc_discovery_config(self):
        """Discovery configs for what the EVCC optimizer is asking for."""
        if not self.controller.evcc_available:
            return

        device = {
            "identifiers": [EVCC_DEVICE_ID],
            "name": EVCC_DEVICE_NAME,
            "manufacturer": "MMBC",
            "model": "EvccOptimizer"
        }

        sensors = [
            {"name": "Suggested Action", "key": "action", "unit": "", "device_class": None},
            {"name": "Suggested Charge", "key": "charge", "unit": "W", "device_class": "power"},
            {"name": "Suggested Discharge", "key": "discharge", "unit": "W", "device_class": "power"},
        ]
        for sensor in sensors:
            payload = {
                "name": sensor["name"],
                "state_topic": f"{MQTT_TOPIC_PREFIX}/evcc/{sensor['key']}",
                "unique_id": f"{EVCC_DEVICE_ID}_{sensor['key']}",
                "device": device
            }
            if sensor["unit"]:
                payload["unit_of_measurement"] = sensor["unit"]
            if sensor["device_class"]:
                payload["device_class"] = sensor["device_class"]
                payload["state_class"] = "measurement"

            self.client.publish(
                f"{HA_DISCOVERY_PREFIX}/sensor/{EVCC_DEVICE_ID}_{sensor['key']}/config",
                json.dumps(payload),
                retain=True
            )

        binary_sensors = [
            {"name": "Actionable", "key": "actionable", "icon": "mdi:check-decagram"},
            {"name": "Following", "key": "following", "icon": "mdi:link-variant"},
        ]
        for sensor in binary_sensors:
            payload = {
                "name": sensor["name"],
                "state_topic": f"{MQTT_TOPIC_PREFIX}/evcc/{sensor['key']}",
                "unique_id": f"{EVCC_DEVICE_ID}_{sensor['key']}",
                "payload_on": "ON",
                "payload_off": "OFF",
                "icon": sensor["icon"],
                "device": device
            }
            self.client.publish(
                f"{HA_DISCOVERY_PREFIX}/binary_sensor/{EVCC_DEVICE_ID}_{sensor['key']}/config",
                json.dumps(payload),
                retain=True
            )

    def _publish_evcc_state(self):
        """Publish what EVCC asks for, and whether MMBC is acting on it.

        The suggestion is published whenever an EVCC host is configured, also outside
        Evcc mode, so you can watch what the optimizer would do before switching to it.
        """
        if not self.controller.evcc_available:
            return

        prefix = f"{MQTT_TOPIC_PREFIX}/evcc"
        suggestion = self.controller.optimizer.get_suggestion()

        if suggestion is None:
            self.client.publish(f"{prefix}/action", "unavailable")
            self.client.publish(f"{prefix}/charge", 0)
            self.client.publish(f"{prefix}/discharge", 0)
            self.client.publish(f"{prefix}/actionable", "OFF")
            self.client.publish(f"{prefix}/following", "OFF")
            return

        following = self.controller.mode == BATTERY_EVCC and suggestion.actionable
        self.client.publish(f"{prefix}/action", suggestion.action)
        self.client.publish(f"{prefix}/charge", suggestion.charge)
        self.client.publish(f"{prefix}/discharge", suggestion.discharge)
        self.client.publish(f"{prefix}/actionable", "ON" if suggestion.actionable else "OFF")
        self.client.publish(f"{prefix}/following", "ON" if following else "OFF")
    def _run(self):
        while self.running:
            try:
                total_power = 0
                total_soc = 0
                count = 0
                total_charged = 0
                total_discharged = 0
                index = 0
                for battery in self.batteries:
                    index += 1
                    name = battery.name
                    soc = battery.get_soc()
                    power = battery.get_current_wattage()
                    charged = battery.get_total_charged_kwh()
                    discharged = battery.get_total_discharged_kwh()
                    total_soc += soc
                    total_power += power
                    total_charged += charged
                    total_discharged += discharged
                    count += 1
                    self.client.publish(f"{MQTT_TOPIC_PREFIX}/battery{index}/soc", soc)
                    self.client.publish(f"{MQTT_TOPIC_PREFIX}/battery{index}/power", power)
                    self.client.publish(f"{MQTT_TOPIC_PREFIX}/battery{index}/charged_energy", round(charged, 3))
                    self.client.publish(f"{MQTT_TOPIC_PREFIX}/battery{index}/discharged_energy", round(discharged, 3))

                avg_soc = round(total_soc / count, 2) if count else 0
                state = "idle"
                if total_power > 100:
                    state = "discharging"
                elif total_power < -100:
                    state = "charging"

                # What the controller last asked for, using the same sign convention
                # as `power`: positive = discharging, negative = charging.
                target_action = self.controller.last_action
                target_power = self.controller.last_action_power
                if target_action == "charge":
                    target_power = -target_power
                elif target_action != "discharge":
                    target_power = 0

                self.client.publish(f"{MQTT_TOPIC_PREFIX}/soc", avg_soc)
                self.client.publish(f"{MQTT_TOPIC_PREFIX}/power", total_power)
                self.client.publish(f"{MQTT_TOPIC_PREFIX}/state", state)
                self.client.publish(f"{MQTT_TOPIC_PREFIX}/charged_energy", round(total_charged, 3))
                self.client.publish(f"{MQTT_TOPIC_PREFIX}/discharged_energy", round(total_discharged, 3))
                self.client.publish(f"{MQTT_TOPIC_PREFIX}/target_action", target_action)
                self.client.publish(f"{MQTT_TOPIC_PREFIX}/target_power", target_power)
                self._publish_evcc_state()

            except Exception as e:
                print(f"[MQTT] Error during publish: {e}")

            time.sleep(self.interval)
