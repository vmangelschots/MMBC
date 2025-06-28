import signal
import sys
from core.controller import Controller
from meters.homewizard_p1_meter import HomeWizardP1Meter
from batteries.venus_battery import VenusBattery
from core.mqtt_publisher import MqttPublisher
from telemetry.influx_logger import InfluxLogger
import os
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()

def handle_shutdown(signum, frame):
    print("Shutting down gracefully...")
    controller.shutdown_all()
    sys.exit(0)

if __name__ == "__main__":
    #setup logging
    logger = get_logger('MMBC')
    # Handle shutdown signals
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Get environment variables
    meter_ip = os.getenv("P1_HOST")
    battery_1_ip = os.getenv("BATTERY_1_IP")
    battery_1_address = int(os.getenv("BATTERY_1_ADDRESS"))
    battery_1_port = int(os.getenv("BATTERY_1_PORT", 502))  # Default port is 502 if not set
    if not battery_1_ip or not battery_1_address:
        raise ValueError("BATTERY_1_IP and BATTERY_1_ADDRESS environment variables must be set.")

    battery_2_ip = os.getenv("BATTERY_2_IP")
    battery_2_address = int(os.getenv("BATTERY_2_ADDRESS",0))
    battery_2_port = int(os.getenv("BATTERY_2_PORT", 502))  # Default port is 502 if not set
    battery_2_present = False
    if not battery_2_ip or not battery_2_address:
        logger.info('BATTERY_2_IP and BATTERY_2_ADDRESS environment variables not set. Skipping battery 2.')
    else: 
        logger.info(f'BATTERY_2_IP and BATTERY_2_ADDRESS environment variables set. Battery 2 will be used.')
        battery_2_present = True
    if not meter_ip:
        raise ValueError("P1_HOST environment variable not set. Please set it to your HomeWizard P1 meter's IP address.")
    INFLUX_URL = os.getenv("INFLUX_URL")
    INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
    INFLUX_ORG = os.getenv("INFLUX_ORG")
    INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

    if INFLUX_URL and ( not INFLUX_TOKEN or not INFLUX_ORG or not INFLUX_BUCKET):
        raise ValueError("InfluxDB environment variables (INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET) must be set when INFLUX_URL is set.")

    influx_logger = InfluxLogger(INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET)

    # Initialize HomeWizard P1 Meter and Venus Batteries
    meter = HomeWizardP1Meter(host=meter_ip)
    
    batteries = [
        VenusBattery(ip=battery_1_ip, unit_id=battery_1_address, name="VenusBattery1",port=battery_1_port)
    ]
    if battery_2_present:
        batteries.append(VenusBattery(ip=battery_2_ip, unit_id=battery_2_address, name="VenusBattery2",port=battery_2_port))
    mqtt = MqttPublisher(batteries=batteries, interval=3)
    mqtt.start()
    controller = Controller(meter=meter, batteries=batteries, interval_seconds=3)
    controller.run_forever()
