"""端到端冒烟测试脚本：本地照片 → 上传 → 形象 → 背景 → 游戏 → 视频

用法：
    1. 先启动后端：uvicorn app.main:app --port 8000
    2. 改下面 CONFIG 区的照片路径（必填），其余可按需调整
    3. python scripts/e2e_test.py            # 全链路
       python scripts/e2e_test.py --skip-video   # 跳过视频（最慢的一步）

所有响应 JSON 会打印到终端，生成的图片/视频 URL 也会列在最后，
产物同时保存在服务器 app/storage/ 下（脚本不下载，只打印可访问 URL）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

# ============================== CONFIG ==============================
BASE_URL = "http://127.0.0.1:8000"

# 【改这里】测试照片路径：人脸照（用于卡通形象分析）
PORTRAIT_PHOTO = Path("/root/ND/test_data/2184.jpg")

# 【改这里】背景生成 prompt（想生成什么背景就写什么，仅示例）
BG_PROMPT = "校园操场，阳光明媚，有教学楼和跑道"

# 【改这里】视频串烧用的照片列表（1~10 张，需已存在于本机）
VIDEO_PHOTOS = [
    Path("/root/ND/test_data/2011.jpg"),
    Path("/root/ND/test_data/2012.jpg"),
    Path("/root/ND/test_data/2013.jpg"),
]

# 输出目录：脚本把每步响应 JSON 存这里，方便核对
OUTPUT_DIR = Path(__file__).resolve().parent / "test_output"

# 视频生成参数
VIDEO_THEME = "卡通历险记"
VIDEO_WITH_NARRATION = True      # edge-tts 配音（需联网）
VIDEO_POLL_INTERVAL = 5          # 轮询间隔秒
VIDEO_TIMEOUT = 600              # 最长等待秒
# =====================================================================

client = httpx.Client(base_url=BASE_URL, timeout=60.0)
results: dict[str, dict] = {}   # 每步响应，最后落盘


def step(name: str):
    print(f"\n{'='*20} {name} {'='*20}")

def dump(name: str, data: dict):
    results[name] = data
    print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])

def save_results():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"result_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n全部响应已保存: {out}")

def need(path: Path) -> bool:
    if not path.exists():
        print(f"!! 照片不存在，请先放好: {path}")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-video", action="store_true", help="跳过视频生成（最慢）")
    args = parser.parse_args()

    # ---------- 0. 健康检查 ----------
    step("0. 健康检查 GET /api/health")
    r = client.get("/api/health")
    dump("health", r.json())
    if not r.json().get("zhipu_key_configured"):
        print("!! 警告：未配置 CARTOON_ZHIPU_API_KEY，VLM/剧本相关步骤会走降级逻辑")

    # ---------- 1. 卡通形象：分析 ----------
    step("1. 形象分析 POST /api/v1/avatars/analyze")
    if not need(PORTRAIT_PHOTO):
        return 1
    with PORTRAIT_PHOTO.open("rb") as f:
        r = client.post("/api/v1/avatars/analyze", files={"file": (PORTRAIT_PHOTO.name, f, "image/jpeg")})
    r.raise_for_status()
    analyze = r.json()
    dump("avatar_analyze", analyze)
    avatar_id = analyze["avatar_id"]
    features = analyze["features"]

    # ---------- 2. 形象合成 ----------
    step("2. 形象合成 POST /api/v1/avatars/compose")
    r = client.post("/api/v1/avatars/compose", json={
        "features": features,
        "avatar_id": avatar_id,      # 挂在同一记录下，后续游戏/视频可引用
    })
    r.raise_for_status()
    dump("avatar_compose", r.json())

    # ---------- 3. 换装 ----------
    step("3. 换装 PUT /api/v1/avatars/{avatar_id}/outfit")
    r = client.put(f"/api/v1/avatars/{avatar_id}/outfit", json={
        "outfit": "cape", "accessory": "bow", "expression": "happy",
    })
    r.raise_for_status()
    dump("avatar_outfit", r.json())

    # ---------- 4. 衣橱清单 ----------
    step("4. 衣橱 GET /api/v1/assets/wardrobe")
    r = client.get("/api/v1/assets/wardrobe")
    r.raise_for_status()
    dump("wardrobe", r.json())

    # ---------- 5. 背景生成（用户输入 prompt → CogView） ----------
    step("5. 背景生成 POST /api/v1/backgrounds/cartoonize")
    r = client.post("/api/v1/backgrounds/cartoonize", json={"prompt": BG_PROMPT})
    r.raise_for_status()
    cartoon = r.json()
    dump("background_cartoonize", cartoon)
    background_id = cartoon["background_id"]

    # ---------- 6. 游戏素材包 ----------
    step("6. 游戏素材包 POST /api/v1/games/package")
    r = client.post("/api/v1/games/package", json={
        "avatar_id": avatar_id,
        "background_id": background_id,
        "difficulty": "normal",
        "duration_sec": 60,
        "heart_count": 3,
        "coin_count": 20,
    })
    r.raise_for_status()
    package = r.json()
    dump("game_package", package)

    # ---------- 7. 排行榜 ----------
    step("7. 提交分数 + 排行榜")
    r = client.post("/api/v1/games/scores", json={
        "nickname": "测试员", "score": 1280,
        "difficulty": "normal", "game_id": package["game_id"],
    })
    r.raise_for_status()
    dump("score_submit", r.json())
    r = client.get("/api/v1/games/leaderboard", params={"difficulty": "normal", "limit": 10})
    r.raise_for_status()
    dump("leaderboard", r.json())

    # ---------- 8. 视频生成（异步轮询） ----------
    if args.skip_video:
        print("\n已跳过视频生成（--skip-video）")
    else:
        step("8. 视频生成 POST /api/v1/videos/generate + 轮询")
        photos = [p for p in VIDEO_PHOTOS if p.exists()]
        if not photos:
            print("!! VIDEO_PHOTOS 里没有可用照片，跳过视频步骤")
        else:
            photo_ids = []
            for p in photos:
                with p.open("rb") as f:
                    r = client.post("/api/v1/uploads", files={"file": (p.name, f, "image/jpeg")})
                r.raise_for_status()
                photo_ids.append(r.json()["photo_id"])
            print(f"已上传 {len(photo_ids)} 张照片: {photo_ids}")

            # 视频改走 CogVideoX-Flash 文生视频（GLM-4 剧本→单段 mp4，~1-3 分钟）
            # with_narration/transition/sec_per_scene/avatar_id 现已忽略（兼容保留）
            r = client.post("/api/v1/videos/generate", json={
                "photo_ids": photo_ids,
                "avatar_id": avatar_id,
                "theme": VIDEO_THEME,
                "with_narration": VIDEO_WITH_NARRATION,
                "transition": "fade",
                "sec_per_scene": 3.0,
            })
            r.raise_for_status()
            job = r.json()
            dump("video_submit", job)
            job_id = job["job_id"]

            deadline = time.time() + VIDEO_TIMEOUT
            while time.time() < deadline:
                time.sleep(VIDEO_POLL_INTERVAL)
                r = client.get(f"/api/v1/videos/{job_id}")
                r.raise_for_status()
                job = r.json()
                print(f"  [{job['status']}] {job['progress']*100:.0f}% {job['stage']}")
                if job["status"] in ("done", "failed"):
                    break
            dump("video_result", job)
            if job["status"] != "done":
                print(f"!! 视频生成失败或超时: {job.get('error')}")

    save_results()

    # ---------- 产物 URL 汇总 ----------
    print(f"\n{'='*20} 产物 URL（拼上 {BASE_URL} 即可访问） {'='*20}")
    def show(key, path):
        node = results.get(key)
        cur = node
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return
            cur = cur[p]
        if cur:
            print(f"  {key}: {BASE_URL}{cur}")

    show("avatar_analyze", ["face_crop", "url"])
    show("avatar_compose", ["image", "url"])
    show("avatar_outfit", ["image", "url"])
    show("background_cartoonize", ["image", "url"])
    show("game_package", ["background", "url"])
    show("video_result", ["video", "url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
