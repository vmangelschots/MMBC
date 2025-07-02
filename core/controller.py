import time
from interfaces.meter_interface import MeterInterface
from interfaces.battery_interface import BatteryInterface
from utils.logger import get_logger

import signal
import sys

BATTERY_NORMAL = 1
BATTERY_HOLD = 2
BATTERY_CHARGE = 3
CHARGING = 1
DISCHARGING = 2

class Controller:
    def __init__(self, meter: MeterInterface, batteries: list[BatteryInterface], interval_seconds: int = 5):
        self.meter = meter
        self.batteries = batteries
        self.interval = interval_seconds
        self.cached_priority_targets = []
        self.last_priority_selection_time = 0
        self.selection_interval = 300  # reevaluate every 5 minutes
        self.CHARGE_MAX_SOC = 100
        self.DISCHARGE_MIN_SOC = 11
        self.CHARGE_LIMIT = 2500
        self.DISCHARGE_LIMIT = 2500
        self.mode = BATTERY_NORMAL  # Flag to block discharge if needed
        self.logger = get_logger('Controller')

    def run_forever(self):
        while True:
            now = time.time()
            net_power = self.meter.get_net_power() # Get the net power from the meter

            #calculate the total battery power and adjust the net power accordingly
            battery_power = sum(b.get_current_wattage() for b in self.batteries) # 
            adjusted_power = net_power + battery_power
            self.logger.info(f"net: {net_power}W | adjusted: {adjusted_power}W")
            
            for b in self.batteries:
                self.logger.info(f" {b.name}: {b.get_soc()}% @ {b.get_current_wattage()}W")

            # if adjusted_power is between -30 and + 30 watt, idle all batteries
            if adjusted_power >= -30 and adjusted_power <= 30:
                self._idle_all()
                time.sleep(self.interval)
                continue

            mode = DISCHARGING if adjusted_power > 0 else CHARGING

            power = abs(adjusted_power)
            if self.mode == BATTERY_NORMAL:
                if mode == CHARGING:
                    self._charge(power)
                else:
                    self._discharge(power)    
            elif self.mode == BATTERY_HOLD:
                if mode == CHARGING:
                    self._charge(power)
                else:
                    self._idle_all()
            #the easiest case: Just charge all batteries
            elif self.mode == BATTERY_CHARGE:
                for b in self.batteries:
                        b.charge(self.CHARGE_LIMIT)
            time.sleep(self.interval)

    def _select_target(self, mode: str) -> BatteryInterface | None:
        candidates = []
        for b in self.batteries:
            soc = b.get_soc()
            if mode == CHARGING and soc < self.CHARGE_MAX_SOC:
                candidates.append((b, soc))
            elif mode == DISCHARGING and soc > self.DISCHARGE_MIN_SOC:
                candidates.append((b, soc))

        if not candidates:
            return None

        return min(candidates, key=lambda x: x[1])[0] if mode == CHARGING else max(candidates, key=lambda x: x[1])[0]

    def _target_invalid(self, mode: str) -> bool:
        if not self.active_target:
            return True
        soc = self.active_target.get_soc()
        return (soc >= self.CHARGE_MAX_SOC if mode == CHARGING else soc <= self.DISCHARGE_MIN_SOC)

    def _idle_others(self, active: list[BatteryInterface]):
        for b in self.batteries:
            if b not in active:
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
    
    def _get_batteries_priority_list(self, mode: int) -> list[BatteryInterface]:
        now = time.time()
        
        if (now - self.last_priority_selection_time < self.selection_interval and
            self.cached_priority_targets and
            all(self._battery_is_eligible(b, mode) for b in self.cached_priority_targets)):
            return self.cached_priority_targets

        eligible = []
        for b in self.batteries:
            if self._battery_is_eligible(b, mode):
                eligible.append((b, b.get_soc()))

        sorted_batteries = sorted(eligible, key=lambda x: x[1], reverse=(mode == DISCHARGING))
        self.cached_priority_targets = [b[0] for b in sorted_batteries]
        self.last_priority_selection_time = now
        return self.cached_priority_targets


    def _charge(self,power: int):
        # get the list of batteries to charge based on priority
        target_batteries = self._get_batteries_priority_list(CHARGING)
        #calculate how many batteries can be charged with the given power
        number_of_batteries_to_charge = min(power//self.CHARGE_LIMIT+1, len(target_batteries))
        if number_of_batteries_to_charge == 0:
            self.logger.debug("No batteries to charge")
            self._idle_all()
            return

        power_per_battery = power // number_of_batteries_to_charge
        if power_per_battery > self.CHARGE_LIMIT:
            power_per_battery = self.CHARGE_LIMIT

        self.logger.debug(f"Charging {number_of_batteries_to_charge} batteries with {power_per_battery}W for a total of {power}W")

        for i in range(number_of_batteries_to_charge):
            battery = target_batteries[i]
            battery.charge(power_per_battery)
        self._idle_others(target_batteries[:number_of_batteries_to_charge])
        
    def _discharge(self,power: int):
        # get the list of batteries to charge based on priority
        target_batteries = self._get_batteries_priority_list(DISCHARGING)
        #calculate how many batteries can be charged with the given power
        number_of_batteries_to_discharge = min(power//self.DISCHARGE_LIMIT+1, len(target_batteries))
        if number_of_batteries_to_discharge == 0:
            self.logger.debug("No batteries to discharge")
            self._idle_all()
            return

        power_per_battery = power // number_of_batteries_to_discharge
        if power_per_battery > self.DISCHARGE_LIMIT:
            power_per_battery = self.DISCHARGE_LIMIT

        self.logger.debug(f"Discharging {number_of_batteries_to_discharge} batteries with {power_per_battery}W for a total of {power}W")

        for i in range(number_of_batteries_to_discharge):
            battery = target_batteries[i]
            battery.discharge(power_per_battery)
        self._idle_others(target_batteries[:number_of_batteries_to_discharge])
    
    def _battery_is_eligible(self, b: BatteryInterface, mode: int) -> bool:
        soc = b.get_soc()
        if mode == CHARGING:
            return soc < self.CHARGE_MAX_SOC
        return soc > self.DISCHARGE_MIN_SOC

