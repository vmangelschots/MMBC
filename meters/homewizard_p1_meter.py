import requests
from interfaces.meter_interface import MeterInterface
from utils.logger import get_logger

class HomeWizardP1Meter(MeterInterface):
    def __init__(self, host: str):
        self.url = f"{host}/api/v1/data"
        self.last_known_power = 0
        self.logger = get_logger('P1Meter')

    def get_net_power(self) -> int:
        try:
            response = requests.get(self.url, timeout=2)
            response.raise_for_status()
            data = response.json()

            if "active_power_w" in data:
                self.last_known_power = int(data["active_power_w"])
                return self.last_known_power

            raise ValueError("No usable power field found in P1 data")
        except Exception as e:
            self.logger.warning(f"Error reading data: {e}. Using last known value: {self.last_known_power}W")
            return self.last_known_power
