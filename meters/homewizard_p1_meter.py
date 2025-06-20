import requests
from interfaces.meter_interface import MeterInterface

class HomeWizardP1Meter(MeterInterface):
    def __init__(self, host: str = "http://172.21.2.226"):
        self.url = f"{host}/api/v1/data"

    def get_net_power(self) -> int:
        try:
            response = requests.get(self.url, timeout=2)
            response.raise_for_status()
            data = response.json()

            # Use active_power if available (in watts)
            if "active_power_w" in data:
                return int(data["active_power_w"])

            raise ValueError("No usable power field found in P1 data")
        except Exception as e:
            print(f"[P1Meter] Error reading data: {e}")
            return 0  # fallback to "do nothing"
