import json
import logging
import re
import uuid
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

TOOL_CALL_OPEN = "<tool_call>"
TOOL_CALL_CLOSE = "</tool_call>"
_TOOL_CALL_RE = re.compile(re.escape(TOOL_CALL_OPEN) + r"([\s\S]*?)" + re.escape(TOOL_CALL_CLOSE))
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")


def _compress_schema_type(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "any"
    enum_vals = schema.get("enum")
    if isinstance(enum_vals, list) and enum_vals:
        return " | ".join(json.dumps(v) for v in enum_vals)
    t = schema.get("type", "any")
    if t == "array":
        item = _compress_schema_type(schema.get("items", {}))
        return f"{item}[]"
    if t == "object":
        props = schema.get("properties")
        if not isinstance(props, dict):
            return "object"
        required = set(schema.get("required", []) if isinstance(schema.get("required"), list) else [])
        fields = []
        for key, val in props.items():
            opt = "" if key in required else "?"
            fields.append(f"{key}{opt}: {_compress_schema_type(val)}")
        return "{ " + "; ".join(fields) + " }"
    if isinstance(t, list):
        return " | ".join(_compress_schema_type({**schema, "type": tt}) for tt in t)
    return str(t)


def _compress_tool_definition(tool: dict) -> str:
    fn = tool.get("function", tool)
    name = fn.get("name", "unknown")
    desc = (fn.get("description", "") or "").strip()
    params = fn.get("parameters", {"type": "object", "properties": {}})
    sig = _compress_schema_type(params)
    if desc:
        return f"- {name}{sig}\n  {desc}"
    return f"- {name}{sig}"


def build_tool_system_prompt(tools: List[dict], tool_choice: Any = None) -> str:
    if not tools:
        return ""

    compressed = "\n".join(_compress_tool_definition(t) for t in tools)

    choice = tool_choice
    must_call = choice == "required" or (isinstance(choice, dict) and choice.get("function", {}).get("name"))

    lines = [
        "CRITICAL: You MUST use the tools below to accomplish tasks. Never describe what you want to do — emit the exact tool call XML.",
        "",
        "## Available Tools",
        compressed,
        "",
        "## How to call a tool",
        "Output EXACTLY this format, nothing else:",
        "<tool_call>",
        '{"name": "tool_name", "arguments": {"arg1": "value1"}}',
        "</tool_call>",
        "",
        "## Receiving results",
        "Tool results come back as:",
        '<tool_response tool_call_id="..." name="tool_name">',
        "...result...",
        "</tool_response>",
        "",
        "## Rules",
        "- ONE `<tool_call>` block per tool invocation.",
        "- JSON inside MUST be valid, on one logical line.",
        "- Use the exact tool name from the list above.",
        "- Provide all required arguments; skip unknown ones.",
        "- Do NOT wrap in code fences or markdown.",
        "- Do NOT explain what you are about to do. Just emit the XML.",
    ]

    if must_call:
        lines.append("- You MUST call at least one tool before writing anything else.")

    return "\n".join(lines)


def fold_tool_messages(messages: List[dict]) -> List[dict]:
    if not messages:
        return messages

    call_id_to_name: dict = {}
    result = []

    for msg in messages:
        if not isinstance(msg, dict):
            result.append(msg)
            continue

        role = msg.get("role", "")

        if role == "assistant" and msg.get("tool_calls"):
            blocks = []
            for call in msg["tool_calls"]:
                fn = call.get("function", {})
                args = fn.get("arguments", {})
                name = fn.get("name", "unknown")
                cid = call.get("id", f"call_{uuid.uuid4().hex[:24]}")
                call_id_to_name[cid] = name
                if isinstance(args, str):
                    payload = f'{{"name": {json.dumps(name)}, "arguments": {args}}}'
                else:
                    payload = json.dumps({"name": name, "arguments": args})
                blocks.append(f"{TOOL_CALL_OPEN}\n{payload}\n{TOOL_CALL_CLOSE}")

            original = msg.get("content") or ""
            content = original
            if blocks:
                content = (original + "\n" + "\n".join(blocks)).strip()
            result.append({"role": "assistant", "content": content})

        elif role == "tool":
            call_id = msg.get("tool_call_id", "")
            name = msg.get("name") or call_id_to_name.get(call_id, "tool")
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content)
            id_attr = f' tool_call_id="{_escape_attr(call_id)}"' if call_id else ""
            result.append({
                "role": "user",
                "content": f"<tool_response{id_attr} name=\"{_escape_attr(name)}\">\n{content}\n</tool_response>"
            })

        else:
            result.append(msg)

    return result


_ATTR_ESCAPE = str.maketrans({"&": "&amp;", '"': "&quot;", "<": "&lt;", ">": "&gt;"})

def _escape_attr(value: str) -> str:
    return (value or "").translate(_ATTR_ESCAPE)


def _replacer(m: re.Match, tool_calls: list) -> str:
    inner = m.group(1).strip()
    payload = _parse_tool_call_payload(inner)
    if payload:
        tool_calls.append({
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {
                "name": payload["name"],
                "arguments": json.dumps(payload["arguments"]),
            },
        })
    return ""


def parse_tool_calls_from_text(text: str) -> Tuple[str, List[dict]]:
    if not isinstance(text, str) or TOOL_CALL_OPEN not in text:
        return text or "", []

    tool_calls = []
    cleaned = _TOOL_CALL_RE.sub(lambda m: _replacer(m, tool_calls), text).strip()
    return cleaned, tool_calls


def _parse_tool_call_payload(raw: str) -> Optional[dict]:
    if not raw:
        return None
    text = raw.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        fence = _CODE_FENCE_RE.search(text)
        if fence:
            text = fence.group(1).strip()
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return None
        else:
            return None
    if not isinstance(parsed, dict):
        return None
    name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
    args = parsed.get("arguments") or parsed.get("parameters") or parsed.get("args") or {}
    if not name:
        return None
    return {"name": str(name), "arguments": args}


class ToolCallStreamParser:
    def __init__(self):
        self._pending_text = ""
        self._in_tool_call = False
        self._tool_call_buffer = ""
        self._emitted_count = 0

    def push(self, chunk: str) -> dict:
        result = {"text_delta": "", "completed_calls": []}
        if not chunk:
            return result

        buffer = chunk

        while buffer:
            if self._in_tool_call:
                self._tool_call_buffer += buffer
                buffer = ""
                close_idx = self._tool_call_buffer.find(TOOL_CALL_CLOSE)
                if close_idx == -1:
                    break
                inner = self._tool_call_buffer[:close_idx]
                buffer = self._tool_call_buffer[close_idx + len(TOOL_CALL_CLOSE):]
                self._tool_call_buffer = ""
                payload = _parse_tool_call_payload(inner)
                if payload:
                    result["completed_calls"].append({
                        "index": self._emitted_count,
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": payload["name"],
                            "arguments": json.dumps(payload["arguments"]),
                        },
                    })
                    self._emitted_count += 1
                self._in_tool_call = False
                continue

            self._pending_text += buffer
            buffer = ""

            open_idx = self._pending_text.find(TOOL_CALL_OPEN)
            if open_idx != -1:
                before = self._pending_text[:open_idx]
                if before:
                    result["text_delta"] += before
                tail = self._pending_text[open_idx + len(TOOL_CALL_OPEN):]
                self._pending_text = ""
                self._in_tool_call = True
                buffer = tail
                continue

            safe, remainder = self._split_safe_text(self._pending_text)
            if safe:
                result["text_delta"] += safe
            self._pending_text = remainder

        return result

    def flush(self) -> dict:
        result = {"text_delta": "", "completed_calls": []}
        if self._in_tool_call and self._tool_call_buffer:
            payload = _parse_tool_call_payload(self._tool_call_buffer)
            if payload:
                result["completed_calls"].append({
                    "index": self._emitted_count,
                    "id": f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {
                        "name": payload["name"],
                        "arguments": json.dumps(payload["arguments"]),
                    },
                })
                self._emitted_count += 1
            self._tool_call_buffer = ""
            self._in_tool_call = False
        if self._pending_text:
            result["text_delta"] += self._pending_text
            self._pending_text = ""
        return result

    def has_pending_call(self) -> bool:
        return self._in_tool_call

    def has_emitted_any_call(self) -> bool:
        return self._emitted_count > 0

    @staticmethod
    def _split_safe_text(text: str) -> Tuple[str, str]:
        open_tag = TOOL_CALL_OPEN
        idx = text.find(open_tag)
        if idx != -1:
            return text[:idx], text[idx:]
        if not text or len(text) >= len(open_tag):
            return text, ""
        if open_tag.startswith(text):
            return "", text
        return text, ""
