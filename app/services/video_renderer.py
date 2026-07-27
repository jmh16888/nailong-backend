"""动画视频渲染：卡通照片 + 分镜剧本 → 奶龙历险 mp4。

实现路线（无 moviepy 依赖，全部可控）：
1. 每幕用 PIL 逐帧渲染：Ken Burns 运镜（缩放/平移裁剪）+ 奶龙动作（走/跳/探头）
   + 中文字幕（描边 + 半透明底板）+ 转场（淡入淡出/滑动，直接在帧上做）；
2. 帧经管道喂给 ffmpeg（imageio-ffmpeg 自带二进制）编码成分段 mp4（含该幕配音）；
3. 分段用 concat demuxer 无损拼接成成片。

配音：edge-tts（免费，zh-CN-XiaoyiNeural），音频时长由 mutagen 读取并撑开该幕时长。
"""
from __future__ import annotations

import asyncio
import io
import logging
import math
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..schemas.video import AvatarAction, CameraMotion, Scene, TransitionStyle, VideoGenerateRequest
from . import cartoon, llm, store, vlm

log = logging.getLogger(__name__)

W, H, FPS = 1280, 720, 24
AVATAR_H = 240          # 奶龙在画面中的高度（像素）
_SUB_FONT_SIZE = 38

_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",                    # macOS
    "C:/Windows/Fonts/msyh.ttc",                             # Windows 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",                           # Windows 黑体
]


# ---------------------------------------------------------------- 字体/配音

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    from ..config import settings
    font_dir = settings.assets_dir / "fonts"
    if font_dir.exists():
        for p in sorted(font_dir.glob("*.*tf*")):  # 用户自放字体优先（ttf/otf/ttc）
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise RuntimeError("找不到中文字体：请把 ttf/ttc 字体放到 app/assets/fonts/ 下")


async def _tts(text: str, out: Path, voice: str = "zh-CN-XiaoyiNeural") -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice=voice, rate="+5%").save(str(out))


def _audio_len(path: Path) -> float:
    from mutagen.mp3 import MP3
    return float(MP3(str(path)).info.length)


# ---------------------------------------------------------------- 帧渲染

def _cover(img: Image.Image, scale: float = 1.0) -> Image.Image:
    """等比放大到铺满 W×H 的 scale 倍（Ken Burns 的源图）"""
    w, h = img.size
    s = max(W / w, H / h) * scale
    return img.resize((int(w * s + 0.5), int(h * s + 0.5)), Image.LANCZOS)


def _ken_burns_crop(src: Image.Image, motion: CameraMotion, t: float) -> Image.Image:
    """从放大源图裁剪 W×H 窗口。t ∈ [0,1]。zoom 系用缩放变化，pan 系用平移"""
    if motion in (CameraMotion.zoom_in, CameraMotion.zoom_out):
        z0, z1 = (1.00, 1.15) if motion == CameraMotion.zoom_in else (1.15, 1.00)
        view = _cover(src, z0 + (z1 - z0) * t)
        x = (view.width - W) // 2
        y = (view.height - H) // 2
        return view.crop((x, y, x + W, y + H))
    if motion in (CameraMotion.pan_left, CameraMotion.pan_right):
        view = _cover(src, 1.15)
        span = view.width - W
        r = t if motion == CameraMotion.pan_left else 1 - t
        x = int(span * (0.75 - 0.5 * r) + span * 0.25)  # 在 25%~75% 区间移动
        return view.crop((x, (view.height - H) // 2, x + W, (view.height - H) // 2 + H))
    return _cover(src).crop((0, 0, W, H)) if src.size != (W, H) else _cover_center(src)


def _cover_center(src: Image.Image) -> Image.Image:
    view = _cover(src)
    x, y = (view.width - W) // 2, (view.height - H) // 2
    return view.crop((x, y, x + W, y + H))


def _avatar_pos(action: AvatarAction, t: float, avatar: Image.Image) -> tuple[int, int] | None:
    ground = H - avatar.height - 36
    if action == AvatarAction.walk_across:
        x = int(-avatar.width + (W + avatar.width * 2) * t)
        bob = int(abs(math.sin(t * math.pi * 6)) * 14)
        return x, ground - bob
    if action == AvatarAction.bounce:
        return 120, ground - int(abs(math.sin(t * math.pi * 3)) * 70)
    if action == AvatarAction.peek_corner:
        slide = min(1.0, t / 0.2)
        x = int(W - 40 - (avatar.width - 60) * slide)
        return x, ground + 60
    return None  # none: 不出镜


def _draw_subtitle(frame: Image.Image, text: str, font: ImageFont.FreeTypeFont) -> None:
    lines: list[str] = []
    for para in text.split("\n"):
        lines += textwrap.wrap(para, 22) or [""]
    lines = lines[:2]
    d = ImageDraw.Draw(frame, "RGBA")
    line_h = _SUB_FONT_SIZE + 14
    box_h = line_h * len(lines) + 28
    y0 = H - box_h - 30
    d.rounded_rectangle((80, y0, W - 80, y0 + box_h), 16, fill=(0, 0, 0, 130))
    for i, line in enumerate(lines):
        bbox = d.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        tx, ty = (W - tw) // 2, y0 + 14 + i * line_h
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):  # 描边
            d.text((tx + dx, ty + dy), line, font=font, fill=(0, 0, 0, 255))
        d.text((tx, ty), line, font=font, fill=(255, 255, 255, 255))


def _apply_transition(frame: Image.Image, style: TransitionStyle,
                      t: float, is_head: bool, is_tail: bool) -> Image.Image:
    """转场直接画在帧上：fade=首尾向白色淡变；slide=首尾平移出场/入场"""
    dur = 0.35  # 转场时长占比
    if style == TransitionStyle.fade:
        if is_head and t < dur:
            alpha = int(255 * (1 - t / dur))
            frame = Image.blend(Image.new("RGB", (W, H), (255, 255, 255)), frame, 1 - alpha / 255)
        elif is_tail and t > 1 - dur:
            alpha = (t - (1 - dur)) / dur
            frame = Image.blend(frame, Image.new("RGB", (W, H), (255, 255, 255)), alpha)
    elif style == TransitionStyle.slide:
        if is_head and t < dur:
            off = int(W * 0.25 * (1 - t / dur))
            bg = Image.new("RGB", (W, H), (255, 255, 255))
            bg.paste(frame, (off, 0))
            frame = bg
        elif is_tail and t > 1 - dur:
            off = -int(W * 0.25 * (t - (1 - dur)) / dur)
            bg = Image.new("RGB", (W, H), (255, 255, 255))
            bg.paste(frame, (off, 0))
            frame = bg
    return frame


# ---------------------------------------------------------------- ffmpeg

def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _encode_segment(frames, audio: Path | None, out: Path) -> None:
    cmd = [_ffmpeg(), "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "pipe:0"]
    if audio and audio.exists():
        cmd += ["-i", str(audio)]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for f in frames:
            proc.stdin.write(f.tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg 编码分段失败: {out.name}")
    except BrokenPipeError:
        proc.wait()
        raise RuntimeError(f"ffmpeg 管道中断: {out.name}")


def _concat(segments: list[Path], out: Path) -> None:
    lst = out.parent / "concat.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in segments), encoding="utf-8")
    r = subprocess.run([_ffmpeg(), "-y", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c", "copy", str(out)],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 拼接失败: {r.stderr.decode()[:300]}")


# ---------------------------------------------------------------- 主流程

def render_video(job_id: str, req: VideoGenerateRequest, photo_paths: list[Path],
                 on_progress) -> tuple[Path, list[Scene]]:
    """完整 pipeline。on_progress(stage, progress, storyboard=None) 由调用方更新任务状态。
    返回 (成片路径, 分镜剧本)。"""
    work = store.output_dir(f"videos/{job_id}_work")
    n = len(photo_paths)

    # 1. 卡通化（0 ~ 0.30）
    cartoon_imgs: list[Image.Image] = []
    for i, p in enumerate(photo_paths):
        on_progress(f"卡通化 {i + 1}/{n}", 0.30 * i / n)
        data = cartoon.cartoonize(p.read_bytes(), cartoon.CartoonStyle.paprika)
        cartoon_imgs.append(Image.open(io.BytesIO(data)).convert("RGB"))

    # 2. 照片描述（0.30 ~ 0.55）
    descriptions: list[str] = []
    for i, p in enumerate(photo_paths):
        on_progress(f"照片描述 {i + 1}/{n}", 0.30 + 0.25 * i / n)
        try:
            descriptions.append(vlm.describe_photo(p.read_bytes()))
        except Exception as e:
            log.warning("第 %d 张照片描述失败(%s)，用通用描述", i + 1, e)
            descriptions.append("一处美丽的风景")

    # 3. 分镜剧本（0.55 ~ 0.65）
    on_progress("剧本生成", 0.58)
    photo_ids = [p.stem for p in photo_paths]
    try:
        scenes = llm.write_story(descriptions, req.theme, req.sec_per_scene)
    except Exception as e:
        log.warning("剧本生成失败(%s)，使用默认剧本", e)
        scenes = [Scene(photo_id="", narration="奶龙继续它的奇妙历险！",
                        duration_sec=req.sec_per_scene) for _ in photo_paths]
    for s, pid in zip(scenes, photo_ids):
        s.photo_id = pid
    on_progress("剧本生成", 0.65, scenes)

    # 4. 配音（0.65 ~ 0.80）
    audios: list[Path | None] = []
    if req.with_narration:
        for i, s in enumerate(scenes):
            on_progress(f"配音 {i + 1}/{n}", 0.65 + 0.15 * i / n)
            ap = work / f"voice_{i}.mp3"
            try:
                asyncio.run(_tts(s.narration, ap))
                audios.append(ap)
                s.duration_sec = max(s.duration_sec, _audio_len(ap) + 0.5)
            except Exception as e:
                log.warning("第 %d 幕配音失败(%s)，该幕静音", i + 1, e)
                audios.append(None)
    else:
        audios = [None] * n

    # 5. 渲染（0.80 ~ 1.00）
    avatar_img: Image.Image | None = None
    if req.avatar_id:
        ap = store.output_dir("avatars") / f"{req.avatar_id}.png"
        if ap.exists():
            raw = Image.open(ap).convert("RGBA")
            aw = int(raw.width * AVATAR_H / raw.height)
            avatar_img = raw.resize((aw, AVATAR_H), Image.LANCZOS)

    font = _load_font(_SUB_FONT_SIZE)
    segments: list[Path] = []
    for i, (cimg, scene, audio) in enumerate(zip(cartoon_imgs, scenes, audios)):
        on_progress(f"渲染 {i + 1}/{n}", 0.80 + 0.18 * i / n, scenes)
        n_frames = max(1, int(scene.duration_sec * FPS))

        def frames():
            for f in range(n_frames):
                t = f / max(n_frames - 1, 1)
                frame = _ken_burns_crop(cimg, scene.camera_motion, t).convert("RGB")
                if avatar_img is not None:
                    pos = _avatar_pos(scene.avatar_action, t, avatar_img)
                    if pos:
                        rgba = frame.convert("RGBA")
                        rgba.alpha_composite(avatar_img, pos)
                        frame = rgba.convert("RGB")
                _draw_subtitle(frame, scene.narration, font)
                yield _apply_transition(frame, req.transition, t,
                                        is_head=(i > 0), is_tail=(i < n - 1))

        seg = work / f"seg_{i:02d}.mp4"
        _encode_segment(frames(), audio, seg)
        segments.append(seg)

    on_progress("拼接成片", 0.99, scenes)
    final = store.output_dir("videos") / f"{job_id}.mp4"
    _concat(segments, final)
    return final, scenes
