import signal
import sys
from core.controller import Controller
from meters.homewizard_p1_meter import HomeWizardP1Meter
from batteries.venus_battery import VenusBattery
from core.mqtt_publisher import MqttPublisher
import os
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()

def handle_shutdown(signum, frame):
    print("Shutting down gracefully...")
    controller.shutdown_all()
    sys.exit(0)

if __name__ == "__main__":
    logger = get_logger('MMBC')
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    # Real HomeWizard P1 meter
    meter_ip = os.getenv("P1_HOST")
    battery_1_ip = os.getenv("BATTERY_1_IP")
    battery_1_address = int(os.getenv("BATTERY_1_ADDRESS"))
    if not battery_1_ip or not battery_1_address:
        raise ValueError("BATTERY_1_IP and BATTERY_1_ADDRESS environment variables must be set.")

    battery_2_ip = os.getenv("BATTERY_2_IP")
    battery_2_address = int(os.getenv("BATTERY_2_ADDRESS",0))
    battery_2_present = False
    if not battery_2_ip or not battery_2_address:
        logger.info('BATTERY_2_IP and BATTERY_2_ADDRESS environment variables not set. Skipping battery 2.')
    else: 
        logger.info(f'BATTERY_2_IP and BATTERY_2_ADDRESS environment variables set. Battery 2 will be used.')
        battery_2_present = True
    if not meter_ip:
        raise ValueError("P1_HOST environment variable not set. Please set it to your HomeWizard P1 meter's IP address.")

    meter = HomeWizardP1Meter(host=meter_ip)
    
    batteries = [
        VenusBattery(ip=battery_1_ip, unit_id=battery_1_address, name="VenusBattery1")
    ]
    if battery_2_present:
        batteries.append(VenusBattery(ip=battery_2_ip, unit_id=battery_2_address, name="VenusBattery2"))
    mqtt = MqttPublisher(batteries=batteries, interval=3)
    mqtt.start()
    controller = Controller(meter=meter, batteries=batteries, interval_seconds=3)
    controller.run_forever()
