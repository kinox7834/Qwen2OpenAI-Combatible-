import logging

logger = logging.getLogger(__name__)

_qwen_token: str = ""


def init_token(token: str):
    global _qwen_token
    _qwen_token = token
    if token:
        logger.info("Qwen token configured")


def get_token() -> str:
    return _qwen_token
