import json
import time
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator, Dict, Any, Optional, List

from .tools import ToolCallStreamParser, parse_tool_calls_from_text

logger = logging.getLogger(__name__)


@dataclass
class SessionContainer:
    chat_id: Optional[str] = None
    parent_id: Optional[str] = None


async def parse_qwen_sse(
    response,
    model: str,
    chat_id: str,
    container: Optional[SessionContainer] = None,
    tool_parser: Optional[ToolCallStreamParser] = None,
) -> AsyncGenerator[str, None]:
    chat_id_str = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    started = False

    yield f'data: {json.dumps({"id": chat_id_str, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})}\n\n'

    async for line in response.aiter_lines():
        if not line.strip():
            continue
        if not line.startswith("data: "):
            continue

        raw = line[6:]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if "response.created" in data:
            started = True
            if container is not None:
                rc = data["response.created"]
                container.chat_id = rc.get("chat_id")
                container.parent_id = rc.get("response_id")
            continue

        if data.get("type") == "error" or "error" in data:
            err = data.get("error", {}) or data.get("message", "Unknown error")
            yield f'data: {json.dumps({"error": {"message": str(err), "type": "api_error"}})}\n\n'
            break

        choices = data.get("choices", [])
        if not choices:
            continue

        now = int(time.time())
        delta = choices[0].get("delta", {})
        phase = delta.get("phase", "answer")
        content = delta.get("content", "")
        response_id = data.get("response_id", chat_id_str)
        status = delta.get("status", "")

        if phase == "thinking_summary":
            if content:
                yield f'data: {json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": now, "model": model, "choices": [{"index": 0, "delta": {"content": None, "reasoning_content": content}, "finish_reason": None}]}, ensure_ascii=False)}\n\n'

        elif phase == "answer":
            if tool_parser:
                parsed = tool_parser.push(content)
                if parsed["text_delta"]:
                    yield f'data: {json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": now, "model": model, "choices": [{"index": 0, "delta": {"content": parsed["text_delta"]}, "finish_reason": None}]}, ensure_ascii=False)}\n\n'
                for call in parsed["completed_calls"]:
                    yield f'data: {json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": now, "model": model, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": call["index"], "id": call["id"], "type": "function", "function": {"name": call["function"]["name"], "arguments": ""}}]}, "finish_reason": None}]}, ensure_ascii=False)}\n\n'
                    args = call["function"]["arguments"]
                    for offset in range(0, len(args), 256):
                        piece = args[offset:offset + 256]
                        yield f'data: {json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": now, "model": model, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": call["index"], "function": {"arguments": piece}}]}, "finish_reason": None}]}, ensure_ascii=False)}\n\n'
            else:
                if content:
                    yield f'data: {json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": now, "model": model, "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]}, ensure_ascii=False)}\n\n'

        if status == "finished" and phase == "answer":
            finish_reason = "tool_calls" if (tool_parser and tool_parser.has_emitted_any_call()) else "stop"
            yield f'data: {json.dumps({"id": response_id, "object": "chat.completion.chunk", "created": now, "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}]})}\n\n'

    if not started:
        yield f'data: {json.dumps({"error": {"message": "No response from Qwen", "type": "api_error"}})}\n\n'

    yield "data: [DONE]\n\n"


async def collect_sse_response(response) -> tuple[str, str, Optional[str]]:
    full_content = ""
    reasoning_content = ""
    extracted_parent_id = None
    async for line in response.aiter_lines():
        if not line.strip() or not line.startswith("data: "):
            continue
        raw = line[6:]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if "response.created" in data:
            rc = data["response.created"]
            extracted_parent_id = rc.get("response_id")
            continue

        choices = data.get("choices", [])
        if not choices:
            continue
        delta = choices[0].get("delta", {})
        phase = delta.get("phase", "answer")
        content = delta.get("content", "")
        if phase == "thinking_summary" and content:
            reasoning_content += content
        elif phase == "answer" and content:
            full_content += content
    return full_content, reasoning_content, extracted_parent_id


def build_non_streaming_response(
    full_content: str,
    reasoning_content: str,
    model: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    message: Dict[str, Any] = {
        "role": "assistant",
        "content": full_content if full_content else "",
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    if reasoning_content:
        message["reasoning_content"] = reasoning_content

    finish_reason = "tool_calls" if tool_calls else "stop"

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
