# Qwen2OpenAI

A reverse proxy that exposes [Qwen Studio (chat.qwen.ai)](https://chat.qwen.ai) as an OpenAI-compatible API. Use Qwen's latest models (qwen3.7-max, qwen3.6-plus, etc.) with any AI coding agent that supports the OpenAI API format.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

## Features

- **OpenAI-compatible endpoints** — `/v1/chat/completions`, `/v1/models`
- **Streaming + non-streaming** — SSE streaming or single response
- **Single token** — simple setup with one Qwen JWT token
- **Tool/function calling** — via prompt injection (`<tool_call>` XML format)
- **Thinking/search mode** — append `-thinking` or `-search` to model names
- **Session persistence** — maintains conversation context across messages (saved to `sessions.json`)
- **Security** — optional API key auth, rate limiting, security headers
- **Auto-kill** — frees port on restart without manual PID hunting

## Installation

```bash
pip install qwen2openai
```

Or from source:

```bash
git clone https://github.com/YOUR_USERNAME/qwen2openai.git
cd qwen2openai
pip install -r requirements.txt
```

### Docker

```bash
docker build -t qwen2openai .
docker run -d \
  -p 8000:8000 \
  -e QWEN_TOKENS=your_token_here \
  -e API_KEY=your_api_key \
  qwen2openai
```

Mount a volume for persistent `.env` and logs:

```bash
docker run -d \
  -p 8000:8000 \
  -v /path/to/data:/app/data \
  -e QWEN_TOKENS=your_token_here \
  -e LOG_FILE=/app/data/qwen2openai.log \
  qwen2openai
```

## Quick Start

1. Get your Qwen token:
   - Open [chat.qwen.ai](https://chat.qwen.ai) in Chrome
   - Press F12 → **Application** → **Local Storage**
   - Copy the value of key `token`

2. Start the server (wizard will prompt for token):
   ```bash
   qwen2openai
   ```
   Or with `start.bat` / `start.ps1` (Windows).

3. Connect any AI agent:
   ```
   OPENAI_BASE_URL=http://192.168.x.x:8000/v1
   OPENAI_API_KEY=anything
   ```
   If API key auth is enabled, send `X-API-Key` header.

## Configuration

All settings go in a `.env` file (created by the setup wizard):

| Variable | Default | Description |
|---|---|---|
| `QWEN_TOKENS` | — | Qwen JWT token |
| `API_KEY` | — | Optional API key for proxy auth |
| `HOST` | `0.0.0.0` | Bind address (auto-detects LAN IP) |
| `PORT` | `8000` | Server port |
| `QWEN_BASE_URL` | `https://chat.qwen.ai` | Qwen Studio base URL |
| `RATE_LIMIT` | `60` | Max requests/min per IP |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `LOG_FILE` | — | Optional log file path (10 MB rotating, 5 backups) |

## Endpoints

### `POST /v1/chat/completions`

Standard OpenAI chat completion format.

```json
{
  "model": "qwen3.7-max",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": true,
  "temperature": 0.7
}
```

**Vision / multimodal:** Send images using OpenAI's content array format:

```json
{
  "model": "qwen3.7-max",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "What's in this image?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo..."}},
        {"type": "image_url", "image_url": {"url": "https://example.com/photo.jpg"}}
      ]
    }
  ]
}
```

Both base64 data URIs and public HTTP URLs are supported. Images are uploaded to Qwen Studio's file API automatically.

**Model naming:**
- Base model: `qwen3.7-max`, `qwen3.6-plus`, `qwen3.5-flash`, etc.
- Enable thinking: `qwen3.7-max-thinking`
- Enable web search: `qwen3.7-max-search`
- Both: `qwen3.7-max-thinking-search`

**Short aliases** (mapped by proxy to real model IDs):
`qwen`, `qwen3`, `qwen3.5`, `qwen3.6`, `qwen3.7`, `qwen3-max`, `qwen3-coder`, `qwen3-vl`, `qwen3.5-omni`, `qwen3.5-max`, `qwen3.6-preview`, `qwen-plus`, `qwen3-omni-flash`, `qwen-beta-v24`, `qwen-beta-v16`

### `GET /v1/models`

Lists available models (OpenAI-compatible format).

### `POST /v1/images/generations`

Not supported. Returns `501` with a pointer to the official DashScope API.

### `GET /debug`

Returns request headers and token pool state — useful for debugging.

## Tool / Function Calling

Tool calling works via prompt injection since Qwen Studio's web API has no native tools support. The proxy translates OpenAI `tools`/`tool_choice` into a `<tool_call>` XML format that Qwen understands.

```json
{
  "model": "qwen3.7-max",
  "messages": [{"role": "user", "content": "What's the weather in Tokyo?"}],
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Get weather",
      "parameters": {
        "type": "object",
        "properties": {
          "location": {"type": "string"}
        }
      }
    }
  }]
}
```

## Using with OpenCode

Add a provider in `~/.config/opencode/opencode.json`:

```json
{
  "provider": {
     "qwen2openai": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Qwen2OpenAI",
      "options": {
        "baseURL": "http://192.168.1.x:8000/v1"
      },
      "models": {
        "qwen3.7-max": { "permissions": ["all"] },
        "qwen3.6-plus": { "permissions": ["all"] },
        "qwen3.5-flash": { "permissions": ["all"] },
        "qwen3-coder-plus": { "permissions": ["all"] }
      }
    }
  }
}
```

Then in any project's `.opencode.json`:

```json
{
  "model": "qwen3.7-max",
  "provider": "qwen2openai"
}
```

See [OpenCode provider docs](https://opencode.ai/docs/providers) for more details.

## Project Structure

```
qwen2openai/
├── qwen2openai/
│   ├── __init__.py          # Package init, version, exports
│   ├── __main__.py          # Entry point + setup wizard
│   ├── server.py            # FastAPI app, middleware, uvicorn runner
│   ├── router.py            # API routes
│   ├── client.py            # Qwen HTTP client
│   ├── stream.py            # SSE parser, response builder
│   ├── tools.py             # Tool calling prompt injection
│   ├── models.py            # Pydantic models
│   ├── auth.py              # Token pool manager
│   └── config.py            # Settings from .env
├── sessions.json            # Persistent session storage (auto-created)
├── .github/
│   └── ISSUE_TEMPLATE/
│       └── bug_report.md    # GitHub issue template
├── Dockerfile               # Docker deployment
├── .dockerignore
├── pyproject.toml           # Package metadata
├── LICENSE                  # MIT license
├── server.py                # Alternative entry point
├── run_logged.py            # Launcher with file logging redirect
├── start.bat                # Windows batch launcher
├── start.ps1                # PowerShell launcher
├── debug-collect.bat        # Debug info collector
├── debug-collect.ps1
├── .env.example             # Configuration reference
└── requirements.txt
```

## Logging

By default, logs go to stdout. To write to a file with rotation:

```bash
# In .env
LOG_FILE=qwen2openai.log

# Or via environment variable
LOG_FILE=qwen2openai.log qwen2openai
```

- **Rotation**: 10 MB per file, up to 5 backups (`qwen2openai.log.1`, `qwen2openai.log.2`, ...)
- **Format**: `2026-05-31 22:55:35,611 [INFO] qwen2openai.server: message`

## Notes

- The proxy binds to your LAN IP (not `0.0.0.0`) for network-level security.
- Port-in-use auto-kill uses `netstat` + `taskkill` (Windows) to free the port on restart.
- Tokens are checked periodically for recovery from rate limits.
