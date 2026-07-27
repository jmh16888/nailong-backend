"""智谱开放平台统一客户端：GLM-4V-Flash / GLM-4-Flash / CogView-3-Flash（均为免费模型）。

- OpenAI 兼容接口，base_url 见 config
- 全局并发信号量限流（免费模型有并发限制）+ tenacity 指数退避重试
- extract_json 容错解析模型输出的 JSON
"""
from __future__ import annotations

import base64
import json
import re
import threading

import httpx
from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import settings


class ZhipuError(RuntimeError):
    """智谱 API 调用失败（未配置 key / 网络错误 / 重试耗尽）"""


_client: OpenAI | None = None
_client_lock = threading.Lock()
_sem = threading.Semaphore(settings.api_concurrency)


def get_client() -> OpenAI:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                if not settings.zhipu_api_key:
                    raise ZhipuError("未配置智谱 API Key：请在 .env 中设置 NAILONG_ZHIPU_API_KEY")
                _client = OpenAI(
                    api_key=settings.zhipu_api_key,
                    base_url=settings.zhipu_base_url,
                    timeout=httpx.Timeout(120.0, connect=15.0),
                )
    return _client


_RETRY = dict(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)


@retry(**_RETRY)
def chat_text(prompt: str, system: str | None = None, model: str | None = None,
              temperature: float = 0.3) -> str:
    """纯文本对话（GLM-4-Flash）"""
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    with _sem:
        resp = get_client().chat.completions.create(
            model=model or settings.llm_model, messages=messages, temperature=temperature,
        )
    return resp.choices[0].message.content or ""


@retry(**_RETRY)
def chat_with_image(prompt: str, image_bytes: bytes, system: str | None = None,
                    model: str | None = None, temperature: float = 0.2) -> str:
    """图文对话（GLM-4V-Flash），图片走 base64"""
    b64 = base64.b64encode(image_bytes).decode()
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ]},
    ]
    with _sem:
        resp = get_client().chat.completions.create(
            model=model or settings.vlm_model, messages=messages, temperature=temperature,
        )
    return resp.choices[0].message.content or ""


@retry(**_RETRY)
def gen_image(prompt: str, size: str = "1024x1024") -> bytes:
    """文生图（CogView-3-Flash），返回图片字节"""
    with _sem:
        resp = get_client().images.generate(
            model=settings.image_gen_model, prompt=prompt, size=size,
        )
    url = resp.data[0].url
    with _sem:
        r = httpx.get(url, timeout=120.0, follow_redirects=True)
        r.raise_for_status()
    return r.content


# ---------- JSON 容错解析 ----------

_JSON_OBJ = re.compile(r"\{.*\}", re.S)
_JSON_ARR = re.compile(r"\[.*\]", re.S)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> dict | list:
    """从模型输出中提取 JSON：优先 ```json 代码块，其次首个 {...} / [...] 块"""
    text = text.strip()
    m = _FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    for pattern in (_JSON_OBJ, _JSON_ARR):
        m = pattern.search(text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    raise ZhipuError(f"模型输出中未找到合法 JSON: {text[:200]}...")
