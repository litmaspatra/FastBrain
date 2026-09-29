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
    semantic_backend: str = "auto"
    semantic_model: Path | None = None
    semantic_labels: Path | None = None
    semantic_dim: int = 2048
    semantic_helper: str = ""
    semantic_helper_timeout: float = 0.35
    semantic_min_confidence: float = 0.75

    @classmethod
    def from_env(cls) -> "Config":
        home = Path(os.getenv("FASTBRAIN_HOME", str(Path.home() / ".fastbrain"))).expanduser()
        pkg_skills = Path(__file__).resolve().parent.parent / "skills" / "builtin.json"
        model = Path(os.getenv("FASTBRAIN_SEMANTIC_MODEL", str(home / "models" / "semantic.onnx"))).expanduser()
        labels = Path(os.getenv("FASTBRAIN_SEMANTIC_LABELS", str(home / "models" / "semantic-labels.json"))).expanduser()
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
            semantic_backend=os.getenv("FASTBRAIN_SEMANTIC_BACKEND", "auto").lower(),
            semantic_model=model,
            semantic_labels=labels,
            semantic_dim=max(128, int(os.getenv("FASTBRAIN_SEMANTIC_DIM", "2048"))),
            semantic_helper=os.getenv("FASTBRAIN_SEMANTIC_HELPER", "").strip(),
            semantic_helper_timeout=float(os.getenv("FASTBRAIN_SEMANTIC_HELPER_TIMEOUT", "0.35")),
            semantic_min_confidence=max(0.0,min(1.0,float(os.getenv("FASTBRAIN_SEMANTIC_MIN_CONFIDENCE","0.75")))),
        )

    def ensure(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        (self.home / "models").mkdir(parents=True, exist_ok=True)
