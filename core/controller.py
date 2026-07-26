import time
from interfaces.meter_interface import MeterInterface
from interfaces.battery_interface import BatteryInterface
from utils.logger import get_logger


import signal
import sys

BATTERY_NORMAL = 1
BATTERY_HOLD = 2
BATTERY_CHARGE = 3
BATTERY_SELFCONTROL = 4
CHARGING = 1
DISCHARGING = 2

class Controller:
    def __init__(self, meter: MeterInterface, batteries: list[BatteryInterface], interval_seconds: int = 5, initial_mode: int = BATTERY_NORMAL, self_control_available: bool = True, grid_max_import: int | None = None):
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
        self.grid_max_import = grid_max_import  # capacity tariff cap in watts, None = no limit
        self.self_control_available = self_control_available
        self.mode = initial_mode
        self.logger = get_logger('Controller')
        if self.grid_max_import is not None:
            if self.meter:
                self.logger.info(f"Grid import limit active: charging is capped to keep grid import below {self.grid_max_import}W")
            else:
                self.logger.warning(f"Grid import limit set to {self.grid_max_import}W but no meter is configured. House consumption is unknown, so total charge power is capped at the limit itself.")
        self.set_battery_mode(initial_mode)

    def run_forever(self):
        while True:
            now = time.time()
            if self.meter:
                net_power = self.meter.get_net_power() # Get the net power from the meter
            else:
                net_power = 0

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
                    self._charge(self._cap_charge_power(power, adjusted_power))
                else:
                    self._discharge(power)
            elif self.mode == BATTERY_HOLD:

                if mode == CHARGING:
                    self._charge(self._cap_charge_power(power, adjusted_power))
                else:
                    self._idle_all()
            #the easiest case: Just charge all batteries

            elif self.mode == BATTERY_CHARGE:
                self._charge_all(adjusted_power)
            elif self.mode == BATTERY_SELFCONTROL:
                pass # do nothing, let the batteries control themselves
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

 

    def _idle_others(self, active: list[BatteryInterface]):
        for b in self.batteries:
            if b not in active:
                b.idle()

    def _idle_all(self):
        for b in self.batteries:
            b.idle()
    def set_battery_mode(self, mode: int = BATTERY_NORMAL):
        if mode == BATTERY_SELFCONTROL:
            if not self.self_control_available:
                self.logger.warning("Self-control mode requested but not available. Falling back to Normal.")
                mode = BATTERY_NORMAL
            else:
                for b in self.batteries:
                    b.release()
                self.logger.info("Self-control mode enabled. All batteries will control themselves.")
        else:
            for b in self.batteries:
                b.aquire_control()
            self.logger.info(f"Battery mode set to {mode}. All batteries will follow this mode.")
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


    def _charge_headroom(self, house_power: int) -> int | None:
        """Total charge power (W) still allowed under the grid import limit.

        house_power is the household consumption without the batteries
        (positive = importing from the grid). Returns None when no limit is configured.
        """
        if self.grid_max_import is None:
            return None
        if not self.meter:
            # Without a meter the house consumption is unknown, so the limit itself
            # is the only cap we can apply.
            return self.grid_max_import
        return max(0, self.grid_max_import - house_power)

    def _cap_charge_power(self, power: int, house_power: int) -> int:
        """Reduce a requested charge power so the grid import stays under the limit."""
        headroom = self._charge_headroom(house_power)
        if headroom is None or power <= headroom:
            return power
        self.logger.info(f"Grid import limit {self.grid_max_import}W: house is using {house_power}W, capping charge from {power}W to {headroom}W")
        return headroom

    def _charge_all(self, house_power: int):
        """Charge every battery at full power, limited by the grid headroom if configured."""
        headroom = self._charge_headroom(house_power)
        if headroom is None:
            power_per_battery = self.CHARGE_LIMIT
        else:
            power_per_battery = min(self.CHARGE_LIMIT, headroom // len(self.batteries))

        if power_per_battery <= 0:
            self.logger.info(f"Grid import limit {self.grid_max_import}W reached: house is using {house_power}W, idling all batteries")
            self._idle_all()
            return

        if headroom is not None and power_per_battery < self.CHARGE_LIMIT:
            self.logger.info(f"Grid import limit {self.grid_max_import}W: house is using {house_power}W, charging {len(self.batteries)} batteries at {power_per_battery}W each")

        for b in self.batteries:
            b.charge(power_per_battery)

    def _charge(self,power: int):
        if power <= 0:
            self.logger.debug("No charge power available")
            self._idle_all()
            return
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

