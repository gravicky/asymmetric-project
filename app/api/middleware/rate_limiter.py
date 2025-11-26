'''
uses leaky bucket algorithm
'''

from functools import wraps
from fastapi import HTTPException
import time

# store: {user_id: {tokens, last_refill}} use central db/cache to store this in actual production code
token_buckets = {}

def rate_limit(max_requests: int = 100, window: int = 600):
    refill_rate = max_requests / window

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get("user", {})
            user_id = user.get("user_id", "anonymous")

            now = time.time()

            bucket = token_buckets.get(user_id, {
                "tokens": max_requests,
                "last": now
            })

            # refill
            elapsed = now - bucket["last"]
            bucket["tokens"] = min(
                max_requests,
                bucket["tokens"] + elapsed * refill_rate
            )
            bucket["last"] = now

            if bucket["tokens"] < 1:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")

            bucket["tokens"] -= 1

            token_buckets[user_id] = bucket
            return await func(*args, **kwargs)

        return wrapper
    return decorator

'''
we can also use some other libraries directly for rate limiting, slowapi - which is by default in memory, but also can use redis
and fastapi-limiter which by default uses redis

slowapi config in main.py
'''