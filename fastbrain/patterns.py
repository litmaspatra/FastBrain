from __future__ import annotations

import re

_FAST_ROUTER_PATTERNS = [
    (re.compile(r"^(?:call|phone|ring)\s+(.+)$", re.I), lambda m: f"call_contact {m.group(1).strip()}"),
    (re.compile(r"^(?:message|text|whatsapp|sms)\s+(.+)$", re.I), lambda m: f"send_whatsapp {m.group(1).strip()}"),
    (re.compile(r"^(?:send|tell)\s+(.+?)\s+(?:to\s+)?(.+)$", re.I), lambda m: f"send_whatsapp {m.group(1).strip()} {m.group(2).strip()}"),
    (re.compile(r"^(?:play|open|watch|show)\s+(.+)$", re.I), lambda m: f"play_music {m.group(1).strip()}"),
    (re.compile(r"^(?:turn\s+)?(?:the\s+)?flashlight\s+(on|off)$", re.I), lambda m: f"torch_{'on' if m.group(1).lower() == 'on' else 'off'}"),
    (re.compile(r"^(?:turn\s+)?(?:the\s+)?torch\s+(on|off)$", re.I), lambda m: f"torch_{'on' if m.group(1).lower() == 'on' else 'off'}"),
    (re.compile(r"^(?:check|show|get)\s+(?:my\s+|the\s+)?battery(?:\s+status)?$", re.I), lambda _m: "battery_status"),
    (re.compile(r"^(?:(?:check|show|get)\s+(?:my\s+|the\s+)?)?(?:wifi|wi-fi)(?:\s+status)?$", re.I), lambda _m: "wifi_status"),
    (re.compile(r"^(?:set|turn)\s+volume(?:\s+to)?\s+(\d{1,3})$", re.I), lambda m: f"set_volume {m.group(1)}"),
]

def normalize_pre_router_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return ""
    for pattern, transformer in _FAST_ROUTER_PATTERNS:
        match = pattern.match(cleaned)
        if not match:
            continue
        transformed = transformer(match)
        if transformed:
            return transformed
    return cleaned

def maybe_deterministic_route(text: str):
    normalized = normalize_pre_router_text(text)
    if not normalized:
        return None
    if normalized.startswith("call_contact "):
        return {"skill": "call_contact", "args": {"contact": normalized.split(" ", 1)[1]}}
    if normalized.startswith("send_whatsapp "):
        rest = normalized.split(" ", 1)[1]
        parts = rest.split(maxsplit=1)
        if len(parts) == 2:
            return {"skill": "send_whatsapp", "args": {"contact": parts[0], "message": parts[1]}}
        return {"skill": "send_whatsapp", "args": {"contact": parts[0] if parts else "", "message": ""}}
    if normalized.startswith("play_music "):
        return {"skill": "play_music", "args": {"query": normalized.split(" ", 1)[1]}}
    if normalized.startswith("torch_"):
        return {"skill": normalized, "args": {}}
    if normalized in {"battery_status", "wifi_status"}:
        return {"skill": normalized, "args": {}}
    if normalized.startswith("set_volume "):
        try:
            return {"skill": "set_volume", "args": {"level": int(normalized.split(" ", 1)[1])}}
        except ValueError:
            pass
    return None
