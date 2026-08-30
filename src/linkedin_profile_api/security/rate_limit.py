from __future__ import annotations

import time
from collections import defaultdict, deque

from linkedin_profile_api.linkedin.exceptions import LocalRateLimitedError
from linkedin_profile_api.security.api_key import KeyRole


class RateLimiter:
    def __init__(self, evaluator_per_hour: int, demo_per_hour: int) -> None:
        self._limits = {
            KeyRole.EVALUATOR: evaluator_per_hour,
            KeyRole.DEMO: demo_per_hour,
        }
        self._hits: dict[KeyRole, deque[float]] = defaultdict(deque)
        self._window = 3600.0

    def check(self, role: KeyRole) -> None:
        now = time.monotonic()
        bucket = self._hits[role]
        cutoff = now - self._window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self._limits[role]:
            raise LocalRateLimitedError()
        bucket.append(now)
