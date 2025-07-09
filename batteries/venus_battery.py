from pymodbus.client import ModbusTcpClient
from interfaces.battery_interface import BatteryInterface
from utils.logger import get_logger
from datetime import datetime

REG_SOC = 32104
REG_POWER = 32202
REG_CHARGE_SETPOINT = 42020
REG_DISCHARGE_SETPOINT = 42021
REG_SET_FORCED_DISCHARGE = 42010  # 0 stop, 1 charge, 2 discharge
REG_RS484_CONTROL_MODE = 42000
BATTERY_MODBUS_CONTROL = 0x55aa  # Modbus control mode for Venus battery
BATTERY_MODBUS_CONTROL_RELEASE = 0x55bb  # Modbus control release value

class VenusBattery(BatteryInterface):
    def __init__(self, ip: str, unit_id: int = 1, name: str = "Venus", port: int = 502):
        self.ip = ip
        self.unit_id = unit_id
        self.port = port
        self.name = name
        self.client = ModbusTcpClient(host=self.ip, port=self.port)
        self.current_power = 0
        self.connected = False
        self.last_connect_attempt = None
        self.retry_backoff = 1
        self.last_written_values = {}  # register_address -> value
        self.self_control = False  # Flag to indicate if the battery is in self-control mode
        self.logger = get_logger('VenusBattery')
        self._connect()
        self._write_if_changed(REG_RS484_CONTROL_MODE, BATTERY_MODBUS_CONTROL)
        self.last_control_mode_check = datetime.now()
        self.released = False  # Flag to indicate if the battery has released control

    def _connect(self):
        now = datetime.now()
        if not self.client:
            self.client = ModbusTcpClient(host=self.ip, port=self.port)
            self.connected = False
            self.last_connect_attempt = None
            self.retry_backoff = 1

        if self.client.connected:
            return

        if self.last_connect_attempt and (now - self.last_connect_attempt).total_seconds() < self.retry_backoff:
            return

        self.last_connect_attempt = now
        try:
            if self.client.connect():
                self.connected = True
                self.retry_backoff = 1
                self.logger.info(f"[{self.name}] Connected to battery at {self.ip}")
            else:
                self.connected = False
                self.retry_backoff = min(self.retry_backoff * 2, 10)
                self.logger.warning(f"[{self.name}] Connection failed. Backing off for {self.retry_backoff}s")
        except Exception as e:
            self.connected = False
            self.retry_backoff = min(self.retry_backoff * 2, 10)
            self.logger.error(f"[{self.name}] Exception while connecting: {e}")

    def _write_if_changed(self, address: int, value: int) -> None:
        if self.last_written_values.get(address) != value:
            self.client.write_register(address=address, value=value, slave=self.unit_id)
            self.last_written_values[address] = value

    def get_soc(self) -> float:
        if not self.released and (datetime.now() - self.last_control_mode_check).total_seconds() > 60:
            self._check_control_mode()
            self.last_control_mode_check = datetime.now()
        registers = self._safe_read(REG_SOC, count=1)
        if registers is None or len(registers) < 1:
            raise Exception("Failed to read SOC")
        return registers[0]

    def get_current_wattage(self) -> int:
        registers = self._safe_read(REG_POWER, count=2)
        if registers is None or len(registers) < 2:
            return self.current_power
        high, low = registers[0], registers[1]
        raw = (high << 16) | low
        if raw & 0x80000000:
            raw -= 0x100000000
        return raw

    def charge(self, watts: int) -> None:
        self.logger.info(f"[{self.name}] Setting charge to {watts}W")
        self._connect()
        self._write_if_changed(REG_SET_FORCED_DISCHARGE, 1)
        self._write_if_changed(REG_DISCHARGE_SETPOINT, 0)
        self._write_if_changed(REG_CHARGE_SETPOINT, int(watts))
        self.current_power = -watts

    def discharge(self, watts: int) -> None:
        self.logger.info(f"[{self.name}] Setting discharge to {watts}W")
        self._connect()
        self._write_if_changed(REG_SET_FORCED_DISCHARGE, 2)
        self._write_if_changed(REG_CHARGE_SETPOINT, 0)
        self._write_if_changed(REG_DISCHARGE_SETPOINT, int(watts))
        self.current_power = watts

    def idle(self) -> None:
        self.logger.info(f"[{self.name}] Setting idle (0W)")
        self._connect()
        self._write_if_changed(REG_SET_FORCED_DISCHARGE, 0)
        self._write_if_changed(REG_CHARGE_SETPOINT, 0)
        self._write_if_changed(REG_DISCHARGE_SETPOINT, 0)
        self.current_power = 0

    def aquire_control(self) -> None:
        self.logger.info(f"[{self.name}] Aquiring control")
        self.released = False
        self._connect()
        # Ensure control mode is set correctly
        self._check_control_mode()
        self.last_control_mode_check = datetime.now()
    def release(self) -> None:
        self.logger.info(f"[{self.name}] Releasing control")
        self.released = True
        self._connect()
        self._write_if_changed(REG_RS484_CONTROL_MODE, BATTERY_MODBUS_CONTROL_RELEASE)
    def shutdown(self):
        try:
            self._connect()
            self.release()
            self.client.close()
            self.connected = False
            print(f"[{self.name}] RS485 control released.")
        except Exception as e:
            print(f"[{self.name}] Failed to release RS485 control: {e}")

    def _check_control_mode(self):
        try:
            registers = self._safe_read(REG_RS484_CONTROL_MODE, count=1)
            if registers is None or len(registers) < 1:
                self.logger.warning(f"[{self.name}] Could not read control mode (read error).")
                return
            mode = registers[0]
            if mode != BATTERY_MODBUS_CONTROL:
                self.logger.warning(f"[{self.name}] Control mode lost! Reapplying Modbus control...")
                self._write_if_changed(REG_RS484_CONTROL_MODE, BATTERY_MODBUS_CONTROL)
        except Exception as e:
            self.logger.error(f"[{self.name}] Failed to check/reset control mode: {e}")

    def _safe_read(self, address, count=1):
        self._connect()
        if not self.client.connected:
            return None
        try:
            result = self.client.read_holding_registers(address=address, count=count, slave=self.unit_id)
            if result.isError() or not result.registers or len(result.registers) < count:
                self.logger.warning(f"[{self.name}] Failed Modbus read at {address}")
                return None
            return result.registers
        except Exception as e:
            self.logger.error(f"[{self.name}] Exception during read at {address}: {e}")
            return None

    def get_total_charged_kwh(self) -> float:
        registers = self._safe_read(33000, count=2)
        if registers is None or len(registers) < 2:
            self.logger.warning(f"[{self.name}] Failed to read total charged energy")
            return 0.0
        raw = (registers[0] << 16) | registers[1]
        return raw / 100  # Wh to kWh

    def get_total_discharged_kwh(self) -> float:
        registers = self._safe_read(33002, count=2)
        if registers is None or len(registers) < 2:
            self.logger.warning(f"[{self.name}] Failed to read total discharged energy")
            return 0.0
        raw = (registers[0] << 16) | registers[1]
        return raw / 100
