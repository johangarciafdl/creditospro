import time
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rules=None):
        super().__init__(app)
        self.rules = rules or {
            "/auth/login": (10, 60),
        }
        self.requests = defaultdict(deque)
        self.lock = Lock()

    async def dispatch(self, request, call_next):
        rule = self.rules.get(request.url.path)
        if request.method == "POST" and rule:
            limit, window = rule
            forwarded_for = request.headers.get("x-forwarded-for", "")
            client = forwarded_for.split(",", 1)[0].strip() if forwarded_for else None
            client = client or (request.client.host if request.client else "unknown")
            key = (request.url.path, client)
            now = time.monotonic()
            with self.lock:
                bucket = self.requests[key]
                while bucket and now - bucket[0] > window:
                    bucket.popleft()
                if len(bucket) >= limit:
                    return JSONResponse({"error": "Demasiados intentos. Intenta mas tarde."}, status_code=429)
                bucket.append(now)
        return await call_next(request)
