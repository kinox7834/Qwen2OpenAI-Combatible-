import json
import uuid
import time
import asyncio
import logging
import pathlib
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse

from .auth import get_token
from .client import QwenClient, map_model
from .config import settings
from .models import (
    ChatRequest,
    ModelList,
    ModelInfo,
    HealthResponse,
)
from .stream import parse_qwen_sse, build_non_streaming_response, SessionContainer
from .stream import collect_sse_response
from .tools import ToolCallStreamParser, parse_tool_calls_from_text, build_tool_system_prompt

logger = logging.getLogger(__name__)

SESSIONS_FILE = pathlib.Path(__file__).parent.parent / "sessions.json"


def _save_sessions():
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(_sessions, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save sessions: {e}")


def _load_sessions() -> dict:
    try:
        if SESSIONS_FILE.exists():
            with open(SESSIONS_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load sessions: {e}")
    return {}

router = APIRouter()


def _requires_tool_call(tool_choice) -> bool:
    if tool_choice == "required":
        return True
    if isinstance(tool_choice, dict) and tool_choice.get("type") == "function" and tool_choice.get("function", {}).get("name"):
        return True
    return False


def _build_required_retry_hint(tool_choice) -> str:
    if isinstance(tool_choice, dict) and tool_choice.get("function", {}).get("name"):
        name = tool_choice["function"]["name"]
        return f"You did not call any tool in your previous reply. You MUST now call the tool `{name}` using the <tool_call>...</tool_call> format and nothing else."
    return "You did not call any tool in your previous reply. You MUST now call exactly one tool using the <tool_call>...</tool_call> format and nothing else."


@router.get("/debug")
async def debug(request: Request):
    token = get_token()
    return {
        "headers": dict(request.headers),
        "token_configured": bool(token),
        "token_preview": token[:16] + "..." if token else None,
    }


@router.get("/health")
async def health():
    return HealthResponse(
        status="ok",
        token_configured=bool(get_token()),
    )


def _default_models():
    return [
        {"id": "qwen3.6-plus", "object": "model", "owned_by": "qwen"},
        {"id": "qwen3.7-max", "object": "model", "owned_by": "qwen"},
        {"id": "qwen3.6-max-preview", "object": "model", "owned_by": "qwen"},
        {"id": "qwen3.5-plus", "object": "model", "owned_by": "qwen"},
        {"id": "qwen3.5-flash", "object": "model", "owned_by": "qwen"},
        {"id": "qwen3-coder-plus", "object": "model", "owned_by": "qwen"},
    ]


@router.get("/v1/models")
async def list_models():
    token = get_token()
    if not token:
        raise HTTPException(status_code=401, detail="No token configured")

    try:
        models = await _get_client(token).list_models()
    except Exception as e:
        logger.error(f"Failed to fetch models: {e}")
        models = _default_models()

    return ModelList(
        data=[
            ModelInfo(
                id=m.get("id", "unknown"),
                object="model",
                owned_by=m.get("owned_by", "qwen"),
                capabilities=m.get("info", {}).get("meta", {}).get("capabilities"),
            )
            for m in models
        ]
    )


@router.post("/v1/images/generations")
async def image_generations():
    raise HTTPException(
        status_code=501,
        detail="Image generation is not available via the Qwen Studio web API. "
        "Use the official Alibaba Cloud DashScope API (https://dashscope.aliyun.com) "
        "with models like qwen-image-plus or qwen-image.",
    )


_sessions: dict = _load_sessions()
_session_locks: dict = {}
_clients: dict = {}


def _get_session_lock(token: str) -> asyncio.Lock:
    if token not in _session_locks:
        _session_locks[token] = asyncio.Lock()
    return _session_locks[token]


def _get_client(token: str) -> QwenClient:
    if token not in _clients:
        _clients[token] = QwenClient(token)
    return _clients[token]


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, body: ChatRequest):
    token = get_token()
    if not token:
        raise HTTPException(status_code=401, detail="No token configured")

    messages_dict = [m.model_dump() for m in body.messages]
    has_tools = bool(body.tools)
    tool_choice = body.tool_choice

    enable_thinking = True
    model_name = body.model
    enable_search = False

    if "-thinking" in model_name:
        enable_thinking = True
        model_name = model_name.replace("-thinking", "")
    if "-search" in model_name:
        enable_search = True
        model_name = model_name.replace("-search", "")

    force_new = request.query_params.get("new_chat", "").lower() in ("true", "1", "yes")

    client = _get_client(token)

    session_chat_id = None
    session_parent_id = None
    initial_system = ""

    if not session_parent_id and not force_new:
        for m in messages_dict:
            if m.get("role") == "system":
                initial_system += ("\n\n" if initial_system else "") + m.get("content", "")

    model_id = map_model(model_name)

    async with _get_session_lock(token):
        if force_new:
            _sessions.pop(token, None)
            _save_sessions()
        else:
            session = _sessions.get(token, {})
            session_chat_id = session.get("chat_id")
            session_parent_id = session.get("parent_id")
            if not session_chat_id:
                session_chat_id = await client.create_chat(model_id)
                _sessions[token] = {"chat_id": session_chat_id, "system_prompt": initial_system}
                _save_sessions()
            elif not session.get("system_prompt"):
                _sessions[token] = {**session, "system_prompt": initial_system}
                _save_sessions()
            else:
                initial_system = session.get("system_prompt", "")

        try:
            resp, chat_id = await client.chat_completion(
                model=model_name,
                messages=messages_dict,
                stream=body.stream,
                temperature=body.temperature,
                enable_thinking=enable_thinking,
                enable_search=enable_search,
                chat_id=session_chat_id,
                parent_id=session_parent_id,
                tools=body.tools,
                tool_choice=tool_choice,
                initial_system_prompt=initial_system,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Chat completion failed")
            raise HTTPException(status_code=500, detail=str(e))

        if body.stream:
            tool_parser = ToolCallStreamParser() if has_tools else None

            async def stream_with_session(tp=tool_parser):
                container = SessionContainer()
                async for chunk in parse_qwen_sse(resp, model_name, chat_id, container, tool_parser=tp):
                    yield chunk
                if tp:
                    tail = tp.flush()
                    if tail["text_delta"]:
                        yield f'data: {json.dumps({"id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion.chunk", "created": int(time.time()), "model": model_name, "choices": [{"index": 0, "delta": {"content": tail["text_delta"]}, "finish_reason": None}]})}\n\n'
                    for call in tail["completed_calls"]:
                        yield f'data: {json.dumps({"id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion.chunk", "created": int(time.time()), "model": model_name, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": call["index"], "id": call["id"], "type": "function", "function": {"name": call["function"]["name"], "arguments": ""}}]}, "finish_reason": None}]})}\n\n'
                        args = call["function"]["arguments"]
                        for off in range(0, len(args), 32):
                            yield f'data: {json.dumps({"id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion.chunk", "created": int(time.time()), "model": model_name, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": call["index"], "function": {"arguments": args[off:off+32]}}]}, "finish_reason": None}]})}\n\n'
                    if tail["completed_calls"]:
                        yield f'data: {json.dumps({"id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion.chunk", "created": int(time.time()), "model": model_name, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})}\n\n'
                if container.parent_id:
                    _sessions[token] = {"chat_id": chat_id, "parent_id": container.parent_id}
                    _save_sessions()

            return StreamingResponse(
                stream_with_session(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            full_content, reasoning_content, resp_parent_id = await collect_sse_response(resp)
            tool_calls = None
            if has_tools:
                cleaned, extracted = parse_tool_calls_from_text(full_content)
                if extracted:
                    tool_calls = extracted
                    full_content = cleaned
            if not tool_calls and _requires_tool_call(tool_choice):
                retry_hint = _build_required_retry_hint(tool_choice)
                retry_messages = messages_dict + [{"role": "system", "content": retry_hint}]
                try:
                    retry_resp, retry_chat_id = await client.chat_completion(
                        model=model_name,
                        messages=retry_messages,
                        stream=False,
                        temperature=body.temperature,
                        enable_thinking=enable_thinking,
                        enable_search=enable_search,
                        chat_id=chat_id,
                        parent_id=resp_parent_id,
                        tools=body.tools,
                        tool_choice=tool_choice,
                    )
                    retry_content, _, retry_parent = await collect_sse_response(retry_resp)
                    if retry_parent:
                        resp_parent_id = retry_parent
                    if has_tools:
                        cleaned_retry, retry_calls = parse_tool_calls_from_text(retry_content)
                        if retry_calls:
                            tool_calls = retry_calls
                            full_content = cleaned_retry
                except Exception as e:
                    logger.warning(f"tool_choice retry failed: {e}")
            result = build_non_streaming_response(full_content, reasoning_content, model_name, tool_calls=tool_calls)
            if resp_parent_id:
                _sessions[token] = {"chat_id": chat_id, "parent_id": resp_parent_id}
                _save_sessions()
            return JSONResponse(content=result)
