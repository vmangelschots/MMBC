from abc import ABC, abstractmethod

class MeterInterface(ABC):
    @abstractmethod
    def get_net_power(self) -> int:
        """
        Return the current net power at the grid connection point:
        - Positive value → Importing power from the grid
        - Negative value → Exporting power to the grid
        - 0 → Perfect balance
        """
        pass
