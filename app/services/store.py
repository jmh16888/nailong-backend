"""存储助手：统一的资源 ID、路径与 JSON sidecar 管理

目录约定（config.storage_dir 下）：
  uploads/{photo_id}.{ext}                     上传原图
  outputs/avatars/{avatar_id}.png/.json        卡通形象 + 特征
  outputs/faces/{avatar_id}.jpg                人脸裁剪图
  outputs/backgrounds/{background_id}.png/.json 卡通背景 + 场景标签
  outputs/games/{game_id}/...                  游戏素材包
  outputs/videos/{job_id}.mp4                  成片
  outputs/videos/jobs/{job_id}.json            视频任务状态
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from ..config import settings


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def uploads_dir() -> Path:
    return settings.storage_dir / "uploads"


def output_dir(kind: str) -> Path:
    p = settings.storage_dir / "outputs" / kind
    p.mkdir(parents=True, exist_ok=True)
    return p


def find_upload(photo_id: str) -> Path | None:
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        p = uploads_dir() / f"{photo_id}{ext}"
        if p.exists():
            return p
    return None


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def url_of(path: Path) -> str:
    """磁盘路径 → /static 相对 URL"""
    rel = path.relative_to(settings.storage_dir)
    return f"/static/{rel.as_posix()}"
