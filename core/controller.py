import time
from interfaces.meter_interface import MeterInterface
from interfaces.battery_interface import BatteryInterface
from utils.logger import get_logger

import signal
import sys

BATTERY_NORMAL = 1
BATTERY_HOLD = 2
BATTERY_CHARGE = 3

class Controller:
    def __init__(self, meter: MeterInterface, batteries: list[BatteryInterface], interval_seconds: int = 5):
        self.meter = meter
        self.batteries = batteries
        self.interval = interval_seconds
        self.active_target = None
        self.last_selection_time = 0
        self.selection_interval = 300  # reevaluate every 5 minutes
        self.CHARGE_MAX_SOC = 100
        self.DISCHARGE_MIN_SOC = 11
        self.CHARGE_LIMIT = 2500
        self.DISCHARGE_LIMIT = 2500
        self.mode = BATTERY_NORMAL  # Flag to block discharge if needed
        self.logger = get_logger('Controller')

    def run_forever(self):
        while True:
            net_power = self.meter.get_net_power()
            battery_offset = sum(b.get_current_wattage() for b in self.batteries)
            adjusted_power = net_power + battery_offset
            now = time.time()

            self.logger.info(f"net: {net_power}W | adjusted: {adjusted_power}W")
            for b in self.batteries:
                self.logger.info(f" {b.name}: {b.get_soc()}% @ {b.get_current_wattage()}W")

            if adjusted_power == 0:
                self._idle_all()
                time.sleep(self.interval)
                continue

            mode = "discharge" if adjusted_power > 0 else "charge"
            power = abs(adjusted_power)
            if self.mode == BATTERY_NORMAL:
                if power <= max(self.CHARGE_LIMIT, self.DISCHARGE_LIMIT):
                    if (self.active_target is None or
                        self._target_invalid(mode) or
                        now - self.last_selection_time > self.selection_interval):
                        self.active_target = self._select_target(mode)
                        self.last_selection_time = now

                    if self.active_target:
                        if mode == "charge":
                            self.active_target.charge(power)
                        else:
                            self.active_target.discharge(power)
                        self._idle_others(self.active_target)
                    else:
                        self._idle_all()

                else:
                    split = min(power / len(self.batteries), self.CHARGE_LIMIT if mode == "charge" else self.DISCHARGE_LIMIT)
                    for b in self.batteries:
                        soc = b.get_soc()
                        if mode == "charge" and soc < self.CHARGE_MAX_SOC:
                            b.charge(split)
                        elif mode == "discharge" and soc > self.DISCHARGE_MIN_SOC:
                            b.discharge(split)
                        else:
                            b.idle()
            elif self.mode == BATTERY_HOLD:
                if power <= max(self.CHARGE_LIMIT, self.DISCHARGE_LIMIT):
                    if (self.active_target is None or
                        self._target_invalid(mode) or
                        now - self.last_selection_time > self.selection_interval):
                        self.active_target = self._select_target(mode)
                        self.last_selection_time = now

                    if self.active_target:
                        if mode == "charge":
                            self.active_target.charge(power)
                            self._idle_others(self.active_target)
                        else:
                            self._idle_all()
                        
                    else:
                        self._idle_all()

                else:
                    split = min(power / len(self.batteries), self.CHARGE_LIMIT if mode == "charge" else self.DISCHARGE_LIMIT)
                    for b in self.batteries:
                        soc = b.get_soc()
                        if mode == "charge" and soc < self.CHARGE_MAX_SOC:
                            b.charge(split)
                        elif mode == "discharge" and soc > self.DISCHARGE_MIN_SOC:
                            b.discharge(split)
                        else:
                            b.idle()
            elif self.mode == BATTERY_CHARGE:
                for b in self.batteries:
                        b.charge(self.CHARGE_LIMIT)
            time.sleep(self.interval)

    def _select_target(self, mode: str) -> BatteryInterface | None:
        candidates = []
        for b in self.batteries:
            soc = b.get_soc()
            if mode == "charge" and soc < self.CHARGE_MAX_SOC:
                candidates.append((b, soc))
            elif mode == "discharge" and soc > self.DISCHARGE_MIN_SOC:
                candidates.append((b, soc))

        if not candidates:
            return None

        return min(candidates, key=lambda x: x[1])[0] if mode == "charge" else max(candidates, key=lambda x: x[1])[0]

    def _target_invalid(self, mode: str) -> bool:
        if not self.active_target:
            return True
        soc = self.active_target.get_soc()
        return (soc >= self.CHARGE_MAX_SOC if mode == "charge" else soc <= self.DISCHARGE_MIN_SOC)

    def _idle_others(self, active: BatteryInterface):
        for b in self.batteries:
            if b != active:
                b.idle()

    def _idle_all(self):
        for b in self.batteries:
            b.idle()
    def set_battery_mode(self,mode: int = BATTERY_NORMAL ):
        """Block or unblock discharge for all batteries."""
        self.mode = mode
    def shutdown_all(self):
        for b in self.batteries:
            if hasattr(b, "shutdown"):
                b.shutdown()

