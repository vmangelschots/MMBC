import signal
import sys
from core.controller import Controller
from meters.homewizard_p1_meter import HomeWizardP1Meter
from batteries.venus_battery import VenusBattery
from optimizers.evcc_optimizer import EvccOptimizer
from core.mqtt_publisher import MqttPublisher
import os
from dotenv import load_dotenv
from utils.logger import get_logger
from core.config_loader import get_config_value

load_dotenv()

def handle_shutdown(signum, frame):
    print("Shutting down gracefully...")
    controller.shutdown_all()
    sys.exit(0)

if __name__ == "__main__":
    logger = get_logger('MMBC')
    logger.info("Starting MMBC (Multi Meter Battery Controller) Version 1.1.2...")
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    # Real HomeWizard P1 meter
    meter_ip = get_config_value("P1_HOST")
    battery_1_ip = get_config_value("BATTERY_1_IP")
    battery_1_address = int(get_config_value("BATTERY_1_ADDRESS"))
    battery_1_port = int(get_config_value("BATTERY_1_PORT", 502))  # Default port is 502 if not set
    if not battery_1_ip or not battery_1_address:
        raise ValueError("BATTERY_1_IP and BATTERY_1_ADDRESS environment variables must be set.")

    battery_2_ip = get_config_value("BATTERY_2_IP")
    battery_2_address = int(get_config_value("BATTERY_2_ADDRESS",0))
    battery_2_port = int(get_config_value("BATTERY_2_PORT", 502))  # Default port is 502 if not set
    battery_2_present = False
    if not battery_2_ip or not battery_2_address:
        logger.info('BATTERY_2_IP and BATTERY_2_ADDRESS environment variables not set. Skipping battery 2.')
    else: 
        logger.info(f'BATTERY_2_IP and BATTERY_2_ADDRESS environment variables set. Battery 2 will be used.')
        battery_2_present = True
    battery_3_ip = get_config_value("BATTERY_3_IP")
    battery_3_address = int(get_config_value("BATTERY_3_ADDRESS",0))
    battery_3_port = int(get_config_value("BATTERY_3_PORT", 502))  # Default port is 502 if not set
    battery_3_present = False
    if not battery_3_ip or not battery_3_address:
        logger.info('BATTERY_3_IP and BATTERY_3_ADDRESS environment variables not set. Skipping battery 3.')
    else: 
        logger.info(f'BATTERY_3_IP and BATTERY_3_ADDRESS environment variables set. Battery 3 will be used.')
        battery_3_present = True
    if not meter_ip:
        logger.info('P1_HOST environment variable not set. Not using HomeWizard P1 meter.')
        #raise ValueError("P1_HOST environment variable not set. Please set it to your HomeWizard P1 meter's IP address.")
        meter = None
    else:
        meter = HomeWizardP1Meter(host=meter_ip)
    
    batteries = [
        VenusBattery(ip=battery_1_ip, unit_id=battery_1_address, name="VenusBattery1",port=battery_1_port)
    ]
    if battery_2_present:
        batteries.append(VenusBattery(ip=battery_2_ip, unit_id=battery_2_address, name="VenusBattery2",port=battery_2_port))
    if battery_3_present:
        batteries.append(VenusBattery(ip=battery_3_ip, unit_id=battery_3_address, name="VenusBattery3",port=battery_3_port))
   
    self_control_available = get_config_value("SELF_CONTROL_AVAILABLE", "true").lower() == "true"

    # Optional capacity tariff cap: never import more than this many watts from the grid.
    # Not set (or empty) means no limit.
    grid_max_import = get_config_value("GRID_MAX_IMPORT_WATTS")
    if grid_max_import is None or str(grid_max_import).strip() == "":
        grid_max_import = None
        logger.info("GRID_MAX_IMPORT_WATTS not set. Charging is not limited by grid import.")
    else:
        try:
            grid_max_import = int(grid_max_import)
        except (TypeError, ValueError):
            logger.error(f"GRID_MAX_IMPORT_WATTS is not a number: {grid_max_import!r}. Ignoring it, charging will not be limited.")
            grid_max_import = None
        else:
            if grid_max_import <= 0:
                logger.error(f"GRID_MAX_IMPORT_WATTS must be a positive number of watts, got {grid_max_import}. Ignoring it, charging will not be limited.")
                grid_max_import = None
            else:
                logger.info(f"Grid import limited to {grid_max_import}W. Charging will be throttled to stay below it.")

    # Optional EVCC optimizer: enables the Evcc battery mode, which follows the
    # suggestions of EVCC's experimental optimizer. Not set = mode unavailable.
    evcc_host = get_config_value("EVCC_HOST")
    optimizer = None
    if evcc_host:
        evcc_battery = get_config_value("EVCC_BATTERY_NAME") or None
        evcc_poll_interval = int(get_config_value("EVCC_POLL_SECONDS", 30))
        optimizer = EvccOptimizer(host=evcc_host, battery_name=evcc_battery, poll_interval=evcc_poll_interval)
        logger.info(f"EVCC optimizer enabled at {evcc_host} (battery: {evcc_battery or 'first controllable'}, polled every {evcc_poll_interval}s).")
    else:
        logger.info("EVCC_HOST not set. Evcc mode is not available.")

    controller = Controller(meter=meter, batteries=batteries, interval_seconds=3, self_control_available=self_control_available, grid_max_import=grid_max_import, optimizer=optimizer)
    mqtt = MqttPublisher(controller,batteries=batteries, interval=3)
    mqtt.start()
    controller.run_forever()
