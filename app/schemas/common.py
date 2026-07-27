"""通用模型：统一响应包装、图片资源引用"""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应包装（错误时 http 状态码也会非 200，这里主要承载业务错误）"""
    code: int = Field(0, description="0=成功，非 0 为业务错误码")
    message: str = Field("ok", description="错误描述，成功时为 ok")
    data: T | None = Field(None, description="业务数据")


class ImageRef(BaseModel):
    """一个可访问的图片资源"""
    id: str = Field(..., description="资源 ID")
    url: str = Field(..., description="相对 URL（/static/...），前端拼 base 即可")


class UploadResponse(BaseModel):
    photo_id: str = Field(..., description="照片 ID，后续接口（视频生成等）用它引用")
    url: str = Field(..., description="图片访问 URL")
    width: int
    height: int
