import time
from interfaces.meter_interface import MeterInterface
from interfaces.battery_interface import BatteryInterface
from interfaces.optimizer_interface import OptimizerInterface
from utils.logger import get_logger


import signal
import sys

BATTERY_NORMAL = 1
BATTERY_HOLD = 2
BATTERY_CHARGE = 3
BATTERY_SELFCONTROL = 4
BATTERY_EVCC = 5
CHARGING = 1
DISCHARGING = 2

EVCC_CHARGE = "charge"
EVCC_DISCHARGE = "discharge"
EVCC_HOLD = "hold"

class Controller:
    def __init__(self, meter: MeterInterface, batteries: list[BatteryInterface], interval_seconds: int = 5, initial_mode: int = BATTERY_NORMAL, self_control_available: bool = True, grid_max_import: int | None = None, optimizer: OptimizerInterface | None = None):
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
        self.DEADBAND = 30  # ignore grid imbalances smaller than this
        self.grid_max_import = grid_max_import  # capacity tariff cap in watts, None = no limit
        self.self_control_available = self_control_available
        self.optimizer = optimizer
        self.last_evcc_action = None
        # what the controller last told the batteries to do, for reporting over MQTT
        self.last_action = "idle"
        self.last_action_power = 0  # total target power in watts, always positive
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

            flow = DISCHARGING if adjusted_power > 0 else CHARGING
            power = abs(adjusted_power)

            if self.mode == BATTERY_NORMAL:
                self._run_normal(adjusted_power, power, flow)
            elif self.mode == BATTERY_HOLD:
                self._run_hold(adjusted_power, power, flow)
            #the easiest case: Just charge all batteries
            elif self.mode == BATTERY_CHARGE:
                self._charge_all(adjusted_power)
            elif self.mode == BATTERY_EVCC:
                self._run_evcc(adjusted_power, power, flow)
            elif self.mode == BATTERY_SELFCONTROL:
                # do nothing, let the batteries control themselves
                self._record_action("selfcontrol", 0)
            time.sleep(self.interval)

    def _in_deadband(self, adjusted_power: int) -> bool:
        """True when the grid is close enough to zero that acting on it is not worth it."""
        return -self.DEADBAND <= adjusted_power <= self.DEADBAND

    def _run_normal(self, adjusted_power: int, power: int, flow: int, max_discharge: int | None = None):
        """Follow the grid: charge from surplus, discharge to cover consumption."""
        if self._in_deadband(adjusted_power):
            self._idle_all()
            return

        if flow == CHARGING:
            self._charge(self._cap_charge_power(power, adjusted_power))
        else:
            if max_discharge is not None and power > max_discharge:
                self.logger.debug(f"Limiting discharge from {power}W to {max_discharge}W")
                power = max_discharge
            self._discharge(power)

    def _run_hold(self, adjusted_power: int, power: int, flow: int):
        """Charge from surplus, but never discharge."""
        if self._in_deadband(adjusted_power):
            self._idle_all()
            return

        if flow == CHARGING:
            self._charge(self._cap_charge_power(power, adjusted_power))
        else:
            self._idle_all()

    def _run_evcc(self, adjusted_power: int, power: int, flow: int):
        """Follow the suggestion of the EVCC optimizer.

        Falls back to normal self-consumption whenever no usable suggestion is
        available, so an EVCC outage never leaves the batteries stranded.
        """
        suggestion = self.optimizer.get_suggestion() if self.optimizer else None

        if suggestion is None:
            self._log_evcc_action(None)
            self._run_normal(adjusted_power, power, flow)
            return

        self._log_evcc_action(suggestion)

        if not suggestion.actionable:
            self._run_normal(adjusted_power, power, flow)
            return

        if suggestion.action == EVCC_CHARGE and suggestion.charge > 0:
            # Charge at the suggested power, but never below the solar surplus we
            # already have: free energy beats the optimizer's grid charge target.
            surplus = power if flow == CHARGING else 0
            target = max(suggestion.charge, surplus)
            self._charge(self._cap_charge_power(target, adjusted_power))
        elif suggestion.action == EVCC_HOLD:
            # Hold means do not discharge. A solar surplus is still used to charge.
            self._run_hold(adjusted_power, power, flow)
        elif suggestion.action == EVCC_DISCHARGE:
            # Cover the house load, capped at what the optimizer asked for. Never
            # discharge into the grid.
            self._run_normal(adjusted_power, power, flow, max_discharge=suggestion.discharge or None)
        else:
            self._run_normal(adjusted_power, power, flow)

    def _log_evcc_action(self, suggestion):
        """Log the EVCC suggestion once, whenever it changes."""
        action = suggestion.action if suggestion else None
        if action == self.last_evcc_action:
            return
        self.last_evcc_action = action

        if suggestion is None:
            self.logger.warning("No usable EVCC suggestion, falling back to normal mode")
        elif not suggestion.actionable:
            self.logger.info(f"EVCC suggests '{suggestion.action}' but marked it not actionable, falling back to normal mode")
        elif suggestion.action in (EVCC_CHARGE, EVCC_DISCHARGE, EVCC_HOLD):
            self.logger.info(f"EVCC suggests '{suggestion.action}' (charge {suggestion.charge}W, discharge {suggestion.discharge}W)")
        else:
            self.logger.info(f"EVCC suggests '{suggestion.action}', treating it as normal mode")


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
        self._record_action("idle", 0)
        for b in self.batteries:
            b.idle()

    def _record_action(self, action: str, power: int):
        """Remember the last decision so it can be published over MQTT."""
        self.last_action = action
        self.last_action_power = power
    @property
    def evcc_available(self) -> bool:
        return self.optimizer is not None

    def set_battery_mode(self, mode: int = BATTERY_NORMAL):
        if mode == BATTERY_EVCC and not self.evcc_available:
            self.logger.warning("EVCC mode requested but no EVCC optimizer is configured. Falling back to Normal.")
            mode = BATTERY_NORMAL

        if mode == BATTERY_EVCC:
            self.last_evcc_action = None  # log the first suggestion after every switch

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

        self._record_action("charge", power_per_battery * len(self.batteries))
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

        self._record_action("charge", power_per_battery * number_of_batteries_to_charge)
        for i in range(number_of_batteries_to_charge):
            battery = target_batteries[i]
            battery.charge(power_per_battery)
        self._idle_others(target_batteries[:number_of_batteries_to_charge])
        
    def _discharge(self,power: int):
        if power <= 0:
            self.logger.debug("No discharge power requested")
            self._idle_all()
            return
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

        self._record_action("discharge", power_per_battery * number_of_batteries_to_discharge)
        for i in range(number_of_batteries_to_discharge):
            battery = target_batteries[i]
            battery.discharge(power_per_battery)
        self._idle_others(target_batteries[:number_of_batteries_to_discharge])
    
    def _battery_is_eligible(self, b: BatteryInterface, mode: int) -> bool:
        soc = b.get_soc()
        if mode == CHARGING:
            return soc < self.CHARGE_MAX_SOC
        return soc > self.DISCHARGE_MIN_SOC

