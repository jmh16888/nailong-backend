"""动画视频模块契约：分镜剧本（GLM-4-Flash 生成）+ 异步任务状态"""
from enum import Enum

from pydantic import BaseModel, Field

from .common import ImageRef


class TransitionStyle(str, Enum):
    fade = "fade"      # 淡入淡出
    slide = "slide"    # 滑动
    none = "none"      # 硬切


class CameraMotion(str, Enum):
    """Ken Burns 运镜方式"""
    zoom_in = "zoom_in"
    zoom_out = "zoom_out"
    pan_left = "pan_left"
    pan_right = "pan_right"
    static = "static"


class AvatarAction(str, Enum):
    """奶龙形象在该幕的动作"""
    walk_across = "walk_across"   # 从画面一侧走到另一侧
    bounce = "bounce"             # 原地弹跳
    peek_corner = "peek_corner"   # 从角落探出
    none = "none"


class Scene(BaseModel):
    """分镜剧本中的一幕（GLM-4-Flash 根据照片描述串烧生成）"""
    photo_id: str
    narration: str = Field(..., description="旁白文案，1~2 句，奶龙口吻")
    camera_motion: CameraMotion = CameraMotion.zoom_in
    avatar_action: AvatarAction = AvatarAction.walk_across
    duration_sec: float = Field(3.0, ge=1.5, le=10)


class VideoGenerateRequest(BaseModel):
    photo_ids: list[str] = Field(..., min_length=1, max_length=10,
                                 description="已上传照片 ID（/uploads 返回），按顺序串成故事")
    avatar_id: str | None = Field(None, description="奶龙形象 ID，提供则出镜")
    theme: str = Field("卡通历险记", max_length=50, description="故事主题，影响剧本风格")
    with_narration: bool = Field(True, description="是否用 edge-tts 生成旁白配音")
    transition: TransitionStyle = TransitionStyle.fade
    sec_per_scene: float = Field(3.0, ge=1.5, le=10, description="默认每幕时长（秒）")


class JobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class VideoJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = Field(..., ge=0, le=1)
    stage: str = Field("", description="当前阶段：排队中/卡通化/照片描述/剧本生成/配音/渲染/完成")
    storyboard: list[Scene] | None = Field(None, description="分镜剧本（生成后可见，前端可预览）")
    video: ImageRef | None = Field(None, description="成片 mp4（status=done 时返回）")
    error: str | None = None
