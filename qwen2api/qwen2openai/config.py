import socket
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


@lru_cache(maxsize=1)
def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class Settings(BaseSettings):
    qwen_tokens: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    qwen_base_url: str = "https://chat.qwen.ai"
    log_level: str = "INFO"
    log_file: Optional[str] = None
    api_key: Optional[str] = None
    rate_limit: int = 60

    @property
    def token(self) -> str:
        if not self.qwen_tokens:
            return ""
        return self.qwen_tokens.split(",")[0].strip()

    @property
    def lan_ip(self) -> str:
        return get_lan_ip()

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Content-Type": "application/json",
    "source": "web",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Origin": settings.qwen_base_url,
    "Referer": settings.qwen_base_url + "/",
    "bx-v": "2.5.36",
    "Timezone": "Mon Feb 23 2026 22:06:02 GMT+0800",
    "Version": "0.2.7",
}
