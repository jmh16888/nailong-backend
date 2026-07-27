"""VLM 任务层：调 GLM-4V-Flash 完成人像/场景/照片描述，输出严格校验过的 pydantic 对象。

解析策略：extract_json → pydantic 校验 → 失败则把错误信息回喂模型"修正"一次 →
再失败抛 ZhipuError（由调用方决定降级策略）。
"""
from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..prompts import (
    PHOTO_DESC_PROMPT, PHOTO_DESC_SYSTEM, PORTRAIT_PROMPT, PORTRAIT_SYSTEM,
    SCENE_PROMPT, SCENE_SYSTEM,
)
from ..schemas.avatar import FaceFeatures
from ..schemas.background import SceneTags
from . import zhipu

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _validate_with_repair(raw: str, model_cls: type[T], image_bytes: bytes | None = None) -> T:
    """JSON 解析 + pydantic 校验，失败回喂修复一次"""
    try:
        return model_cls.model_validate(zhipu.extract_json(raw))
    except (zhipu.ZhipuError, ValidationError) as e:
        log.warning("首次解析失败(%s)，尝试回喂修复", e)
    fix_prompt = (
        f"下面这段输出不符合要求，请修正为合法的 JSON（只输出 JSON，不要解释）。\n"
        f"错误信息：{str(e)[:300]}\n\n原始输出：\n{raw[:1500]}"
    )
    if image_bytes is not None:
        fixed = zhipu.chat_with_image(fix_prompt, image_bytes)
    else:
        fixed = zhipu.chat_text(fix_prompt)
    return model_cls.model_validate(zhipu.extract_json(fixed))


def analyze_portrait(image_bytes: bytes) -> FaceFeatures:
    """五官特征分析（人脸裁剪图效果更佳）"""
    raw = zhipu.chat_with_image(PORTRAIT_PROMPT, image_bytes, system=PORTRAIT_SYSTEM)
    return _validate_with_repair(raw, FaceFeatures, image_bytes)


def analyze_scene(image_bytes: bytes) -> SceneTags:
    """场景分析：游戏主题 + 障碍物建议"""
    raw = zhipu.chat_with_image(SCENE_PROMPT, image_bytes, system=SCENE_SYSTEM)
    return _validate_with_repair(raw, SceneTags, image_bytes)


def describe_photo(image_bytes: bytes) -> str:
    """照片多维度描述 → 拼成一段中文给剧本层用"""
    raw = zhipu.chat_with_image(PHOTO_DESC_PROMPT, image_bytes, system=PHOTO_DESC_SYSTEM)

    class _Desc(BaseModel):
        summary: str = ""
        scene: str = ""
        subjects: str = ""
        atmosphere: str = ""
        highlight: str = ""

    d = _validate_with_repair(raw, _Desc, image_bytes)
    parts = [p for p in (d.summary, d.scene, d.subjects, d.atmosphere, d.highlight) if p]
    return "；".join(parts) or "一张有趣的照片"
