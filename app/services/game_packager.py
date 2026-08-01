"""游戏素材包：跑跳帧生成（Pillow 仿射变换）+ 程序化障碍物/金币精灵 + 关卡配置"""
from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image

from ..schemas.background import SceneTags
from ..schemas.game import (
    CharacterSprite, Difficulty, GameConfig, GamePackageResponse, SpriteInfo,
)
from ..schemas.common import ImageRef
from . import bg_remove, image_gen, store

log = logging.getLogger(__name__)

# 难度 → 关卡数值预设（前端游戏引擎直接消费）
DIFFICULTY_PRESET: dict[Difficulty, dict] = {
    Difficulty.easy:   {"gravity": 1800, "move_speed": 260, "jump_velocity": 720,
                        "obstacle_speed": 180, "interval": (1.6, 2.4)},
    Difficulty.normal: {"gravity": 2000, "move_speed": 300, "jump_velocity": 760,
                        "obstacle_speed": 260, "interval": (1.1, 1.8)},
    Difficulty.hard:   {"gravity": 2200, "move_speed": 340, "jump_velocity": 800,
                        "obstacle_speed": 360, "interval": (0.7, 1.2)},
}

# 场景提示词 → 障碍物精灵类型（关键词匹配）
_OBSTACLE_MAP = [
    (("树桩", "木桩", "stump"), "stump"),
    (("石", "岩", "rock", "stone"), "stone"),
    (("路障", "锥", "cone", "施工"), "cone"),
    (("花", "草丛", "flower"), "flower"),
    (("台阶", "石阶", "楼梯"), "stone"),
    (("车", "护栏"), "cone"),
]
_DEFAULT_OBSTACLES = ["stone", "stump", "cone"]


# ---------------------------------------------------------------- 角色帧

def _anchor_bottom(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """缩放后贴回原画布，底边对齐（跑步挤压感的锚点）"""
    canvas = Image.new("RGBA", img.size, (0, 0, 0, 0))
    resized = img.resize(size, Image.LANCZOS)
    canvas.alpha_composite(resized, ((img.width - size[0]) // 2, img.height - size[1]))
    return canvas


def make_character_frames(avatar_path: Path, out_dir: Path) -> CharacterSprite:
    """从奶龙形象 PNG 生成跑步 2 帧 + 跳跃 1 帧"""
    base = Image.open(avatar_path).convert("RGBA")
    w, h = base.size

    run0 = base
    run1 = _anchor_bottom(base, (int(w * 1.04), int(h * 0.90)))          # 挤压帧
    jump = base.rotate(10, expand=False, resample=Image.BICUBIC)         # 跳跃后仰
    jump = _anchor_bottom(jump, (int(w * 1.02), int(h * 1.02)))

    frames = []
    for name, im in (("run_0", run0), ("run_1", run1), ("jump", jump)):
        p = out_dir / f"{name}.png"
        im.save(p)
        frames.append(p)
    return CharacterSprite(
        run_frames=[ImageRef(id=f.stem, url=store.url_of(f)) for f in frames[:2]],
        jump_frame=ImageRef(id=frames[2].stem, url=store.url_of(frames[2])),
    )


# ---------------------------------------------------------------- 精灵绘制

def _make_sprite(kind: str) -> Image.Image:
    """游戏精灵：CogView 生成 → rembg 抠透明 → 96×96 居中；失败抛错（无 _draw_sprite 兜底）。"""
    b = image_gen.cogview_sprite(kind)
    c = bg_remove.cutout_to_canvas(b, 96) if b else None
    if not c:
        raise RuntimeError(f"精灵生成失败：CogView/抠图未返回有效结果（{kind}）")
    try:
        return Image.open(io.BytesIO(c)).convert("RGBA")
    except Exception as e:
        raise RuntimeError(f"精灵 {kind} 抠图结果解码失败: {e}")


def _pick_obstacles(scene: SceneTags | None) -> list[str]:
    kinds: list[str] = []
    if scene:
        for hint in scene.obstacle_hints:
            for keywords, kind in _OBSTACLE_MAP:
                if any(k in hint for k in keywords) and kind not in kinds:
                    kinds.append(kind)
    for k in _DEFAULT_OBSTACLES:
        if len(kinds) >= 3:
            break
        if k not in kinds:
            kinds.append(k)
    return kinds[:3]


# ---------------------------------------------------------------- 打包入口

def build_package(game_id: str, avatar_path: Path, background_path: Path,
                  scene: SceneTags | None, difficulty: Difficulty,
                  duration_sec: int, heart_count: int, coin_count: int) -> GamePackageResponse:
    out_dir = store.output_dir(f"games/{game_id}")

    character = make_character_frames(avatar_path, out_dir)

    obstacles: list[SpriteInfo] = []
    for kind in _pick_obstacles(scene):
        p = out_dir / f"obstacle_{kind}.png"
        sprite = _make_sprite(kind)
        sprite.save(p)
        obstacles.append(SpriteInfo(name=kind, image=ImageRef(id=kind, url=store.url_of(p)),
                                    width=sprite.width, height=sprite.height))

    coin = _make_sprite("coin")
    coin_path = out_dir / "coin.png"
    coin.save(coin_path)
    coin_sprite = SpriteInfo(name="coin", image=ImageRef(id="coin", url=store.url_of(coin_path)),
                             width=coin.width, height=coin.height)

    p = DIFFICULTY_PRESET[difficulty]
    config = GameConfig(
        difficulty=difficulty, duration_sec=duration_sec,
        heart_count=heart_count, coin_count=coin_count,
        gravity=p["gravity"], move_speed=p["move_speed"], jump_velocity=p["jump_velocity"],
        obstacle_speed=p["obstacle_speed"],
        obstacle_interval_min=p["interval"][0], obstacle_interval_max=p["interval"][1],
    )
    store.save_json(out_dir / "config.json", config)

    return GamePackageResponse(
        game_id=game_id,
        background=ImageRef(id=game_id, url=store.url_of(background_path)),
        character=character,
        obstacles=obstacles,
        coin_sprite=coin_sprite,
        config=config,
    )
