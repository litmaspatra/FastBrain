from . import __version__

API = 1  # bump when the /health shape or the router contract changes


def health_payload(stack):
    """Cheap, side-effect-free: no model loads, no network. Called by the router, the TCP bridge and the doctor."""
    cfg, sem = stack["config"], stack["semantic"].status()
    return {
        "ok": True,
        "status": "ready",
        "version": __version__,
        "api": API,
        "capabilities": {
            "semantic_backend": sem.get("backend"),
            "minilm_ready": bool(sem.get("minilm_ready")),
            "memory_mode": cfg.memory_mode,
            "hindsight_direct": bool(cfg.hindsight_url or cfg.hindsight_cmd),
            "skills": len(stack["registry"].all()),
            "llm": False,  # FastBrain makes no LLM calls; Hermes does
        },
    }
