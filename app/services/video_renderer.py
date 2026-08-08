"""动画视频生成：CogVideoX-Flash 文生视频。

pipeline：GLM-4V-Flash 描述照片 → GLM-4-Flash 写分镜剧本 → 拼成一段 prompt
          → CogVideoX-Flash 文生视频（with_audio AI 音效）→ 落盘 mp4。

不再用 PIL 逐帧合成 / ffmpeg 编码拼接 / edge-tts 旁白——CogVideoX 直出带音效的 mp4。
照片/形象不再是视频像素来源，只作故事文本种子（CogVideoX 纯文生视频，不收图）。
"""
from __future__ import annotations

import logging
from pathlib import Path

from ..schemas.video import Scene, VideoGenerateRequest
from . import llm, store, vlm, zhipu

log = logging.getLogger(__name__)


def render_video(job_id: str, req: VideoGenerateRequest, photo_paths: list[Path],
                 on_progress) -> tuple[Path, list[Scene]]:
    """完整 pipeline。on_progress(stage, progress, storyboard=None) 由调用方更新任务状态。
    返回 (成片路径, 分镜剧本)。"""
    n = len(photo_paths)

    # 1. 照片描述（0 ~ 0.40）—— GLM-4V-Flash，作故事素材
    descriptions: list[str] = []
    for i, p in enumerate(photo_paths):
        on_progress(f"照片描述 {i + 1}/{n}", 0.40 * (i + 1) / max(n, 1))
        try:
            descriptions.append(vlm.describe_photo(p.read_bytes()))
        except Exception as e:
            log.warning("第 %d 张照片描述失败(%s)，用通用描述", i + 1, e)
            descriptions.append("一处美丽的风景")

    # 2. 分镜剧本（0.40 ~ 0.55）—— GLM-4-Flash
    on_progress("剧本生成", 0.50)
    try:
        scenes = llm.write_story(descriptions, req.theme, req.sec_per_scene)
    except Exception as e:
        log.warning("剧本生成失败(%s)，使用默认剧本", e)
        scenes = [Scene(photo_id="", narration="主角继续它的奇妙历险！",
                        duration_sec=req.sec_per_scene) for _ in photo_paths]
    for s, pid in zip(scenes, [p.stem for p in photo_paths]):
        s.photo_id = pid
    on_progress("剧本生成", 0.55, scenes)

    # 3. 拼 CogVideoX prompt（theme + 全部分镜 narration）
    narrations = "；".join(s.narration for s in scenes if s.narration)
    prompt = f"{req.theme}：{narrations}" if narrations else req.theme

    # 4. CogVideoX 文生视频（0.55 ~ 0.99，阻塞轮询，约 1~3 分钟）
    on_progress("CogVideoX 生成中", 0.60)
    mp4 = zhipu.cogvideo(prompt, duration=10, with_audio=True)
    final = store.output_dir("videos") / f"{job_id}.mp4"
    final.write_bytes(mp4)
    on_progress("完成", 0.99, scenes)
    return final, scenes
