"""
Rate limiting middleware — Redis-backed, per IP.
60 anrop/minut för vanliga endpoints, 10/minut för auth.
"""
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    In-process rate limiter (funkar på single-server setup).
    För multi-instance: byt till Redis-backend.
    """

    def __init__(self, app, default_rpm: int = 60, auth_rpm: int = 10):
        super().__init__(app)
        self.default_rpm = default_rpm
        self.auth_rpm = auth_rpm
        self._cache: dict[str, list[float]] = defaultdict(list)

    def _check(self, key: str, limit: int) -> bool:
        now = time.time()
        window = now - 60.0
        hits = self._cache[key]
        # Rensa gamla anrop
        self._cache[key] = [t for t in hits if t > window]
        if len(self._cache[key]) >= limit:
            return False
        self._cache[key].append(now)
        return True

    async def dispatch(self, request: Request, call_next):
        # Skippa health check
        if request.url.path == "/health":
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"

        # Striktare limit för auth-endpoints
        if request.url.path.startswith("/api/v1/auth"):
            limit = self.auth_rpm
            key = f"auth:{ip}"
        else:
            limit = self.default_rpm
            key = f"api:{ip}"

        if not self._check(key, limit):
            return JSONResponse(
                status_code=429,
                content={"detail": f"För många förfrågningar. Max {limit}/minut."},
                headers={"Retry-After": "60"},
            )

        return await call_next(request)
