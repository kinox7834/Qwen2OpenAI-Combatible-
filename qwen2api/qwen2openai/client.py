import json
import uuid
import time
import logging
from typing import List, Dict, Optional, Tuple, Any

import httpx

from .config import settings, DEFAULT_HEADERS
from .tools import build_tool_system_prompt, fold_tool_messages
from .upload import upload_image_url

logger = logging.getLogger(__name__)

QWEN_BASE = settings.qwen_base_url

MODEL_ALIASES = {
    "qwen3.6-plus": "qwen3.6-plus",
    "qwen3.7-max": "qwen3.7-max",
    "qwen3.6-max-preview": "qwen3.6-max-preview",
    "qwen3.6-27b": "qwen3.6-27b",
    "qwen-latest-series-invite-beta-v24": "qwen-latest-series-invite-beta-v24",
    "qwen-latest-series-invite-beta-v16": "qwen-latest-series-invite-beta-v16",
    "qwen3.5-plus": "qwen3.5-plus",
    "qwen3.5-omni-plus": "qwen3.5-omni-plus",
    "qwen3.6-35b-a3b": "qwen3.6-35b-a3b",
    "qwen3.5-flash": "qwen3.5-flash",
    "qwen3.5-max-2026-03-08": "qwen3.5-max-2026-03-08",
    "qwen3.6-plus-preview": "qwen3.6-plus-preview",
    "qwen3.5-397b-a17b": "qwen3.5-397b-a17b",
    "qwen3.5-122b-a10b": "qwen3.5-122b-a10b",
    "qwen3.5-omni-flash": "qwen3.5-omni-flash",
    "qwen3.5-27b": "qwen3.5-27b",
    "qwen3.5-35b-a3b": "qwen3.5-35b-a3b",
    "qwen3-max-2026-01-23": "qwen3-max-2026-01-23",
    "qwen-plus-2025-07-28": "qwen-plus-2025-07-28",
    "qwen3-coder-plus": "qwen3-coder-plus",
    "qwen3-vl-plus": "qwen3-vl-plus",
    "qwen3-omni-flash-2025-12-01": "qwen3-omni-flash-2025-12-01",
    "qwen3.5-omni": "qwen3.5-omni-plus",
    "qwen3.5-max": "qwen3.5-max-2026-03-08",
    "qwen3.6-preview": "qwen3.6-plus-preview",
    "qwen3.5-397b": "qwen3.5-397b-a17b",
    "qwen3.5-122b": "qwen3.5-122b-a10b",
    "qwen-plus": "qwen-plus-2025-07-28",
    "qwen3-omni-flash": "qwen3-omni-flash-2025-12-01",
    "qwen-beta-v24": "qwen-latest-series-invite-beta-v24",
    "qwen-beta-v16": "qwen-latest-series-invite-beta-v16",
    "qwen": "qwen3.6-plus",
    "qwen3": "qwen3.6-plus",
    "qwen3.5": "qwen3.5-plus",
    "qwen3.6": "qwen3.6-plus",
    "qwen3.7": "qwen3.7-max",
    "qwen3-max": "qwen3-max-2026-01-23",
    "qwen3-coder": "qwen3-coder-plus",
    "qwen3-vl": "qwen3-vl-plus",
}


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                parts.append(str(item))
                continue
            t = item.get("type", "")
            if t == "text":
                parts.append(item.get("text", ""))
            elif t == "image_url":
                url = item.get("image_url", {}).get("url", "")
                parts.append(f"[Image: {url[:80]}]" if url else "[Image]")
            else:
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    return str(content)


def map_model(model: str) -> str:
    lower = model.lower()
    for suffix in ("-thinking", "-search", "-image", "-video"):
        lower = lower.replace(suffix, "")
    return MODEL_ALIASES.get(lower, lower)


class QwenClient:
    def __init__(self, token: str):
        self.token = token
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=30.0),
            follow_redirects=True,
        )

    async def _headers(self, chat_id: Optional[str] = None) -> Dict[str, str]:
        headers = {
            **DEFAULT_HEADERS,
            "Authorization": f"Bearer {self.token}",
            "X-Request-Id": str(uuid.uuid4()),
        }
        if chat_id:
            headers["Referer"] = f"{QWEN_BASE}/c/{chat_id}"
        return headers

    async def list_models(self) -> List[Dict[str, Any]]:
        url = f"{QWEN_BASE}/api/models"
        resp = await self.client.get(url, headers=await self._headers())
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    async def create_chat(self, model_id: str, title: str = "API Chat") -> str:
        url = f"{QWEN_BASE}/api/v2/chats/new"
        payload = {
            "title": title,
            "models": [model_id],
            "chat_mode": "normal",
            "chat_type": "t2t",
            "timestamp": int(time.time() * 1000),
            "project_id": "",
        }
        resp = await self.client.post(url, json=payload, headers=await self._headers())
        resp.raise_for_status()
        data = resp.json()
        chat_id = data.get("data", {}).get("id")
        if not chat_id:
            raise ValueError(f"Failed to create chat: {data}")
        return chat_id

    async def _process_multimodal(self, content: Any) -> tuple[str, list[str]]:
        if isinstance(content, str):
            return content, []
        if not isinstance(content, list):
            return str(content), []
        text_parts = []
        file_ids = []
        for item in content:
            if not isinstance(item, dict):
                text_parts.append(str(item))
                continue
            t = item.get("type", "")
            if t == "text":
                text_parts.append(item.get("text", ""))
            elif t == "image_url":
                url = item.get("image_url", {}).get("url", "")
                if url:
                    fid = await upload_image_url(self.token, url)
                    if fid:
                        file_ids.append(fid)
                    text_parts.append("[Image attached]" if fid else f"[Image (upload failed): {url[:60]}]")
            else:
                text_parts.append(str(item.get("text", "")))
        return "\n".join(text_parts), file_ids

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        stream: bool = True,
        temperature: Optional[float] = None,
        enable_thinking: Optional[bool] = None,
        enable_search: bool = False,
        chat_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Any = None,
        initial_system_prompt: str = "",
    ) -> Tuple[httpx.Response, str]:
        if not self.token:
            raise ValueError("Qwen token not configured")

        model_id = map_model(model)

        messages = fold_tool_messages(messages)

        if chat_id:
            logger.debug(f"Reusing existing chat {chat_id}")
        else:
            chat_id = await self.create_chat(model_id)

        system_content = initial_system_prompt
        conversation_parts = []
        current_user_msg = None
        all_file_ids: list[str] = []

        for msg in messages:
            role = msg.get("role", "")
            if role == "system":
                if not initial_system_prompt:
                    text = extract_text(msg.get("content", ""))
                    system_content += ("\n\n" if system_content else "") + text
            elif role == "user":
                if current_user_msg is not None:
                    conversation_parts.append(current_user_msg)
                text, file_ids = await self._process_multimodal(msg.get("content", ""))
                all_file_ids.extend(file_ids)
                current_user_msg = text
            elif role == "assistant":
                text = extract_text(msg.get("content", ""))
                if current_user_msg is not None:
                    paired = f"{current_user_msg}<｜Assistant｜>{text}<｜end of sentence｜>"
                    conversation_parts.append(paired)
                    current_user_msg = None
                else:
                    conversation_parts.append(f"<｜Assistant｜>{text}<｜end of sentence｜>")

        if current_user_msg is not None:
            conversation_parts.append(current_user_msg)

        if tools:
            tool_prompt = build_tool_system_prompt(tools, tool_choice)
            if tool_prompt:
                system_content = (tool_prompt + "\n\n" + system_content).strip()

        if len(conversation_parts) > 1:
            user_content = "<｜User｜>".join(conversation_parts)
        elif len(conversation_parts) == 1:
            user_content = conversation_parts[0]
        else:
            user_content = ""

        if system_content:
            user_content = f"{system_content}\n\n{user_content}"

        fid = str(uuid.uuid4())
        child_id = str(uuid.uuid4())
        ts = int(time.time())

        feature_config = {
            "thinking_enabled": True,
            "output_schema": "phase",
            "research_mode": "normal",
            "auto_thinking": True if enable_thinking is None else enable_thinking,
            "thinking_mode": "Auto",
            "thinking_format": "summary",
            "auto_search": enable_search,
        }

        payload = {
            "stream": True,
            "version": "2.1",
            "incremental_output": True,
            "chat_id": chat_id,
            "chat_mode": "normal",
            "model": model_id,
            "parent_id": parent_id,
            "messages": [
                {
                    "fid": fid,
                    "parentId": parent_id,
                    "childrenIds": [child_id],
                    "role": "user",
                    "content": user_content,
                    "user_action": "chat",
                    "files": [{"file_id": f} for f in all_file_ids] if all_file_ids else [],
                    "timestamp": ts,
                    "models": [model_id],
                    "chat_type": "t2t",
                    "feature_config": feature_config,
                    "extra": {"meta": {"subChatType": "t2t"}},
                    "sub_chat_type": "t2t",
                    "parent_id": parent_id,
                },
            ],
            "timestamp": ts + 1,
        }

        url = f"{QWEN_BASE}/api/v2/chat/completions?chat_id={chat_id}"
        headers = await self._headers(chat_id)
        headers["x-accel-buffering"] = "no"

        resp = await self.client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp, chat_id

    async def close(self):
        await self.client.aclose()
