"""DataSource interface. The twin engine only talks to this, so swapping the
simulator for real sensors (MQTT, BMS, smart meters) needs no engine changes."""
from abc import ABC, abstractmethod
from datetime import datetime


class DataSource(ABC):
    @abstractmethod
    def now(self) -> datetime: ...

    @abstractmethod
    def step(self, minutes: int = 1) -> None:
        """Advance by `minutes` (a real source would instead poll / drain its queue)."""

    @abstractmethod
    def readings(self) -> dict:
        """Latest readings: {"rooms": {...}, "washrooms": {...}, "bins": {...}}."""

    @abstractmethod
    def act(self, action: str, target: str) -> None:
        """Apply a field action (fix_room, fix_leak, empty_bin). Real source: no-op, the fix happens physically."""

    @abstractmethod
    def set_cv_override(self, room_id: str, people: int | None, lights_on: bool | None, fans_on: bool | None) -> None:
        """Feed computer-vision observations for a room."""
