"""背景生成（真实实现）：CogView-3-Flash 按 prompt 生图 + GLM-4-Flash 场景标签"""
from fastapi import APIRouter, HTTPException

from ...schemas.background import (
    BackgroundPromptRequest, CartoonizeResponse, SceneTags, SceneType, TimeOfDay,
)
from ...schemas.common import ImageRef
from ...services import image_gen, store, vlm

router = APIRouter()


def _default_scene() -> SceneTags:
    return SceneTags(
        scene_type=SceneType.other, indoor=False, time_of_day=TimeOfDay.day,
        main_elements=["未知场景"], color_tone="暖色",
        suggested_theme="卡通大冒险", obstacle_hints=["石头", "树桩"],
    )


@router.post("/backgrounds/cartoonize", response_model=CartoonizeResponse,
             summary="文本 prompt → 卡通背景 + 场景标签（CogView 生图）")
def cartoonize(req: BackgroundPromptRequest) -> CartoonizeResponse:
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(400, "prompt 不能为空")

    # 1. CogView 生背景（失败直接报错，无 AnimeGAN 兜底）
    png_bytes = image_gen.cogview_background(prompt)
    if not png_bytes:
        raise HTTPException(502, "背景生成失败：CogView 未返回有效结果")

    # 2. GLM-4 从 prompt 文本提取场景标签（供游戏挑障碍物；失败降级默认）
    try:
        scene = vlm.analyze_scene_from_text(prompt)
    except Exception:
        scene = _default_scene()

    # 3. 落盘
    bg_id = store.new_id()
    png_path = store.output_dir("backgrounds") / f"{bg_id}.png"
    png_path.write_bytes(png_bytes)
    store.save_json(png_path.with_suffix(".json"), scene)

    return CartoonizeResponse(
        background_id=bg_id,
        image=ImageRef(id=bg_id, url=store.url_of(png_path)),
        scene=scene,
    )
