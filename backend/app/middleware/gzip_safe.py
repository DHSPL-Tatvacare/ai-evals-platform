"""GZip middleware that leaves SSE routes uncompressed."""
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import Receive, Scope, Send


class GZipSafeMiddleware(GZipMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path.endswith("/stream"):
            await self.app(scope, receive, send)
            return

        await super().__call__(scope, receive, send)
