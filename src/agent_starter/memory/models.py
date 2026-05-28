from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Preference:
    key: str
    value: str


@dataclass
class Observation:
    text: str


@dataclass
class RecalledMemory:
    prefs: list[Preference] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.prefs and not self.observations
