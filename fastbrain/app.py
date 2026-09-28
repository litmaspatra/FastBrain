from .config import Config
from .db import DB
from .skills import SkillRegistry
from .semantic import SemanticEngine
from .memory import MemoryBridge
from .context import ContextEngine
from .microreasoner import MicroReasoner
from .experience import ExperienceEngine
from .learner import SkillLearner
from .engine import FastBrain
from .executor import Executor


def build(cfg=None):
    cfg = cfg or Config.from_env()
    cfg.ensure()
    db = DB(cfg.db_path)
    registry = SkillRegistry(cfg.skills_path, db)
    memory = MemoryBridge(db, cfg)
    context = ContextEngine(db, memory)
    semantic = SemanticEngine(registry)
    experience = ExperienceEngine(db)
    micro = MicroReasoner(cfg, registry, context)
    engine = FastBrain(cfg, db, registry, semantic, context, micro, experience)
    return {
        "config": cfg,
        "db": db,
        "registry": registry,
        "memory": memory,
        "context": context,
        "semantic": semantic,
        "experience": experience,
        "micro": micro,
        "engine": engine,
        "executor": Executor(registry, experience, context),
        "learner": SkillLearner(registry, db),
    }
