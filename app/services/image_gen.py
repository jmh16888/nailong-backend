"""文生图任务层：CogView-3-Flash（免费）。

- cogview_avatar：主展示形象图。GLM-4V 提取特征+notes → GLM-4 扩成外貌描述
  → 我用写死的 Q版卡通风前后缀包住 → CogView 生成 → 经 rembg 抠透明。
  （Q版风格写死保证，不靠 GLM-4 自觉，避免出写实图。）
- cogview_background：背景图。用户/描述文本 prompt → CogView 重画（不透明）。
- cogview_sprite：游戏障碍/金币精灵底图（经 rembg 抠透明）。

所有调用 zhipu（tenacity 重试）；任一失败静默返回 None，由调用方报错
（已删全部硬编码兜底，不再回退纸娃娃/AnimeGAN/_draw_sprite）。
"""
from __future__ import annotations

import io
import logging

from PIL import Image

from ..prompts import (
    AVATAR_PROMPT_BUILDER_SYSTEM,
    avatar_prompt_builder_prompt,
    sprite_prompt,
)
from ..schemas.avatar import FaceFeatures
from . import zhipu

log = logging.getLogger(__name__)


def _valid_image_bytes(b: bytes) -> bool:
    """校验 CogView 返回的字节能解码且尺寸合理（非空、非缩略）。"""
    if not b:
        return False
    try:
        with Image.open(io.BytesIO(b)) as im:
            im.verify()
        im = Image.open(io.BytesIO(b))
        w, h = im.size
        return w >= 64 and h >= 64
    except Exception:
        return False


def _clean_prompt(s: str) -> str:
    """去 GLM-4 输出首尾空白/引号。"""
    return (s or "").strip().strip('"').strip("'").strip()


def cogview_avatar(features: FaceFeatures) -> bytes | None:
    """主展示形象图：GLM-4 出外貌描述 → 写死 Q版卡通风前后缀包住 → CogView（不透明底图，交 bg_remove 抠透明）。

    失败返回 None（调用方报错，无纸娃娃兜底）。
    """
    try:
        desc = _clean_prompt(zhipu.chat_text(
            avatar_prompt_builder_prompt(features), system=AVATAR_PROMPT_BUILDER_SYSTEM,
        ))
        if not desc:
            log.warning("GLM-4 未返回有效外貌描述，用默认")
            desc = "一个可爱的卡通人物"
        # Q版风格写死在前后缀，保证 CogView 出 Q版卡通（不靠 GLM-4 自觉）
        prompt = (f"Q版卡通人物形象，大头小身比例，可爱Q版卡通风，{desc}，"
                  f"纯色浅色背景，全身像，居中构图，明亮柔和配色，高清，无文字无水印")
        log.info("avatar cogview prompt: %s", prompt)
        b = zhipu.gen_image(prompt)
        return b if _valid_image_bytes(b) else None
    except Exception as e:
        log.warning("CogView 形象生成失败，已跳过: %s", e)
        return None


def cogview_background(prompt: str) -> bytes | None:
    """背景图：用户/描述文本 prompt → CogView 重画（不透明）；失败返回 None。"""
    try:
        text = (prompt or "").strip() or "一处有趣的场景"
        full = (f"{text}，Q版卡通风格，横版2D游戏背景插画，"
                f"无人物主体，明亮柔和配色，高清，无文字无水印")
        b = zhipu.gen_image(full)
        return b if _valid_image_bytes(b) else None
    except Exception as e:
        log.warning("CogView 背景生成失败，已跳过: %s", e)
        return None


def cogview_sprite(kind: str) -> bytes | None:
    """游戏障碍/金币精灵底图（不透明，交 bg_remove 抠透明）；失败返回 None。"""
    try:
        b = zhipu.gen_image(sprite_prompt(kind))
        return b if _valid_image_bytes(b) else None
    except Exception as e:
        log.warning("CogView 精灵生成失败(%s)，已跳过: %s", kind, e)
        return None
