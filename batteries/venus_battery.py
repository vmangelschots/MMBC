from pymodbus.client import ModbusTcpClient
from interfaces.battery_interface import BatteryInterface
from utils.logger import get_logger
from datetime import datetime

REG_SOC = 32104
REG_POWER = 32202
REG_CHARGE_SETPOINT = 42020
REG_DISCHARGE_SETPOINT = 42021
REG_SET_FORCED_DISCHARGE = 42010 # 0 stop, 1 charge, 2 discharge
REG_RS484_CONTROL_MODE = 42000
BATTERY_MODBUS_CONTROL = 0x55aa  # Modbus control mode for Venus battery
BATTERY_MODBUS_CONTROLL_RELEASE = 0x55bb  # Modbus control release value
class VenusBattery(BatteryInterface):
    def __init__(self, ip: str, unit_id: int = 1, name: str = "Venus"):
        self.ip = ip
        self.unit_id = unit_id
        self.name = name
        self.client = ModbusTcpClient(host=self.ip, port=502)
        self.current_power = 0  # track last commanded power
        self.logger = get_logger('VenusBattery')
        self._connect()
        self.client.write_register(address=REG_RS484_CONTROL_MODE, value=BATTERY_MODBUS_CONTROL, slave=self.unit_id)
        self.last_control_mode_check =  datetime.now() # timestamp for last control mode check
    
    def _connect(self):
        if not self.client:
            self.client = ModbusTcpClient(host=self.ip, port=502)
        if not self.client.connected:
            if not self.client.connect():
                raise ConnectionError(f"Could not connect to battery at {self.ip}")
            self.logger.info(f"[{self.name}] Connected to battery at {self.ip}")

    def get_soc(self) -> float:
        if (datetime.now() - self.last_control_mode_check).total_seconds() > 60:
            self._check_control_mode()
            self.last_control_mode_check = datetime.now()
        self._connect()
        result = self.client.read_holding_registers(address=REG_SOC, count=1, slave=self.unit_id)
        if result.isError():
            raise Exception("Failed to read SOC")
        return result.registers[0] 

    def get_current_wattage(self) -> int:
        self._connect()
        result = self.client.read_holding_registers(address=REG_POWER, count=2, slave=self.unit_id)

        if result.isError() or not result.registers or len(result.registers) < 2:
            self.logger.warning(f"[{self.name}] Failed to read power or incomplete response: {result}")
            return self.current_power  # fallback to last known
        high, low = result.registers[0], result.registers[1]
        raw = (high << 16) | low
        if raw & 0x80000000:
            raw -= 0x100000000  # interpret as signed

        #self.current_power = raw
        return raw

    def charge(self, watts: int) -> None:
        self.logger.info(f"[{self.name}] Setting charge to {watts}W")
        self._connect()
        self.client.write_register(address=REG_SET_FORCED_DISCHARGE, value=1, slave=self.unit_id)
        self.client.write_register(address=REG_DISCHARGE_SETPOINT, value=0, slave=self.unit_id)
        self.client.write_register(address=REG_CHARGE_SETPOINT, value=int(watts), slave=self.unit_id)
        self.current_power = -watts

    def discharge(self, watts: int) -> None:
        self.logger.info(f"[{self.name}] Setting discharge to {watts}W")
        self._connect()
        self.client.write_register(address=REG_SET_FORCED_DISCHARGE, value=2, slave=self.unit_id)
        self.client.write_register(address=REG_CHARGE_SETPOINT, value=0, slave=self.unit_id)
        self.client.write_register(address=REG_DISCHARGE_SETPOINT, value=int(watts), slave=self.unit_id)
        self.current_power = watts

    def idle(self) -> None:
        self.logger.info(f"[{self.name}] Setting idle (0W)")
        self._connect()
        self.client.write_register(address=REG_SET_FORCED_DISCHARGE, value=0, slave=self.unit_id)
        self.client.write_register(address=REG_CHARGE_SETPOINT, value=0, slave=self.unit_id)
        self.client.write_register(address=REG_DISCHARGE_SETPOINT, value=0, slave=self.unit_id)
        self.current_power = 0
    def shutdown(self):
        try:
            self._connect()
            self.client.write_register(address=REG_RS484_CONTROL_MODE, value=BATTERY_MODBUS_CONTROLL_RELEASE, slave=self.unit_id)
            self.client.close()
            print(f"[{self.name}] RS485 control released.")
        except Exception as e:
            print(f"[{self.name}] Failed to release RS485 control: {e}")

    def _check_control_mode(self):
        try:
            self._connect()
            result = self.client.read_holding_registers(address=REG_RS484_CONTROL_MODE, count=1, slave=self.unit_id)
            if result is None or result.isError() or not result.registers:
                self.logger.warning(f"[{self.name}] Could not verify control mode (read error).")
                return

            mode = result.registers[0]
            if mode != BATTERY_MODBUS_CONTROL:
                self.logger.warning(f"[{self.name}] Control mode lost! Reapplying Modbus control...")
                self.client.write_register(address=REG_RS484_CONTROL_MODE, value=BATTERY_MODBUS_CONTROL, slave=self.unit_id)

        except Exception as e:
            self.logger.error(f"[{self.name}] Failed to check/reset control mode: {e}")