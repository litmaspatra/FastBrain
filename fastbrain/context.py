from __future__ import annotations
import time


class ContextEngine:
    TTL_SECONDS = {
        "pending_confirmation": 60,
        "person": 900,
        "app": 600,
        "message": 600,
        "action": 600,
        "media_query": 1800,
        "media_player": 1800,
        "music_query": 1800,
        "track": 3600,
    }

    def __init__(self, db, memory):
        self.db = db
        self.memory = memory

    def needs(self, skill: str) -> list[str]:
        if skill in {"call_contact", "send_whatsapp", "send_sms"}:
            return ["aliases", "recent_people"]
        if skill in {"play_music", "choose_music_from_context"}:
            return ["music_preferences", "recent_tracks", "time_of_day"]
        if skill == "open_app":
            return ["recent_apps"]
        return []

    def resolve_alias(self, name: str):
        m = self.memory.lookup_hot("alias", name, "communication")
        return (m.get("value") if m else name, m.get("_source", "none") if m else "none")

    def recent(self, kind, max_age_seconds=None):
        rows = self.db.work_recent(kind, 1)
        if not rows:
            return None
        row = rows[0]
        ttl = self.TTL_SECONDS.get(kind) if max_age_seconds is None else max_age_seconds
        if ttl is not None and time.time() - float(row.get("updated_at", 0)) > ttl:
            # If the newest row is stale, every older row of the same kind is stale too.
            self.db.work_delete(kind)
            return None
        return row["value"]

    def recent_values(self, kind, limit=5, max_age_seconds=None):
        ttl = self.TTL_SECONDS.get(kind) if max_age_seconds is None else max_age_seconds
        now = time.time()
        out = []
        stale = False
        for row in self.db.work_recent(kind, limit):
            if ttl is not None and now - float(row.get("updated_at", 0)) > ttl:
                stale = True
                continue
            out.append(row["value"])
        if stale and not out:
            self.db.work_delete(kind)
        return out

    def remember_entity(self, kind, value):
        self.db.work_set(kind, str(value).lower(), value)

    def set_pending_confirmation(self, payload):
        self.db.work_set("pending_confirmation", "contact", payload)

    def pending_confirmation(self, max_age_seconds=60):
        return self.recent("pending_confirmation", max_age_seconds=max_age_seconds)

    def clear_pending_confirmation(self):
        self.db.work_delete("pending_confirmation", "contact")

    def remember_action(self, skill, arguments):
        self.db.work_set("action", skill, {"skill": skill, "arguments": arguments})
        if arguments.get("contact"):
            self.remember_entity("person", arguments["contact"])
        if arguments.get("app"):
            self.remember_entity("app", arguments["app"])
        if arguments.get("message"):
            self.db.work_set("message", "last", arguments["message"])
        if arguments.get("query"):
            self.db.work_set("media_query", "last", arguments["query"])
        if arguments.get("player"):
            self.db.work_set("media_player", "last", arguments["player"])
        if skill in {"play_music", "choose_music_from_context"} and arguments.get("query"):
            self.db.work_set("music_query", "last", arguments["query"])
            self.remember_entity("track", arguments["query"])

    def time_bucket(self):
        h = time.localtime().tm_hour
        return "morning" if 5 <= h < 12 else "afternoon" if 12 <= h < 17 else "evening" if 17 <= h < 22 else "night"

    def music_context(self):
        bucket = self.time_bucket()
        # FastBrain's real-time path must never block on a durable-memory miss.
        # Hindsight remains durable truth, but preferences should be projected or
        # warmed into memory_hot before latency-sensitive device-control requests.
        m = self.memory.lookup_hot("preference", bucket, "music")
        # A negative cache entry means "no usable preference for this bucket".
        # It is metadata, not a real preference value, and must never reach the
        # media executor as a query string.
        if m and m.get("_negative"):
            m = None
        return {
            "time_of_day": bucket,
            "preference": m.get("value") if m else None,
            "recent_tracks": self.recent_values("track", 5),
            "source": m.get("_source", "none") if m else "none",
        }
