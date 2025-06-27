from abc import ABC, abstractmethod

class BatteryInterface(ABC):
    @abstractmethod
    def get_soc(self) -> float:
        """Return the state of charge as a percentage (0.0 to 100.0)."""
        pass

    @abstractmethod
    def get_current_wattage(self) -> int:
        """Return current power flow in watts: positive for discharge, negative for charge, zero for idle."""
        pass

    @abstractmethod
    def charge(self, watts: int) -> None:
        """Set the battery to charge at a given wattage."""
        pass

    @abstractmethod
    def discharge(self, watts: int) -> None:
        """Set the battery to discharge at a given wattage."""
        pass

    @abstractmethod
    def idle(self) -> None:
        """Stop charging or discharging."""
        pass

    @abstractmethod
    def get_total_charged_kwh(self) -> float:
        """Return the total energy charged in kWh."""
        pass

    @abstractmethod
    def get_total_discharged_kwh(self) -> float:
        """Return the total energy discharged in kWh."""
        pass