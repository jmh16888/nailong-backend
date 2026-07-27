"""背景卡通化（真实实现）：AnimeGANv2 / OpenCV + GLM-4V-Flash 场景分析"""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ...schemas.background import CartoonizeResponse, CartoonStyle, SceneTags, SceneType, TimeOfDay
from ...schemas.common import ImageRef
from ...services import cartoon, store, vlm

router = APIRouter()


def _default_scene() -> SceneTags:
    return SceneTags(
        scene_type=SceneType.other, indoor=False, time_of_day=TimeOfDay.day,
        main_elements=["未知场景"], color_tone="暖色",
        suggested_theme="奶龙大冒险", obstacle_hints=["石头", "树桩"],
    )


@router.post("/backgrounds/cartoonize", response_model=CartoonizeResponse,
             summary="照片 → 卡通背景 + 场景标签")
async def cartoonize(
    file: UploadFile = File(...),
    style: CartoonStyle = Form(CartoonStyle.paprika, description="卡通画风"),
) -> CartoonizeResponse:
    data = await file.read()
    if not data:
        raise HTTPException(400, "空文件")

    # 1. 卡通化（AnimeGANv2，失败自动回退 OpenCV，不抛错）
    png_bytes = cartoon.cartoonize(data, style)

    # 2. GLM-4V-Flash 场景分析（用原图，失败降级默认标签）
    try:
        scene = vlm.analyze_scene(data)
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
