"""文生图任务层：CogView-3-Flash（免费），用于可选"精致手绘版"形象彩蛋"""
from __future__ import annotations

import logging

from ..prompts import fancy_avatar_prompt
from ..schemas.avatar import FaceFeatures
from . import zhipu

log = logging.getLogger(__name__)


def fancy_avatar(features: FaceFeatures) -> bytes | None:
    """按特征 JSON 生成精致手绘版奶龙形象；失败返回 None（不影响主流程）"""
    try:
        return zhipu.gen_image(fancy_avatar_prompt(features))
    except Exception as e:  # 彩蛋环节，任何失败都静默降级
        log.warning("CogView 精致版生成失败，已跳过: %s", e)
        return None
