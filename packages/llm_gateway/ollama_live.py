"""M01 / M07 本机 Ollama 回环自动探活与推理桥接器（100% 仅访问 127.0.0.1，零外网依赖）."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import urlparse

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# 针对 12GB VRAM 独显（如 RTX 4070）+ 64GB RAM 的本地编程与共生模型优先推荐序
_PREFERRED_MODELS = (
    "qwen3.5:9b",
    "gemma4:12b",
    "qwen3-coder:30b",
    "deepseek-coder-v2:latest",
    "deepseek-r1:14b",
    "qwen2.5:3b",
)


def _assert_loopback(base_url: str) -> str:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if host not in _LOOPBACK_HOSTS:
        raise PermissionError(f"Ollama 桥接器仅允许访问本机回环地址，已拒绝: {base_url}")
    return base_url.rstrip("/")


def list_ollama_models(
    base_url: str = "http://127.0.0.1:11434",
    *,
    timeout_sec: float = 1.5,
) -> list[dict[str, Any]]:
    """探测本机已启动的 Ollama 服务并返回可用对话/编码模型列表（自动过滤纯向量嵌入模型）。"""
    root = _assert_loopback(base_url)
    req = urllib.request.Request(f"{root}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []

    out: list[dict[str, Any]] = []
    for item in data.get("models") or []:
        name = str(item.get("name") or "").strip()
        if not name or "embed" in name.lower():
            continue
        size_gb = round(float(item.get("size") or 0) / 1e9, 2)
        out.append({"name": name, "size_gb": size_gb})
    return out


def pick_best_local_model(models: list[dict[str, Any]]) -> str | None:
    """从本机已装模型中挑选最适合 12GB 显存流畅响应的主力模型。"""
    if not models:
        return None
    available = {m["name"]: m["name"] for m in models}
    for pref in _PREFERRED_MODELS:
        if pref in available:
            return pref
    # 其次优先含 coder 或 qwen 的模型
    for m in models:
        if "coder" in m["name"].lower() or "qwen" in m["name"].lower():
            return m["name"]
    return models[0]["name"]


def make_ollama_infer_fn(
    model_getter: Callable[[], str | None],
    *,
    base_url: str = "http://127.0.0.1:11434",
    timeout_sec: float = 180.0,
    num_ctx: int = 8192,
) -> Callable[[list[dict[str, str]]], str]:
    """生成可直接注入 SemanticCoCreatorWorker / ReActWorker / CodeActWorker 的本地推理函数。"""
    root = _assert_loopback(base_url)

    def _infer(messages: list[dict[str, str]]) -> str:
        model = model_getter()
        if not model:
            raise RuntimeError("未检测到可用的本机 Ollama 模型，请确认 `ollama serve` 已运行。")
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "num_ctx": num_ctx,
                "temperature": 0.25,
            },
        }
        req = urllib.request.Request(
            f"{root}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
        msg = body.get("message") or {}
        return str(msg.get("content") or "")

    return _infer
