"""Token bucket rate limiter for the public API."""

import time


class TokenBucket:
    """Allows `rate` requests per second with bursts up to `capacity`."""

    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.updated = time.monotonic()

    def allow(self) -> bool:
        """Take one token if there is one; refill by elapsed time first."""
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


def retry_after_seconds(bucket: TokenBucket) -> float:
    """How long a rejected client should wait before the next request (Retry-After header)."""
    missing = max(0.0, 1 - bucket.tokens)
    return missing / bucket.rate
