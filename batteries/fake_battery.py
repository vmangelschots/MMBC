import time
from interfaces.battery_interface import BatteryInterface

class FakeBattery(BatteryInterface):
    def __init__(self, name: str, initial_soc: float = 50.0, capacity_wh: float = 5120):
        self.name = name
        self.soc = initial_soc
        self.capacity_wh = capacity_wh
        self.current_power = 0  # +W = discharge, -W = charge
        self._last_update_time = time.time()

    def _update_soc(self):
        now = time.time()
        dt = now - self._last_update_time
        self._last_update_time = now

        if self.current_power == 0:
            return

        wh = (abs(self.current_power) * dt) / 3600
        soc_delta = (wh / self.capacity_wh) * 100

        if self.current_power > 0:
            self.soc = max(0, self.soc - soc_delta)
        else:
            self.soc = min(100, self.soc + soc_delta)

    def get_soc(self) -> float:
        self._update_soc()
        return round(self.soc, 2)

    def get_current_wattage(self) -> int:
        return self.current_power

    def charge(self, watts: int) -> None:
        self._update_soc()
        self.current_power = -abs(watts)

    def discharge(self, watts: int) -> None:
        self._update_soc()
        self.current_power = abs(watts)

    def idle(self) -> None:
        self._update_soc()
        self.current_power = 0
