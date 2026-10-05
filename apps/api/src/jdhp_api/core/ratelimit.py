"""Sliding windows for tile requests, per user and per IP (SEC-12).

Two fixed windows approximate the sliding window the specification asks for: a one-second
burst window sized to pages times tiles per page, and a sixty-second sustained window. The
counters live in Redis so every gateway process sees the same picture. When Redis is
unreachable the limiter keeps counting in process memory: readers degrade, they never open
up (THREAT_MODEL T-G7).
"""

from __future__ import annotations

import dataclasses
import time
from collections import defaultdict

from redis.asyncio import Redis
from redis.exceptions import RedisError

BURST_WINDOW_SECONDS = 1
SUSTAINED_WINDOW_SECONDS = 60


@dataclasses.dataclass(frozen=True, slots=True)
class Limits:
    burst_per_second: int
    sustained_per_minute: int


class RateLimiter:
    def __init__(
        self, redis: Redis | None, limits: Limits, *, prefix: str = "jdhp:rl:tiles"
    ) -> None:
        self._redis = redis
        self._limits = limits
        self._prefix = prefix
        self._memory: dict[str, list[float]] = defaultdict(list)
        self.degraded = False

    def _keys(self, scope: str, subject: str, now: float) -> tuple[str, str]:
        second = int(now) // BURST_WINDOW_SECONDS
        minute = int(now) // SUSTAINED_WINDOW_SECONDS
        return (
            f"{self._prefix}:{scope}:{subject}:s:{second}",
            f"{self._prefix}:{scope}:{subject}:m:{minute}",
        )

    async def hit(self, scope: str, subject: str, now: float | None = None) -> bool:
        """Count one request. Returns False when either window is over its limit."""
        now = now if now is not None else time.time()
        burst_key, sustained_key = self._keys(scope, subject, now)
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline(transaction=True)
                pipe.incr(burst_key)
                pipe.expire(burst_key, BURST_WINDOW_SECONDS + 1)
                pipe.incr(sustained_key)
                pipe.expire(sustained_key, SUSTAINED_WINDOW_SECONDS + 1)
                burst, _, sustained, _ = await pipe.execute()
                self.degraded = False
                return (
                    int(burst) <= self._limits.burst_per_second
                    and int(sustained) <= self._limits.sustained_per_minute
                )
            except (RedisError, OSError):
                self.degraded = True
        return self._hit_in_memory(f"{scope}:{subject}", now)

    def _hit_in_memory(self, key: str, now: float) -> bool:
        stamps = self._memory[key]
        cutoff = now - SUSTAINED_WINDOW_SECONDS
        stamps[:] = [stamp for stamp in stamps if stamp > cutoff]
        stamps.append(now)
        burst = sum(1 for stamp in stamps if stamp > now - BURST_WINDOW_SECONDS)
        return (
            burst <= self._limits.burst_per_second
            and len(stamps) <= self._limits.sustained_per_minute
        )
