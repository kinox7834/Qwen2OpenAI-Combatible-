import sys
import os
import subprocess
import logging

logger = logging.getLogger(__name__)


def ensure_deps():
    try:
        import fastapi  # noqa
        import uvicorn  # noqa
        import httpx  # noqa
        import pydantic  # noqa
        import pydantic_settings  # noqa
    except ImportError:
        req = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
        if not os.path.exists(req):
            print("Dependencies missing. Install with: pip install qwen2openai")
            print("Or from source: pip install -r requirements.txt")
            sys.exit(1)
        print("Installing dependencies...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", req, "-q"]
        )
        print("Dependencies installed.")


def ensure_env():
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path) and "--setup" not in sys.argv:
        return

    print("\n=== Qwen2OpenAI Setup ===")
    print("Get your Qwen token from:")
    print("  1. Go to https://chat.qwen.ai")
    print("  2. Open DevTools (F12) \u2192 Application \u2192 Local Storage")
    print("  3. Copy the value of 'token'\n")

    existing = {}
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip()

    token = input(f"Paste your Qwen token{' (current: ' + existing.get('QWEN_TOKENS', '')[:16] + '...)' if existing.get('QWEN_TOKENS') else ''}: ").strip()
    if not token:
        token = existing.get("QWEN_TOKENS", "")

    current_api_key = existing.get("API_KEY", "")
    print(f"\nOptional: Set an API key to protect your proxy (recommended)")
    print(f"Agents will need to send X-API-Key header with this value.")
    api_key = input(f"API key{' (current: ' + current_api_key[:8] + '...)' if current_api_key else ''} (or press Enter to skip): ").strip()
    if not api_key:
        api_key = current_api_key

    with open(env_path, "w") as f:
        f.write(f'QWEN_TOKENS={token}\n')
        f.write(f'API_KEY={api_key}\n')
        f.write('# HOST= (leave empty to auto-detect LAN IP)\n')
        f.write('PORT=8000\n')
        f.write('QWEN_BASE_URL=https://chat.qwen.ai\n')
        f.write('LOG_LEVEL=INFO\n')
    print(f".env file saved at {env_path}\n")


def main():
    ensure_deps()
    if "--no-setup" not in sys.argv:
        ensure_env()

    from .server import run
    run()


if __name__ == "__main__":
    main()
