from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
import time


class ChatMessage(BaseModel):
    role: str
    content: str | List[Dict[str, Any]] = ""


class Message(BaseModel):
    role: str
    content: str = ""
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatRequest(BaseModel):
    model: str = "qwen3.6-plus"
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None


class Delta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class Choice(BaseModel):
    index: int = 0
    delta: Delta = Field(default_factory=Delta)
    message: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    id: str = ""
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: List[Choice] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)


class StreamChunk(BaseModel):
    id: str = ""
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: List[Choice] = Field(default_factory=list)


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    owned_by: str = "qwen"
    capabilities: Optional[Dict[str, bool]] = None


class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelInfo] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    token_configured: bool = False
