"""游戏模块契约：素材包 + 关卡配置 + 免登录排行榜"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .common import ImageRef


class Difficulty(str, Enum):
    easy = "easy"
    normal = "normal"
    hard = "hard"


class GamePackageRequest(BaseModel):
    avatar_id: str = Field(..., description="奶龙形象 ID（/avatars/analyze 或 /compose 返回）")
    background_id: str = Field(..., description="卡通背景 ID（/backgrounds/cartoonize 返回）")
    difficulty: Difficulty = Difficulty.normal
    duration_sec: int = Field(60, ge=30, le=300, description="一局时长（秒）")
    heart_count: int = Field(3, ge=1, le=9, description="爱心（生命）数量")
    coin_count: int = Field(20, ge=0, le=200, description="金币投放数量")


class GameConfig(BaseModel):
    """关卡配置：前端游戏引擎（Canvas/Phaser）直接消费的物理与数值参数"""
    difficulty: Difficulty
    duration_sec: int
    heart_count: int
    coin_count: int
    gravity: float = Field(..., description="重力加速度，像素/秒²")
    move_speed: float = Field(..., description="角色水平移动速度，像素/秒")
    jump_velocity: float = Field(..., description="起跳初速度，像素/秒")
    obstacle_speed: float = Field(..., description="障碍物移动速度，像素/秒")
    obstacle_interval_min: float = Field(..., description="障碍物刷新最小间隔（秒）")
    obstacle_interval_max: float = Field(..., description="障碍物刷新最大间隔（秒）")


class SpriteInfo(BaseModel):
    name: str
    image: ImageRef
    width: int = Field(..., description="像素宽，前端碰撞盒参考")
    height: int = Field(..., description="像素高")


class CharacterSprite(BaseModel):
    run_frames: list[ImageRef] = Field(..., min_length=1, description="跑步帧序列")
    jump_frame: ImageRef = Field(..., description="跳跃帧")


class GamePackageResponse(BaseModel):
    game_id: str
    background: ImageRef
    character: CharacterSprite
    obstacles: list[SpriteInfo] = Field(..., description="按场景标签挑选的障碍物精灵")
    coin_sprite: SpriteInfo
    config: GameConfig


# ---------- 排行榜（免登录极简版） ----------

class ScoreSubmit(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=16)
    score: int = Field(..., ge=0)
    difficulty: Difficulty = Difficulty.normal
    game_id: str | None = None


class LeaderboardEntry(BaseModel):
    rank: int
    nickname: str
    score: int
    difficulty: Difficulty
    created_at: datetime


class LeaderboardResponse(BaseModel):
    entries: list[LeaderboardEntry]
