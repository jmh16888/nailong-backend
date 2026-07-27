"""奶龙形象模块契约。

核心：FaceFeatures —— MediaPipe 量化特征 + GLM-4V-Flash 语义特征融合后的
结构化五官特征 JSON。所有字段取枚举值，保证能一一映射到素材库图层，
也是 GLM-4V-Flash prompt 中限定输出范围的依据。
"""
from enum import Enum

from pydantic import BaseModel, Field

from .common import ImageRef


# ---------- 枚举：与素材库图层一一对应，前后端 + prompt 共用一套词汇 ----------

class GenderStyle(str, Enum):
    """整体形象风格倾向（不做真实性别判定，仅用于卡通形象设计）"""
    boy = "boy"
    girl = "girl"
    neutral = "neutral"


class AgeGroup(str, Enum):
    child = "child"
    teen = "teen"
    young_adult = "young_adult"
    middle_aged = "middle_aged"
    senior = "senior"


class FaceShape(str, Enum):
    round = "round"
    oval = "oval"
    square = "square"
    long = "long"
    heart = "heart"


class HairStyle(str, Enum):
    bald = "bald"            # 光头/板寸以下
    buzz = "buzz"            # 板寸
    short = "short"          # 短发
    medium = "medium"        # 及肩中发
    long_straight = "long_straight"
    long_curly = "long_curly"
    ponytail = "ponytail"    # 马尾
    twin_tails = "twin_tails"  # 双马尾
    bun = "bun"              # 丸子头/盘发


class HairColor(str, Enum):
    black = "black"
    brown = "brown"
    blonde = "blonde"
    gray_white = "gray_white"
    colorful = "colorful"    # 明显染色（粉/蓝/紫等）


class Glasses(str, Enum):
    none = "none"
    round = "round"
    square = "square"
    sunglasses = "sunglasses"


class Expression(str, Enum):
    happy = "happy"
    neutral = "neutral"
    surprised = "surprised"
    cool = "cool"
    shy = "shy"


class SkinTone(str, Enum):
    fair = "fair"
    light = "light"
    medium = "medium"
    tan = "tan"
    dark = "dark"


class Outfit(str, Enum):
    none = "none"        # 奶龙本体（不穿衣服）
    tshirt = "tshirt"
    hoodie = "hoodie"
    dress = "dress"
    suit = "suit"
    cape = "cape"        # 披风（历险记主角感）


class Accessory(str, Enum):
    none = "none"
    hat = "hat"
    headband = "headband"
    bow = "bow"          # 蝴蝶结
    scarf = "scarf"


# ---------- 特征 JSON（核心契约） ----------

class FaceFeatures(BaseModel):
    """结构化形象档案：VLM 预测的五官特征 + 用户穿搭（outfit 槽位）。
    字段全部为枚举，保证可映射到素材库图层。"""
    gender_style: GenderStyle
    age_group: AgeGroup
    face_shape: FaceShape
    hair_style: HairStyle
    hair_color: HairColor
    glasses: Glasses = Glasses.none
    expression: Expression = Expression.happy
    skin_tone: SkinTone = SkinTone.light
    accessories: list[Accessory] = Field(default_factory=list)
    outfit: Outfit = Field(Outfit.none, description="穿搭槽位（VLM 不预测，compose/outfit 阶段设置）")
    notes: str = Field("", description="VLM 自由文本补充（不进规则引擎，供剧本/展示用）")


class MediapipeSignals(BaseModel):
    """本地 MediaPipe 可解释量化信号（报告亮点，前端可不展示）"""
    face_detected: bool
    smile_score: float = Field(..., ge=0, le=1, description="mouthSmile blendshape 强度")
    eye_open_ratio: float = Field(..., ge=0, le=1, description="眼睛睁开程度")
    face_width_height_ratio: float = Field(..., description="脸宽/脸长，辅助脸型判断")


class AvatarAnalyzeResponse(BaseModel):
    avatar_id: str = Field(..., description="形象 ID，后续 compose/outfit/游戏/视频都用它")
    face_crop: ImageRef = Field(..., description="裁剪出的人脸图")
    features: FaceFeatures
    signals: MediapipeSignals


# ---------- 合成 / 换装 / 衣橱 ----------

class ComposeRequest(BaseModel):
    features: FaceFeatures
    avatar_id: str | None = Field(
        None, description="传入 analyze 返回的 avatar_id 则形象图挂在同一记录下（换装/游戏/视频可引用）"
    )
    with_fancy: bool = Field(
        False,
        description="是否额外调 CogView-3-Flash 生成精致手绘版彩蛋（慢，10~30s，可失败降级）",
    )


class AvatarComposeResponse(BaseModel):
    avatar_id: str
    image: ImageRef = Field(..., description="纸娃娃合成的奶龙形象 PNG（透明底）")
    layers: list[str] = Field(..., description="实际使用的图层 asset 相对路径，供调试/换装界面")
    fancy_image: ImageRef | None = Field(None, description="精致手绘版（with_fancy=True 时返回）")


class OutfitChangeRequest(BaseModel):
    """换装请求：只传要更换的槽位，未传的保持原样"""
    hair_style: HairStyle | None = None
    hair_color: HairColor | None = None
    glasses: Glasses | None = None
    outfit: Outfit | None = None
    accessory: Accessory | None = None
    expression: Expression | None = None


class OutfitChangeResponse(BaseModel):
    avatar_id: str
    image: ImageRef
    layers: list[str]
    features: FaceFeatures = Field(..., description="换装合并后的完整特征")


class WardrobeItem(BaseModel):
    id: str = Field(..., description="部件 ID，即对应枚举值")
    name: str = Field(..., description="中文展示名，如 '双马尾'")
    preview: ImageRef | None = Field(None, description="部件预览图（可选）")


class WardrobeCategory(BaseModel):
    slot: str = Field(..., description="槽位：hair_style/hair_color/glasses/outfit/accessory/expression")
    items: list[WardrobeItem]


class WardrobeResponse(BaseModel):
    categories: list[WardrobeCategory]
