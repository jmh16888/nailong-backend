"""照片上传（真实实现，非 mock）：所有功能的入口"""
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from ...config import settings
from ...schemas import UploadResponse

router = APIRouter()

ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/bmp"}


@router.post("/uploads", response_model=UploadResponse, summary="上传照片")
async def upload_photo(file: UploadFile = File(...)) -> UploadResponse:
    if file.content_type not in ALLOWED:
        raise HTTPException(400, f"不支持的图片类型: {file.content_type}")

    photo_id = uuid.uuid4().hex[:12]
    suffix = ".jpg" if file.content_type == "image/jpeg" else f".{file.content_type.split('/')[1]}"
    path = settings.storage_dir / "uploads" / f"{photo_id}{suffix}"
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(400, "图片超过 20MB 限制")
    path.write_bytes(content)

    # 读尺寸（Pillow 未装时退化为 0，mock 阶段可容忍）
    width = height = 0
    try:
        from PIL import Image
        with Image.open(path) as im:
            width, height = im.size
    except ImportError:
        pass

    return UploadResponse(
        photo_id=photo_id,
        url=f"/static/uploads/{photo_id}{suffix}",
        width=width,
        height=height,
    )
