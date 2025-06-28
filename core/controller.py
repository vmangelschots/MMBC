import time
from interfaces.meter_interface import MeterInterface
from interfaces.battery_interface import BatteryInterface
from utils.logger import get_logger
from telemetry.influx_logger import InfluxLogger

import signal
import sys

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
            # Log battery stats to InfluxDB if configured
            influx_logger = InfluxLogger.get_logger()
            for b in self.batteries:
                influx_logger.log_battery_stats(
                    battery_id=b.name,
                    power_out=b.get_current_wattage(),
                    soc=b.get_soc())
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
    def shutdown_all(self):
        for b in self.batteries:
            if hasattr(b, "shutdown"):
                b.shutdown()

