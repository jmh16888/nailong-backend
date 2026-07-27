"""背景卡通化：AnimeGANv2（GPU/CPU）+ OpenCV 纯算法兜底（零模型、零下载）。

AnimeGANv2 通过 torch.hub 加载 bryandlee/animegan2-pytorch（权重 ~15MB，首次运行
从 GitHub 下载并缓存到 ~/.cache/torch/hub；离线/下载失败时自动回退 OpenCV 方案）。
"""
from __future__ import annotations

import io
import logging

import cv2
import numpy as np
from PIL import Image

from ..config import settings
from ..schemas.background import CartoonStyle

log = logging.getLogger(__name__)

# 接口风格 → torch.hub 权重名
_HUB_WEIGHTS = {
    CartoonStyle.paprika: "paprika",
    CartoonStyle.face_paint_v2: "face_paint_512_v2",
    CartoonStyle.face_paint_v1: "face_paint_512_v1",
    CartoonStyle.celeba_distill: "celeba_distill",
}

_generators: dict[str, object] = {}
_device: str | None = None


def _get_generator(style: CartoonStyle):
    """加载（并缓存）AnimeGANv2 生成器；失败抛异常由 cartoonize 捕获降级"""
    global _device
    import torch  # 延迟导入

    if _device is None:
        _device = "cuda" if (settings.device == "cuda" and torch.cuda.is_available()) else "cpu"
    key = _HUB_WEIGHTS[style]
    if key not in _generators:
        log.info("加载 AnimeGANv2 权重 %s（device=%s），首次需下载 ~15MB", key, _device)
        _generators[key] = torch.hub.load(
            "bryandlee/animegan2-pytorch:main", "generator",
            pretrained=key, device=_device, progress=False,
        )
    return _generators[key]


def _animegan_cartoonize(img: Image.Image, style: CartoonStyle) -> Image.Image:
    import torch
    import torchvision.transforms.functional as TF

    model = _get_generator(style)
    # 限制最长边（显存友好），并取 8 的倍数（网络下采样要求）
    w, h = img.size
    scale = min(1.0, 768 / max(w, h))
    w8, h8 = max(8, int(w * scale) // 8 * 8), max(8, int(h * scale) // 8 * 8)
    x = TF.to_tensor(img.resize((w8, h8), Image.LANCZOS)) * 2 - 1  # → [-1, 1]
    with torch.no_grad():
        y = model(x.unsqueeze(0).to(_device))[0].cpu()
    y = (y * 0.5 + 0.5).clamp(0, 1)
    return TF.to_pil_image(y)


def _opencv_cartoonize(img: Image.Image) -> Image.Image:
    """零模型兜底：双边滤波保边平滑 + 颜色量化 + 边缘线叠加"""
    bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    smooth = bgr
    for _ in range(2):  # 两次双边滤波更"卡通"
        smooth = cv2.bilateralFilter(smooth, d=9, sigmaColor=90, sigmaSpace=90)
    # 颜色量化（每通道 24 级 → 8 档色阶）
    quant = (smooth // 32) * 32 + 16
    # 边缘线
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY, blockSize=9, C=3)
    cartoon = cv2.bitwise_and(quant, quant, mask=edges)
    return Image.fromarray(cv2.cvtColor(cartoon, cv2.COLOR_BGR2RGB))


def cartoonize(image_bytes: bytes, style: CartoonStyle) -> bytes:
    """照片 → 卡通图（PNG bytes）。AnimeGAN 失败自动回退 OpenCV，永不抛错。"""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    out: Image.Image
    try:
        out = _animegan_cartoonize(img, style)
    except Exception as e:
        log.warning("AnimeGANv2 不可用(%s: %s)，回退 OpenCV 卡通化", type(e).__name__, e)
        out = _opencv_cartoonize(img)
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def cartoonize_to_file(image_bytes: bytes, style: CartoonStyle, path) -> None:
    path.write_bytes(cartoonize(image_bytes, style))
