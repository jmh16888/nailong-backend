"""文本生成任务层：GLM-4-Flash 写分镜剧本"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field, ValidationError, field_validator

from ..prompts import STORY_SYSTEM, story_prompt
from ..schemas.video import Scene
from . import zhipu

log = logging.getLogger(__name__)


class _SceneRaw(BaseModel):
    photo_index: int
    narration: str
    camera_motion: str = "zoom_in"
    avatar_action: str = "walk_across"
    duration_sec: float = Field(3.0, ge=1.0, le=15.0)


def write_story(descriptions: list[str], theme: str, sec_per_scene: float) -> list[Scene]:
    """把 N 段照片描述串成分镜剧本，返回与照片一一对应的 Scene 列表"""
    raw = zhipu.chat_text(story_prompt(descriptions, theme, sec_per_scene), system=STORY_SYSTEM)
    try:
        items = zhipu.extract_json(raw)
        if isinstance(items, dict):  # 模型有时会包一层 {"scenes": [...]}
            items = next(iter(items.values()))
        scenes_raw = [_SceneRaw.model_validate(it) for it in items]
    except (zhipu.ZhipuError, ValidationError, TypeError, StopIteration) as e:
        log.warning("剧本解析失败(%s)，回喂修复一次", e)
        fixed = zhipu.chat_text(
            f"把下面内容修正为合法 JSON 数组（只输出 JSON）：\n{raw[:2000]}", system=STORY_SYSTEM
        )
        items = zhipu.extract_json(fixed)
        if isinstance(items, dict):
            items = next(iter(items.values()))
        scenes_raw = [_SceneRaw.model_validate(it) for it in items]

    # 对齐照片顺序：以 photo_index 归位，缺幕补默认、多幕截断
    by_index = {s.photo_index: s for s in scenes_raw}
    scenes: list[Scene] = []
    for i in range(len(descriptions)):
        s = by_index.get(i)
        if s is None:
            log.warning("第 %d 幕缺失，使用默认旁白", i)
            s = _SceneRaw(photo_index=i, narration="主角继续它的奇妙历险！")
        scenes.append(Scene(
            photo_id="",  # 由调用方回填 photo_id
            narration=s.narration[:80],
            camera_motion=s.camera_motion,   # pydantic 会校验枚举，非法值抛错
            avatar_action=s.avatar_action,
            duration_sec=max(1.5, min(10.0, s.duration_sec)),
        ))
    return scenes
