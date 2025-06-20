from pymodbus.client import ModbusTcpClient
from interfaces.battery_interface import BatteryInterface

REG_SOC = 32104
REG_POWER = 32202
REG_CHARGE_SETPOINT = 42020
REG_DISCHARGE_SETPOINT = 42021
REG_SET_FORCED_DISCHARGE = 42010 # 0 stop, 1 charge, 2 discharge
REG_RS484_CONTROL_MODE = 42000

class VenusBattery(BatteryInterface):
    def __init__(self, ip: str, unit_id: int = 1, name: str = "Venus"):
        self.ip = ip
        self.unit_id = unit_id
        self.name = name
        self.client = ModbusTcpClient(host=self.ip, port=502)
        self.current_power = 0  # track last commanded power
        self._connect()
        self.client.write_register(address=REG_RS484_CONTROL_MODE, value=0x55aa, slave=self.unit_id)
    def _connect(self):
        if not self.client.connect():
            raise ConnectionError(f"Could not connect to battery at {self.ip}")

    def get_soc(self) -> float:
        self._connect()
        result = self.client.read_holding_registers(address=REG_SOC, count=1, slave=self.unit_id)
        if result.isError():
            raise Exception("Failed to read SOC")
        return result.registers[0] 

    def get_current_wattage(self) -> int:
        self._connect()
        result = self.client.read_holding_registers(address=REG_POWER, count=2, slave=self.unit_id)
        if result.isError():
            raise Exception("Failed to read power")
        return result.registers[1]

    def charge(self, watts: int) -> None:
        print(f"[VenusBattery] Setting charge to {watts}W")
        self._connect()
        self.client.write_register(address=REG_SET_FORCED_DISCHARGE, value=1, slave=self.unit_id)
        self.client.write_register(address=REG_DISCHARGE_SETPOINT, value=0, slave=self.unit_id)
        self.client.write_register(address=REG_CHARGE_SETPOINT, value=int(watts), slave=self.unit_id)
        self.current_power = -watts

    def discharge(self, watts: int) -> None:
        print(f"[VenusBattery] Setting discharge to {watts}W")
        self._connect()
        self.client.write_register(address=REG_SET_FORCED_DISCHARGE, value=2, slave=self.unit_id)
        self.client.write_register(address=REG_CHARGE_SETPOINT, value=0, slave=self.unit_id)
        self.client.write_register(address=REG_DISCHARGE_SETPOINT, value=int(watts), slave=self.unit_id)
        self.current_power = watts

    def idle(self) -> None:
        print("[VenusBattery] Setting idle (0W)")
        self._connect()
        self.client.write_register(address=REG_SET_FORCED_DISCHARGE, value=0, slave=self.unit_id)
        self.client.write_register(address=REG_CHARGE_SETPOINT, value=0, slave=self.unit_id)
        self.client.write_register(address=REG_DISCHARGE_SETPOINT, value=0, slave=self.unit_id)
        self.current_power = 0
