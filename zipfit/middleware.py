"""Bound profile submissions before JSON decoding, including chunked requests."""
from starlette.responses import JSONResponse


class ProfileBodyLimit:
    def __init__(self, app, max_bytes=16_384):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        length = dict(scope["headers"]).get(b"content-length")
        if length:
            try:
                too_large = int(length) > self.max_bytes
            except ValueError:
                return await JSONResponse({"detail": "올바르지 않은 요청입니다."}, status_code=400)(scope, receive, send)
            if too_large:
                return await self.reject(scope, receive, send)
        messages, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                return await self.reject(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            return messages.pop(0) if messages else await receive()

        return await self.app(scope, replay, send)

    async def reject(self, scope, receive, send):
        return await JSONResponse({"detail": "입력 정보가 너무 커요. 입력값을 확인해 주세요."}, status_code=413)(scope, receive, send)
