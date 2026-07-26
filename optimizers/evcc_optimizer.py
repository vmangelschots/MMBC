import time
import requests
from interfaces.optimizer_interface import OptimizerInterface, Suggestion
from utils.logger import get_logger

ACTION_CHARGE = "charge"
ACTION_DISCHARGE = "discharge"
ACTION_HOLD = "hold"
ACTION_NORMAL = "normal"


class EvccOptimizer(OptimizerInterface):
    """Reads battery suggestions from EVCC's experimental optimizer.

    EVCC exposes its state at `<host>/api/state`. Every controllable battery under
    `battery.devices` carries a `suggestion` object, for example:

        {"action": "hold", "charge": 0, "discharge": 0, "actionable": true}

    The optimizer recalculates on 15 minute slots, so the state is polled at most
    once every `poll_interval` seconds and reused in between.
    """

    def __init__(self, host: str, battery_name: str | None = None, poll_interval: int = 30,
                 timeout: int = 3, max_age: int = 600):
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"
        self.url = f"{host.rstrip('/')}/api/state"
        self.battery_name = battery_name
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.max_age = max_age  # drop the cached suggestion once it is this old
        self.logger = get_logger('EvccOptimizer')
        self.last_poll_time = 0.0
        self.last_success_time = 0.0
        self.last_suggestion: Suggestion | None = None
        self.resolved_battery = None  # name of the device the suggestion came from

    def get_suggestion(self) -> Suggestion | None:
        now = time.time()
        if now - self.last_poll_time >= self.poll_interval:
            self.last_poll_time = now
            suggestion = self._poll()
            if suggestion is not None:
                self.last_suggestion = suggestion
                self.last_success_time = now

        if self.last_suggestion is None:
            return None

        age = now - self.last_success_time
        if age > self.max_age:
            self.logger.warning(f"Last EVCC suggestion is {int(age)}s old, discarding it")
            self.last_suggestion = None
            return None

        return self.last_suggestion

    def _poll(self) -> Suggestion | None:
        try:
            response = requests.get(self.url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            self.logger.warning(f"Failed to read EVCC state from {self.url}: {e}")
            return None

        device = self._find_battery(data)
        if device is None:
            return None

        raw = device.get("suggestion")
        if not isinstance(raw, dict):
            self.logger.warning(f"EVCC battery '{self.resolved_battery}' has no suggestion. Is the experimental optimizer enabled?")
            return None

        action = str(raw.get("action", "")).strip().lower()
        if not action:
            self.logger.warning(f"EVCC suggestion for '{self.resolved_battery}' has no action: {raw}")
            return None

        return Suggestion(
            action=action,
            charge=self._to_watts(raw.get("charge")),
            discharge=self._to_watts(raw.get("discharge")),
            actionable=bool(raw.get("actionable", True)),
        )

    def _find_battery(self, data: dict):
        devices = data.get("battery", {}).get("devices", [])
        if not devices:
            self.logger.warning("EVCC state contains no battery devices")
            return None

        if self.battery_name:
            wanted = self.battery_name.strip().lower()
            for device in devices:
                if wanted in (str(device.get("name", "")).lower(), str(device.get("title", "")).lower()):
                    self.resolved_battery = device.get("name") or device.get("title")
                    return device
            known = ", ".join(f"{d.get('name')} ({d.get('title')})" for d in devices)
            self.logger.warning(f"EVCC battery '{self.battery_name}' not found. Available: {known}")
            return None

        # No name configured: take the first controllable battery.
        for device in devices:
            if device.get("controllable"):
                name = device.get("name") or device.get("title")
                if name != self.resolved_battery:
                    self.logger.info(f"Using EVCC battery '{device.get('title')}' ({device.get('name')})")
                    self.resolved_battery = name
                return device

        self.logger.warning("EVCC has no controllable battery device")
        return None

    @staticmethod
    def _to_watts(value) -> int:
        try:
            return max(0, int(round(float(value))))
        except (TypeError, ValueError):
            return 0
