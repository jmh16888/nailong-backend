"""奶龙形象：分析 / 合成 / 换装 / 衣橱（真实实现）

pipeline：MediaPipe 人脸分析 → GLM-4V-Flash 特征提取（失败降级默认特征）
          → 纸娃娃图层合成（程序化素材，可用 assets/nailong/ 下的 PNG 覆盖）
"""
from fastapi import APIRouter, File, HTTPException, UploadFile

from ...config import settings
from ...schemas.avatar import (
    Accessory, AgeGroup, AvatarAnalyzeResponse, AvatarComposeResponse, ComposeRequest,
    Expression, FaceFeatures, FaceShape, GenderStyle, Glasses, HairColor, HairStyle,
    MediapipeSignals, Outfit, OutfitChangeRequest, OutfitChangeResponse, SkinTone,
    WardrobeCategory, WardrobeItem, WardrobeResponse,
)
from ...schemas.common import ImageRef
from ...services import avatar_compose, face, image_gen, store, vlm

router = APIRouter()

_CN = {
    HairStyle: {"bald": "光头", "buzz": "板寸", "short": "短发", "medium": "及肩发",
                "long_straight": "黑长直", "long_curly": "长卷发", "ponytail": "马尾",
                "twin_tails": "双马尾", "bun": "丸子头"},
    HairColor: {"black": "黑色", "brown": "棕色", "blonde": "金色",
                "gray_white": "灰白", "colorful": "彩色"},
    Glasses: {"none": "无", "round": "圆框", "square": "方框", "sunglasses": "墨镜"},
    Outfit: {"none": "奶龙本体", "tshirt": "T恤", "hoodie": "卫衣",
             "dress": "连衣裙", "suit": "西装", "cape": "披风"},
    Accessory: {"none": "无", "hat": "帽子", "headband": "发箍", "bow": "蝴蝶结", "scarf": "围巾"},
    Expression: {"happy": "开心", "neutral": "平静", "surprised": "惊讶", "cool": "酷", "shy": "害羞"},
}


def _default_features(note: str) -> FaceFeatures:
    return FaceFeatures(
        gender_style=GenderStyle.neutral, age_group=AgeGroup.young_adult,
        face_shape=FaceShape.oval, hair_style=HairStyle.short, hair_color=HairColor.black,
        glasses=Glasses.none, expression=Expression.happy, skin_tone=SkinTone.light,
        accessories=[], notes=note,
    )


def _features_path(avatar_id: str):
    return store.output_dir("avatars") / f"{avatar_id}.json"


def _image_path(avatar_id: str):
    return store.output_dir("avatars") / f"{avatar_id}.png"


@router.post("/avatars/analyze", response_model=AvatarAnalyzeResponse,
             summary="上传照片，输出结构化五官特征")
async def analyze_avatar(file: UploadFile = File(...)) -> AvatarAnalyzeResponse:
    data = await file.read()
    if not data:
        raise HTTPException(400, "空文件")

    # 1. MediaPipe 人脸关键点 + 量化信号（本地 CPU）
    try:
        face_bytes, signals = face.analyze_face(data)
    except ImportError:
        raise HTTPException(500, "mediapipe 未安装，请先 pip install mediapipe")

    # 2. GLM-4V-Flash 语义特征（失败降级默认特征，不阻塞流程）
    try:
        features = vlm.analyze_portrait(face_bytes)
        features = face.refine_features(features, signals)
    except Exception as e:
        features = _default_features(f"VLM 分析失败({type(e).__name__})，已使用默认特征")

    # 3. 落盘：人脸裁剪图 + 特征 JSON（换装/合成时引用）
    avatar_id = store.new_id()
    face_path = store.output_dir("faces") / f"{avatar_id}.jpg"
    face_path.write_bytes(face_bytes)
    store.save_json(_features_path(avatar_id), features)

    return AvatarAnalyzeResponse(
        avatar_id=avatar_id,
        face_crop=ImageRef(id=avatar_id, url=store.url_of(face_path)),
        features=features,
        signals=signals,
    )


@router.post("/avatars/compose", response_model=AvatarComposeResponse,
             summary="特征 JSON → 奶龙形象 PNG（纸娃娃合成）")
def compose_avatar(req: ComposeRequest) -> AvatarComposeResponse:
    img, layers = avatar_compose.compose_avatar(req.features)
    avatar_id = req.avatar_id or store.new_id()

    png_path = _image_path(avatar_id)
    img.save(png_path)
    store.save_json(_features_path(avatar_id), req.features)  # 特征与形象同步

    fancy_ref = None
    if req.with_fancy:
        fancy_bytes = image_gen.fancy_avatar(req.features)
        if fancy_bytes:
            fancy_path = store.output_dir("avatars") / f"{avatar_id}_fancy.png"
            fancy_path.write_bytes(fancy_bytes)
            fancy_ref = ImageRef(id=f"{avatar_id}_fancy", url=store.url_of(fancy_path))

    return AvatarComposeResponse(
        avatar_id=avatar_id,
        image=ImageRef(id=avatar_id, url=store.url_of(png_path)),
        layers=layers,
        fancy_image=fancy_ref,
    )


@router.put("/avatars/{avatar_id}/outfit", response_model=OutfitChangeResponse,
            summary="换装/换发型/换表情（只传要改的槽位）")
def change_outfit(avatar_id: str, req: OutfitChangeRequest) -> OutfitChangeResponse:
    fp = _features_path(avatar_id)
    if not fp.exists():
        raise HTTPException(404, f"形象不存在: {avatar_id}（先 analyze 或 compose）")
    features = FaceFeatures(**store.load_json(fp))

    # 合并换装请求（accessory 为单槽替换）
    for field in ("hair_style", "hair_color", "glasses", "outfit", "expression"):
        value = getattr(req, field)
        if value is not None:
            setattr(features, field, value)
    if req.accessory is not None:
        features.accessories = [] if req.accessory == Accessory.none else [req.accessory]

    img, layers = avatar_compose.compose_avatar(features)
    img.save(_image_path(avatar_id))
    store.save_json(fp, features)

    return OutfitChangeResponse(
        avatar_id=avatar_id,
        image=ImageRef(id=avatar_id, url=store.url_of(_image_path(avatar_id))),
        layers=layers,
        features=features,
    )


@router.get("/assets/wardrobe", response_model=WardrobeResponse,
            summary="可换装部件清单（前端换装界面用）")
def get_wardrobe() -> WardrobeResponse:
    slots = {
        "hair_style": HairStyle, "hair_color": HairColor, "glasses": Glasses,
        "outfit": Outfit, "accessory": Accessory, "expression": Expression,
    }
    categories = []
    for slot, enum_cls in slots.items():
        items = []
        for e in enum_cls:
            # 有文件素材的部件给出预览图（/assets 静态挂载）
            preview = None
            if slot in ("glasses", "outfit", "accessory"):
                p = settings.assets_dir / "nailong" / slot / f"{e.value}.png"
                if p.exists():
                    preview = ImageRef(id=e.value, url=f"/assets/nailong/{slot}/{e.value}.png")
            items.append(WardrobeItem(id=e.value, name=_CN.get(enum_cls, {}).get(e.value, e.value),
                                      preview=preview))
        categories.append(WardrobeCategory(slot=slot, items=items))
    return WardrobeResponse(categories=categories)
