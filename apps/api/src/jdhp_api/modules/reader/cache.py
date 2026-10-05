"""Redis keys the reader relies on: cached decisions and heartbeats (ARCHITECTURE 9.9).

Revocation deletes a session's keys at once, so the next tile or heartbeat fails within the
60-second cache window (ACS-2, SEC-5).
"""

from __future__ import annotations

import datetime as dt

from redis.asyncio import Redis

DECISION_TTL_SECONDS = 60
DECISION_PREFIX = "jdhp:grant"
HEARTBEAT_PREFIX = "jdhp:hb"


class ReaderCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def decision_key(session_public_id: str, seq: int) -> str:
        return f"{DECISION_PREFIX}:{session_public_id}:{seq}"

    @staticmethod
    def heartbeat_key(session_public_id: str) -> str:
        return f"{HEARTBEAT_PREFIX}:{session_public_id}"

    async def put_decision(self, session_public_id: str, seq: int, *, allowed: bool) -> None:
        await self._redis.set(
            self.decision_key(session_public_id, seq),
            "1" if allowed else "0",
            ex=DECISION_TTL_SECONDS,
        )

    async def get_decision(self, session_public_id: str, seq: int) -> bool | None:
        value = await self._redis.get(self.decision_key(session_public_id, seq))
        if value is None:
            return None
        return value in (b"1", "1")

    async def touch(self, session_public_id: str, ttl_seconds: int) -> None:
        await self._redis.set(
            self.heartbeat_key(session_public_id),
            dt.datetime.now(dt.UTC).isoformat(),
            ex=ttl_seconds,
        )

    async def is_alive(self, session_public_id: str) -> bool:
        return bool(await self._redis.exists(self.heartbeat_key(session_public_id)))

    async def clear_session(self, session_public_id: str) -> int:
        """Delete every cached decision and the heartbeat of one session. Returns the count."""
        pattern = f"{DECISION_PREFIX}:{session_public_id}:*"
        found = [key async for key in self._redis.scan_iter(match=pattern, count=200)]
        keys = [self.heartbeat_key(session_public_id)] + [
            key.decode() if isinstance(key, bytes) else str(key) for key in found
        ]
        return int(await self._redis.delete(*keys))
