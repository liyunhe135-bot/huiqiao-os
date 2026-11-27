"""本地模型适配器：只走 OpenAI 兼容接口，强制回环地址，绝不外联。

M01 铁律：
- 断网状态下必须可用；base_url 不是 127.0.0.1 / localhost 时直接拒绝。
- 不自己实现推理，只做协议翻译与节流。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.core.errors import HuiQiaoError


class OutboundBlocked(HuiQiaoError):
    code = "HQ101"


@dataclass
class ChatResponse:
    text: str
    model: str
    elapsed_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


def _assert_loopback(base_url: str) -> None:
    """离线铁律：只允许本机回环地址。"""
    low = base_url.lower()
    if not (low.startswith("http://127.0.0.1") or low.startswith("http://localhost")):
        raise OutboundBlocked(f"拒绝非回环地址: {base_url}（汇桥不联网）")


class _BaseAdapter:
    """适配器基类。transport 可注入以便离线单测，不碰真实网络。"""

    name = "base"

    def __init__(self, base_url: str, model: str, *, transport: Any = None) -> None:
        _assert_loopback(base_url)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.transport = transport

    def chat(self, messages: list[dict[str, str]], **options: Any) -> ChatResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            **options,
        }
        raw = self._post("/v1/chat/completions", payload)
        return self._parse(raw)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.transport is None:
            raise HuiQiaoError("M01 未注入 transport；真实 HTTP 传输将在允许拉起服务时接入")
        return self.transport(self.base_url + path, payload)

    def _parse(self, raw: dict[str, Any]) -> ChatResponse:
        try:
            choice = raw["choices"][0]["message"]["content"]
            usage = raw.get("usage", {})
        except (KeyError, IndexError, TypeError) as exc:
            raise HuiQiaoError(f"响应格式非法: {exc}") from exc
        return ChatResponse(
            text=choice or "",
            model=raw.get("model", self.model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
        )


class OllamaAdapter(_BaseAdapter):
    """Ollama OpenAI 兼容端点。"""

    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434/v1", model: str = "qwen3:8b", **kw: Any) -> None:
        super().__init__(base_url, model, **kw)


class LlamaServerAdapter(_BaseAdapter):
    """llama-server / llama-swap OpenAI 兼容端点。"""

    name = "llama-server"

    def __init__(self, base_url: str = "http://127.0.0.1:8080/v1", model: str = "local", **kw: Any) -> None:
        super().__init__(base_url, model, **kw)
