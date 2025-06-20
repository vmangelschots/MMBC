import random
from interfaces.meter_interface import MeterInterface

class FakeP1Meter(MeterInterface):
    def __init__(self, start_power: int = 0, jump_chance: float = 0.05):
        """
        start_power: initial net power in watts
        jump_chance: probability (0.0 - 1.0) of a jump event per call
        """
        self.power = start_power  # current net power
        self.jump_chance = jump_chance

    def get_net_power(self) -> int:
        # Gradual drift: small random variation
        self.power += random.randint(-100, 100)

        # Occasional jump: simulate device switching on/off
        if random.random() < self.jump_chance:
            self.power += random.choice([-2000, -1500, -1000, 1000, 1500, 2000])

        # Clamp to realistic grid range
        self.power = max(-5000, min(5000, self.power))

        return int(self.power)
