from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass(slots=True)
class Decision:
    choice: str
    confidence: float
    scores: dict[str, float] = field(default_factory=dict)

@dataclass(slots=True)
class RouteResult:
    route: str
    domain: str = "unknown"
    skill: str = "normal_hermes"
    arguments: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""
    context_source: str = "none"
    plan: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
