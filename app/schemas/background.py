"""背景卡通化模块契约：卡通风格 + GLM-4V-Flash 场景标签（驱动游戏主题）"""
from enum import Enum

from pydantic import BaseModel, Field

from .common import ImageRef


class CartoonStyle(str, Enum):
    """AnimeGANv2 可选画风（对应 torch.hub bryandlee/animegan2-pytorch 的权重）"""
    paprika = "paprika"                  # 今敏《红辣椒》风：色彩浓郁，风景人像皆宜
    face_paint_v2 = "face_paint_v2"      # 肖像彩绘 v2：柔和明亮，人像更好看
    face_paint_v1 = "face_paint_v1"      # 肖像彩绘 v1：笔触更重
    celeba_distill = "celeba_distill"    # 人像精简风：轻量快速


class SceneType(str, Enum):
    indoor = "indoor"
    street = "street"
    forest = "forest"
    seaside = "seaside"
    mountain = "mountain"
    campus = "campus"
    sky = "sky"            # 天空/开阔户外
    other = "other"


class TimeOfDay(str, Enum):
    day = "day"
    dusk = "dusk"
    night = "night"


class SceneTags(BaseModel):
    """GLM-4V-Flash 场景分析结果：决定游戏主题皮肤与障碍物组合"""
    scene_type: SceneType
    indoor: bool
    time_of_day: TimeOfDay
    main_elements: list[str] = Field(..., description="画面主要元素，中文短语，如 ['教学楼','梧桐树','自行车']")
    color_tone: str = Field(..., description="主色调描述，如 '暖黄' / '冷蓝'")
    suggested_theme: str = Field(..., description="建议游戏主题名，如 '森林大冒险'")
    obstacle_hints: list[str] = Field(..., description="建议障碍物元素，如 ['树桩','岩石']")


class CartoonizeResponse(BaseModel):
    background_id: str
    image: ImageRef = Field(..., description="卡通化后的背景图")
    scene: SceneTags
