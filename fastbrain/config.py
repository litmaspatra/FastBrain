from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(slots=True)
class Config:
    home: Path
    db_path: Path
    skills_path: Path
    memory_mode: str = "hybrid"
    hindsight_url: str = ""
    hindsight_path: str = "/recall"
    hindsight_cmd: str = ""
    direct_timeout: float = 0.8
    execute_threshold: float = 0.90
    context_threshold: float = 0.70
    max_plan_steps: int = 4

    @classmethod
    def from_env(cls) -> "Config":
        home = Path(os.getenv("FASTBRAIN_HOME", str(Path.home() / ".fastbrain"))).expanduser()
        pkg_skills = Path(__file__).resolve().parent.parent / "skills" / "builtin.json"
        return cls(
            home=home,
            db_path=Path(os.getenv("FASTBRAIN_DB", str(home / "fastbrain.db"))).expanduser(),
            skills_path=Path(os.getenv("FASTBRAIN_SKILLS", str(pkg_skills))).expanduser(),
            memory_mode=os.getenv("FASTBRAIN_MEMORY_MODE", "hybrid").lower(),
            hindsight_url=os.getenv("FASTBRAIN_HINDSIGHT_URL", "").rstrip("/"),
            hindsight_path=os.getenv("FASTBRAIN_HINDSIGHT_PATH", "/recall"),
            hindsight_cmd=os.getenv("FASTBRAIN_HINDSIGHT_CMD", ""),
            direct_timeout=float(os.getenv("FASTBRAIN_HINDSIGHT_TIMEOUT", "0.8")),
            execute_threshold=float(os.getenv("FASTBRAIN_EXECUTE_THRESHOLD", "0.90")),
            context_threshold=float(os.getenv("FASTBRAIN_CONTEXT_THRESHOLD", "0.70")),
            max_plan_steps=int(os.getenv("FASTBRAIN_MAX_PLAN_STEPS", "4")),
        )

    def ensure(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
