from typing import Protocol


class ReadinessProbe(Protocol):
    """Future DB adapters implement this probe; liveness does not pretend to query a DB."""

    def is_ready(self) -> bool: ...
