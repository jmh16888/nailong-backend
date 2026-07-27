"""纸娃娃合成引擎：特征 JSON → 奶龙形象 PNG。

两层素材机制：
1. **文件图层**：若 app/assets/nailong/{类别}/{变体}.png 存在则直接使用
   （可用 CogView 生成/手绘的精美素材随时替换，512×512 透明底，锚点与下方程序化绘制一致）；
2. **程序化绘制**：缺省时用 Pillow 几何图形画出奶龙与各部件 —— 零素材即可端到端跑通。

图层顺序：cape(背后) → body → belly(肤色) → outfit → arms → expression → blush
          → hair → glasses → accessory
"""
from __future__ import annotations

import logging
import math

from PIL import Image, ImageDraw

from ..config import settings
from ..schemas.avatar import (
    Accessory, Expression, FaceFeatures, Glasses, HairColor, HairStyle, Outfit, SkinTone,
)

log = logging.getLogger(__name__)

CANVAS = 512
CX = CANVAS // 2

BODY_COLOR = (255, 211, 77, 255)
BODY_OUTLINE = (228, 176, 48, 255)
BELLY_COLORS = {  # skin_tone → 肚皮/脸颊区块颜色（奶龙本体的"肤色"映射）
    SkinTone.fair: (255, 242, 200, 255),
    SkinTone.light: (255, 236, 178, 255),
    SkinTone.medium: (247, 224, 158, 255),
    SkinTone.tan: (238, 212, 142, 255),
    SkinTone.dark: (228, 200, 128, 255),
}
HAIR_COLORS = {
    HairColor.black: (43, 39, 41, 255),
    HairColor.brown: (120, 72, 40, 255),
    HairColor.blonde: (240, 200, 110, 255),
    HairColor.gray_white: (222, 222, 228, 255),
    HairColor.colorful: (230, 90, 150, 255),
}
PINK = (255, 150, 160, 110)

# 身体各部位几何（512 画布，奶龙 = 一颗圆润黄豆）
_BODY = (116, 118, 396, 470)     # 主体椭圆
_BELLY = (178, 292, 334, 452)
_ARM_L = (104, 296, 158, 366)
_ARM_R = (354, 296, 408, 366)
_FOOT_L = (168, 442, 244, 482)
_FOOT_R = (268, 442, 344, 482)
_EYE_L, _EYE_R = (206, 246), (306, 246)
_EYE_R_X, _EYE_R_Y = 26, 30
_MOUTH = (CX, 312)


# ---------------------------------------------------------------- 文件图层

def _file_layer(category: str, variant: str) -> Image.Image | None:
    p = settings.assets_dir / "nailong" / category / f"{variant}.png"
    if p.exists():
        try:
            return Image.open(p).convert("RGBA").resize((CANVAS, CANVAS))
        except Exception as e:  # 坏素材不致命，回退程序化
            log.warning("素材 %s 读取失败(%s)，回退程序化绘制", p, e)
    return None


# ---------------------------------------------------------------- 程序化图层

def _draw_body(d: ImageDraw.ImageDraw, skin: SkinTone) -> None:
    # 头顶小呆毛（奶龙标志性触角）
    d.line([(CX, 122), (CX, 92)], fill=BODY_OUTLINE, width=8)
    d.ellipse((CX - 22, 74, CX - 2, 96), fill=(120, 200, 90, 255))   # 左叶
    d.ellipse((CX + 2, 74, CX + 22, 96), fill=(120, 200, 90, 255))   # 右叶
    # 脚
    for box in (_FOOT_L, _FOOT_R):
        d.ellipse(box, fill=BODY_COLOR, outline=BODY_OUTLINE, width=4)
    # 身体（一颗豆）
    d.ellipse(_BODY, fill=BODY_COLOR, outline=BODY_OUTLINE, width=5)
    # 肚皮（肤色映射区）
    d.ellipse(_BELLY, fill=BELLY_COLORS[skin])
    # 手
    for box in (_ARM_L, _ARM_R):
        d.ellipse(box, fill=BODY_COLOR, outline=BODY_OUTLINE, width=4)


def _draw_expression(d: ImageDraw.ImageDraw, expr: Expression) -> None:
    for (ex, ey) in (_EYE_L, _EYE_R):
        x0, y0 = ex - _EYE_R_X, ey - _EYE_R_Y
        x1, y1 = ex + _EYE_R_X, ey + _EYE_R_Y
        if expr == Expression.happy:
            # 眯眯笑眼：向上弯的弧线
            d.arc((x0 + 2, y0 + 10, x1 - 2, y1 + 16), 180, 360, fill=(60, 50, 45, 255), width=7)
        else:
            d.ellipse((x0, y0, x1, y1), fill=(255, 255, 255, 255), outline=(60, 50, 45, 255), width=3)
            pr = 13 if expr == Expression.surprised else 11
            dy = 8 if expr == Expression.shy else 0
            d.ellipse((ex - pr, ey - pr + dy, ex + pr, ey + pr + dy), fill=(45, 40, 38, 255))
            d.ellipse((ex - 4, ey - 6 + dy, ex + 3, ey + 1 + dy), fill=(255, 255, 255, 255))
            if expr == Expression.cool:  # 半垂眼皮
                d.pieslice((x0 - 2, y0 - 14, x1 + 2, y1), 180, 360, fill=BODY_COLOR)

    mx, my = _MOUTH
    if expr == Expression.happy:
        d.pieslice((mx - 34, my - 16, mx + 34, my + 30), 0, 180, fill=(120, 60, 50, 255))
        d.pieslice((mx - 22, my + 6, mx + 22, my + 26), 0, 180, fill=(240, 120, 120, 255))  # 舌头
    elif expr == Expression.surprised:
        d.ellipse((mx - 14, my - 10, mx + 14, my + 18), fill=(120, 60, 50, 255))
    elif expr == Expression.cool:
        d.arc((mx - 26, my - 8, mx + 30, my + 22), 20, 150, fill=(120, 60, 50, 255), width=6)
    elif expr == Expression.shy:
        d.arc((mx - 18, my - 4, mx + 18, my + 18), 20, 160, fill=(120, 60, 50, 255), width=5)
    else:  # neutral
        d.line([(mx - 20, my + 4), (mx + 20, my + 4)], fill=(120, 60, 50, 255), width=6)

    # 腮红（shy 更明显）
    alpha = 160 if expr == Expression.shy else 90
    for bx in (176, 336):
        d.ellipse((bx - 22, 288, bx + 22, 306), fill=(255, 150, 160, alpha))


def _draw_hair(d: ImageDraw.ImageDraw, style: HairStyle, color: tuple) -> None:
    if style == HairStyle.bald:
        return
    # 基础发盖（头顶圆弧）
    def cap(depth: int) -> None:
        d.pieslice((124, 118 - depth // 2, 388, 300), 180, 360, fill=color)

    if style == HairStyle.buzz:
        d.pieslice((128, 104, 384, 260), 180, 360, fill=color)
    elif style == HairStyle.short:
        cap(40)
        for i in range(7):  # 锯齿刘海
            x = 140 + i * 34
            d.polygon([(x, 190), (x + 17, 218), (x + 34, 190)], fill=color)
    elif style == HairStyle.medium:
        cap(60)
        d.rectangle((124, 170, 168, 330), fill=color)
        d.rectangle((344, 170, 388, 330), fill=color)
    elif style == HairStyle.long_straight:
        cap(60)
        d.rectangle((118, 170, 170, 430), fill=color)
        d.rectangle((342, 170, 394, 430), fill=color)
    elif style == HairStyle.long_curly:
        cap(60)
        for side_x in (144, 368):
            for j, yy in enumerate(range(190, 420, 46)):
                off = 12 if j % 2 else -6
                d.ellipse((side_x - 30 + off, yy, side_x + 30 + off, yy + 52), fill=color)
    elif style == HairStyle.ponytail:
        cap(50)
        d.polygon([(330, 150), (430, 200), (452, 330), (400, 320), (360, 210)], fill=color)
        d.ellipse((400, 300, 460, 380), fill=color)  # 马尾末端
    elif style == HairStyle.twin_tails:
        cap(50)
        for side_x in (128, 384):
            d.ellipse((side_x - 34, 180, side_x + 34, 248), fill=color)
            d.ellipse((side_x - 26, 236, side_x + 26, 330), fill=color)
            d.ellipse((side_x - 18, 318, side_x + 18, 386), fill=color)
    elif style == HairStyle.bun:
        cap(50)
        d.ellipse((CX - 34, 66, CX + 34, 134), fill=color)
        d.arc((CX - 34, 66, CX + 34, 134), 0, 360, fill=(0, 0, 0, 60), width=3)


def _draw_glasses(d: ImageDraw.ImageDraw, kind: Glasses) -> None:
    if kind == Glasses.none:
        return
    dark = (45, 42, 40, 255)
    for (ex, ey) in (_EYE_L, _EYE_R):
        if kind == Glasses.round:
            d.ellipse((ex - 38, ey - 36, ex + 38, ey + 36), outline=dark, width=6)
        elif kind == Glasses.square:
            d.rounded_rectangle((ex - 40, ey - 32, ex + 40, ey + 34), 10, outline=dark, width=6)
        elif kind == Glasses.sunglasses:
            d.rounded_rectangle((ex - 42, ey - 28, ex + 42, ey + 32), 14, fill=(35, 35, 45, 235))
    # 镜桥 + 镜腿
    d.line([(_EYE_L[0] + 36, _EYE_L[1]), (_EYE_R[0] - 36, _EYE_R[1])], fill=dark, width=6)
    d.line([(_EYE_L[0] - 40, _EYE_L[1]), (150, 240)], fill=dark, width=5)
    d.line([(_EYE_R[0] + 40, _EYE_R[1]), (362, 240)], fill=dark, width=5)


def _draw_outfit(d: ImageDraw.ImageDraw, outfit: Outfit, layer: Image.Image) -> None:
    if outfit == Outfit.none:
        return
    if outfit == Outfit.tshirt:
        c = (90, 140, 250, 255)
        d.polygon([(170, 350), (342, 350), (356, 470), (156, 470)], fill=c)
        d.ellipse((120, 330, 190, 390), fill=c)
        d.ellipse((322, 330, 392, 390), fill=c)
    elif outfit == Outfit.hoodie:
        c = (250, 120, 90, 255)
        d.polygon([(168, 344), (344, 344), (358, 470), (154, 470)], fill=c)
        d.arc((196, 312, 316, 380), 180, 360, fill=(230, 100, 75, 255), width=18)  # 帽兜
        d.rounded_rectangle((216, 410, 296, 452), 8, fill=(230, 100, 75, 255))     # 口袋
        d.line([(236, 366), (236, 392)], fill=(255, 255, 255, 255), width=4)       # 抽绳
        d.line([(276, 366), (276, 392)], fill=(255, 255, 255, 255), width=4)
    elif outfit == Outfit.dress:
        c = (250, 130, 180, 255)
        d.polygon([(206, 336), (306, 336), (380, 472), (132, 472)], fill=c)
        d.arc((206, 322, 306, 358), 0, 180, fill=(235, 100, 150, 255), width=8)
        for x in range(160, 380, 40):
            d.ellipse((x, 440, x + 14, 458), fill=(255, 190, 210, 255))
    elif outfit == Outfit.suit:
        d.polygon([(170, 344), (342, 344), (356, 470), (156, 470)], fill=(52, 56, 72, 255))
        d.polygon([(216, 344), (296, 344), (256, 420)], fill=(245, 245, 248, 255))  # 衬衫
        d.polygon([(248, 350), (264, 350), (268, 404), (256, 420), (244, 404)], fill=(200, 50, 50, 255))  # 领带
    elif outfit == Outfit.cape:
        # 背后披风在 _layer 底图先画（见 compose_avatar），这里画颈前系扣
        d.ellipse((CX - 12, 330, CX + 12, 354), fill=(250, 210, 80, 255), outline=(180, 130, 40, 255), width=3)


def _draw_cape_back(img: Image.Image) -> None:
    d = ImageDraw.Draw(img)
    d.polygon([(196, 330), (316, 330), (400, 486), (112, 486)], fill=(200, 60, 60, 255))
    d.polygon([(196, 330), (316, 330), (392, 486), (120, 486)], outline=(160, 40, 40, 255))


def _draw_accessory(d: ImageDraw.ImageDraw, acc: Accessory) -> None:
    if acc == Accessory.hat:
        d.rectangle((216, 44, 296, 112), fill=(70, 130, 200, 255))
        d.ellipse((192, 92, 320, 136), fill=(60, 115, 180, 255))
        d.rectangle((216, 96, 296, 112), fill=(250, 200, 70, 255))  # 帽带
    elif acc == Accessory.headband:
        d.arc((140, 108, 372, 260), 185, 355, fill=(250, 90, 120, 255), width=16)
    elif acc == Accessory.bow:
        bx, by = 336, 156
        d.polygon([(bx, by), (bx - 44, by - 26), (bx - 44, by + 26)], fill=(250, 130, 170, 255))
        d.polygon([(bx, by), (bx + 44, by - 26), (bx + 44, by + 26)], fill=(250, 130, 170, 255))
        d.ellipse((bx - 11, by - 11, bx + 11, by + 11), fill=(235, 100, 145, 255))
    elif acc == Accessory.scarf:
        d.arc((176, 300, 336, 380), 0, 180, fill=(240, 80, 80, 255), width=26)
        d.rounded_rectangle((300, 356, 336, 428), 8, fill=(240, 80, 80, 255))
        d.line([(306, 416), (330, 416)], fill=(255, 200, 200, 255), width=3)


# ---------------------------------------------------------------- 合成入口

def compose_avatar(features: FaceFeatures, size: int = CANVAS) -> tuple[Image.Image, list[str]]:
    """按特征合成奶龙形象，返回 (RGBA 图, 实际图层说明列表)"""
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    layers: list[str] = []

    def use(category: str, variant: str, draw_fn, *args) -> None:
        nonlocal img
        file_img = _file_layer(category, variant)
        if file_img is not None:
            img.alpha_composite(file_img)
            layers.append(f"file:{category}/{variant}.png")
        else:
            draw_fn(*args)
            layers.append(f"proc:{category}/{variant}")

    if features.outfit == Outfit.cape:
        _draw_cape_back(img)
        layers.append("proc:outfit/cape_back")

    d = ImageDraw.Draw(img)
    use("body", "base", _draw_body, d, features.skin_tone)
    use("outfit", features.outfit.value, _draw_outfit, d, features.outfit, img)
    use("expression", features.expression.value, _draw_expression, d, features.expression)

    if features.hair_style != HairStyle.bald:
        hcolor = HAIR_COLORS[features.hair_color]
        use("hair", f"{features.hair_style.value}_{features.hair_color.value}",
            _draw_hair, d, features.hair_style, hcolor)

    use("glasses", features.glasses.value, _draw_glasses, d, features.glasses)
    for acc in features.accessories:
        if acc != Accessory.none:
            use("accessory", acc.value, _draw_accessory, d, acc)

    if size != CANVAS:
        img = img.resize((size, size), Image.LANCZOS)
    return img, layers
