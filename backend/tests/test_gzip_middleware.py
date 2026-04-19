"""GZip middleware must compress JSON but skip text/event-stream."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from app.middleware.gzip_safe import GZipSafeMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(GZipSafeMiddleware, minimum_size=500)

    @app.get("/big-json")
    def big_json():
        return JSONResponse({"data": "x" * 5000})

    @app.get("/small-json")
    def small_json():
        return JSONResponse({"data": "ok"})

    @app.get("/chat/stream")
    def stream():
        def gen():
            for i in range(3):
                yield f"data: event-{i}\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def test_json_is_gzipped():
    client = TestClient(_make_app())
    r = client.get("/big-json", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_sse_path_is_not_gzipped():
    client = TestClient(_make_app())
    r = client.get("/chat/stream", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") is None, (
        "SSE responses must not be gzipped — intermediate proxies may buffer chunks"
    )


def test_small_json_is_not_gzipped():
    client = TestClient(_make_app())
    r = client.get("/small-json", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") is None
