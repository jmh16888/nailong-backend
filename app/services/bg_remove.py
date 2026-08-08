"""抠图服务：rembg(u2net) 把 CogView 不透明底图切成透明 RGBA。

CogView-3-Flash 出的是不透明纯色背景全幅插画，而游戏精灵/角色跑跳帧/视频贴图
都要透明底。rembg 切出主体后，再做 alpha 边缘清理（阈值二值化 + 1px 收缩去背景色
残留）+ 自动取景居中（getbbox 裁剪 → 等比缩放 → 居中贴目标画布），保证角色在
画布中心、精灵大小合适（游戏碰撞盒/视频 resize 才准）。

rembg 未安装或任一步失败时返回 None，调用方报错 502（已移除所有兜底）。
"""
from __future__ import annotations

import io
import logging

from PIL import Image, ImageFilter

log = logging.getLogger(__name__)


def cutout(image_bytes: bytes) -> bytes | None:
    """不透明图 → 透明 PNG bytes。rembg 不可用/失败返回 None。"""
    try:
        from rembg import remove  # 延迟导入；首次会下 u2net 权重(~170MB)
    except ImportError as e:
        log.warning("rembg 未安装，抠图跳过: %s", e)
        return None
    try:
        out = remove(image_bytes)  # 返回 PNG bytes(RGBA，透明底)
        return out if out else None
    except Exception as e:
        log.warning("rembg 抠图失败: %s", e)
        return None


def cutout_to_canvas(image_bytes: bytes, size: int = 512,
                     threshold: int = 128) -> bytes | None:
    """不透明图 → 透明 PNG bytes，居中贴到 size×size 画布。

    流程：rembg 抠图 → alpha 阈值二值化去毛边 → 1px 收缩去背景色残留 →
    getbbox 裁非透明区 → 等比缩放至 size 的 92%（留边距）→ 居中贴透明画布。
    任一步失败返回 None。
    """
    raw = cutout(image_bytes)
    if raw is None:
        return None
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        # 1. alpha 边缘清理：阈值二值化去半透明毛边/光晕
        alpha = img.getchannel("A")
        alpha = alpha.point(lambda a: 255 if a > threshold else 0)
        alpha = alpha.filter(ImageFilter.MinFilter(3))  # 收缩 1px 去背景色残留
        img.putalpha(alpha)
        # 2. 裁到非透明区
        bbox = img.getbbox()
        if not bbox:
            return None  # 全透明 → 抠图失败
        img = img.crop(bbox)
        # 3. 等比缩放到画布内（留 8% 边距，主体不顶满）
        target = max(1, int(size * 0.92))
        w, h = img.size
        scale = min(target / w, target / h)
        new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        # 4. 居中贴到透明画布
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(img, ((size - new_w) // 2, (size - new_h) // 2))
        buf = io.BytesIO()
        canvas.save(buf, "PNG")
        return buf.getvalue()
    except Exception as e:
        log.warning("cutout_to_canvas 处理失败: %s", e)
        return None
