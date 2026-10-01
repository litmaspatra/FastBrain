from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic


@dataclass
class RouteStage:
    name: str
    started: float
    ended: float | None = None

    @property
    def elapsed_ms(self) -> float:
        if self.ended is None:
            return 0.0
        return (self.ended - self.started) * 1000.0


@dataclass
class RouteTrace:
    stages: list[RouteStage] = field(default_factory=list)
    started_at: float = field(default_factory=monotonic)

    def begin(self, name: str):
        self.stages.append(RouteStage(name=name, started=monotonic()))
        return self.stages[-1]

    def end(self, name: str):
        now = monotonic()
        for stage in reversed(self.stages):
            if stage.name == name and stage.ended is None:
                stage.ended = now
                return stage
        return None

    def as_dict(self):
        return {
            "started_at": self.started_at,
            "stages": [{"name": s.name, "elapsed_ms": round(s.elapsed_ms, 3)} for s in self.stages],
            "total_ms": round((monotonic() - self.started_at) * 1000.0, 3),
        }
