from abc import ABC, abstractmethod


class Suggestion:
    """A battery action suggested by an external optimizer.

    action    — one of "charge", "discharge", "hold" or "normal"
    charge    — suggested charge power in watts (0 when not applicable)
    discharge — suggested discharge power in watts (0 when not applicable)
    actionable — False when the optimizer says the suggestion should not be acted on
    """

    def __init__(self, action: str, charge: int = 0, discharge: int = 0, actionable: bool = True):
        self.action = action
        self.charge = charge
        self.discharge = discharge
        self.actionable = actionable

    def __repr__(self) -> str:
        return f"Suggestion(action={self.action!r}, charge={self.charge}W, discharge={self.discharge}W, actionable={self.actionable})"


class OptimizerInterface(ABC):
    @abstractmethod
    def get_suggestion(self) -> Suggestion | None:
        """
        Return the current suggestion for the battery, or None when no usable
        suggestion is available (optimizer unreachable, battery unknown, stale data).
        Implementations are polled every control cycle and are expected to cache.
        """
        pass
