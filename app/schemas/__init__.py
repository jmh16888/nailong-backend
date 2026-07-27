"""接口契约（前后端共用词汇表，v1 已冻结）"""
from .common import ApiResponse, ImageRef, UploadResponse
from .avatar import (
    Accessory, AgeGroup, AvatarAnalyzeResponse, AvatarComposeResponse,
    ComposeRequest, Expression, FaceFeatures, FaceShape, GenderStyle, Glasses,
    HairColor, HairStyle, MediapipeSignals, Outfit, OutfitChangeRequest,
    OutfitChangeResponse, SkinTone, WardrobeCategory, WardrobeItem, WardrobeResponse,
)
from .background import CartoonizeResponse, CartoonStyle, SceneTags, SceneType, TimeOfDay
from .game import (
    CharacterSprite, Difficulty, GameConfig, GamePackageRequest, GamePackageResponse,
    LeaderboardEntry, LeaderboardResponse, ScoreSubmit, SpriteInfo,
)
from .video import (
    AvatarAction, CameraMotion, JobStatus, Scene, TransitionStyle,
    VideoGenerateRequest, VideoJobResponse,
)

__all__ = [name for name in dir() if not name.startswith("_")]
