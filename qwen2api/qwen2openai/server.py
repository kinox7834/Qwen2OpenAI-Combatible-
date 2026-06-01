import os
import socket
import subprocess
import time
import logging
import logging.handlers
from collections import defaultdict

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import init_token
from .config import settings
from .router import router

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 60, window: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window
        self.requests: dict = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        timeline = self.requests[client_ip]
        timeline[:] = [t for t in timeline if t > now - self.window]
        if len(timeline) >= self.max_requests:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
        timeline.append(now)
        return await call_next(request)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)
        key = request.headers.get("X-API-Key", "") or request.query_params.get("api_key", "")
        if key != self.api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key. Set X-API-Key header.")
        return await call_next(request)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response


def create_app() -> FastAPI:
    app = FastAPI(
        title="Qwen2API",
        description="Reverse proxy providing OpenAI-compatible API for Qwen Studio (chat.qwen.ai)",
        version="0.1.0",
    )

    app.add_middleware(SecurityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.api_key:
        app.add_middleware(ApiKeyMiddleware, api_key=settings.api_key)
        logger.info("API key authentication enabled")

    app.add_middleware(RateLimitMiddleware, max_requests=settings.rate_limit)
    logger.info(f"Rate limiting: {settings.rate_limit} requests/min per IP")

    app.include_router(router)

    return app


app = create_app()
init_token(settings.token)


def free_port(host: str, port: int):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect((host, port))
        s.close()
        logger.warning(f"Port {port} in use, killing old process...")
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line.upper():
                    parts = line.strip().split()
                    pid = parts[-1]
                    if pid.isdigit():
                        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        logger.info(f"Killed process PID {pid} on port {port}")
                        break
        except Exception:
            pass
        time.sleep(1)
    except ConnectionRefusedError:
        s.close()
    except OSError:
        s.close()


def setup_logging():
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = []

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(fmt))
    handlers.append(console)

    if settings.log_file:
        log_dir = os.path.dirname(settings.log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            settings.log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(fmt))
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers)


def run():
    setup_logging()

    if not settings.token:
        logger.warning("No QWEN_TOKENS configured! Set them in .env file.")
        logger.warning("Get token: chat.qwen.ai -> F12 -> Application -> Local Storage -> 'token'")

    bind_ip = settings.lan_ip

    logger.info(f"Starting Qwen2API on port {settings.port}")

    print()
    print("=" * 52)
    print("  Qwen2API is ready!")
    print(f"  Local:    http://127.0.0.1:{settings.port}")
    if bind_ip != "127.0.0.1":
        print(f"  Network:  http://{bind_ip}:{settings.port}")
    if settings.api_key:
        print(f"  API Key:  {settings.api_key}")
    print()
    print("  Connect any AI agent:")
    print(f"    OPENAI_BASE_URL=http://{bind_ip}:{settings.port}/v1")
    print(f"    OPENAI_API_KEY=<anything>")
    if settings.api_key:
        print(f"    X-API-Key: {settings.api_key}")
    print(f"    Model:    qwen3.6-plus (or any live model)")
    print("=" * 52)
    print()

    free_port(bind_ip, settings.port)

    uvicorn.run(
        app,
        host=bind_ip,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
