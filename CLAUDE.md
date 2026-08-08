# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概况

cartoonize-backend 是「照片转 Q版卡通」系统的 FastAPI 后端：上传照片 → 分析五官 → 生成 Q版卡通形象 / 背景 / 游戏素材 / 动画视频。生图走智谱 CogView-3-Flash + rembg 抠透明，失败时降级到本地硬编码兜底。

## 环境与常用命令

- **Python 环境**：conda env 名为 `ND`（`/home/vipuser/miniconda3/envs/ND`，Python 3.10）。README 里写的 `conda activate DN` 是笔误，实际是 `ND`。
  - 激活 `conda activate ND`；直接用解释器 `/home/vipuser/miniconda3/envs/ND/bin/python`。
  - 已装：torch(cu121) / cv2 / PIL / mediapipe / edge-tts / mutagen / rembg+onnxruntime / openai / fastapi。
- 装依赖：`pip install -r requirements.txt`（rembg 已列；u2net 权重首次运行自动下到 `.cache/u2net/`）。
- 启动：`uvicorn app.main:app --reload --port 8000`（app 自己读 `.env`）。
- 健康检查：`curl -s http://127.0.0.1:8000/api/health`（看 `zhipu_key_configured`）。
- 端到端冒烟：先改 `scripts/e2e_test.py` 顶部 CONFIG 区照片路径，再 `python scripts/e2e_test.py --skip-video`（快）/ 不带 flag（含视频）。**无单元测试框架**，这是唯一自动化测试。
- `.env` 必须配 `cartoon_ZHIPU_API_KEY`（从 `.env.example` 拷贝）；不配则 CogView/VLM 全降级。`.env` 被 gitignore，不入库。

## 架构

```
api/v1/    路由层 → services/ 实现 → zhipu/image_gen/bg_remove/vlm/llm（模型调用）
schemas/   ★ 接口契约（pydantic 模型 + 枚举，前后端共用词汇）
prompts/   所有发给大模型的 prompt 模板（集中管理）
config.py  pydantic-settings 读 .env（前缀 cartoon_）
store.py   资源 ID/路径/JSON sidecar；url_of() 把磁盘路径转 /static URL
```

- **入口** `app/main.py`：5 个 router 挂 `/api/v1`（uploads / avatars / backgrounds / games / videos）+ `/api/health`；静态挂载 `/static`（产物+上传）和 `/assets`（素材库）。
- **配置** `app/config.py`：把所有模型缓存（TORCH_HOME / HF_HOME / U2NET_HOME）重定向到项目内 `.cache/`，整个项目目录拷贝即可运行，不散落 `~/.cache`。
- **智谱客户端** `services/zhipu.py`：用 `openai` SDK 指向智谱 bigmodel（OpenAI 兼容端点）。三模型：GLM-4V-Flash（`chat_with_image`，图文理解）、GLM-4-Flash（`chat_text`，文本/剧本）、CogView-3-Flash（`gen_image`，文生图）。共享 client + tenacity 重试 + 信号量限流（`api_concurrency=2`）。CogView 是**纯文生图**，无 img2img 入口、无 system role。

### 生图管线（核心，改动最频繁）

生成的图（形象 / 背景 / 游戏精灵）都走：**CogView-3-Flash 出不透明图 → `services/bg_remove.py` 用 rembg(u2net) 抠成透明 RGBA + alpha 边缘清理 + `getbbox` 自动居中到目标画布**（形象 512、精灵 96）。`services/image_gen.py` 的 `cogview_avatar` / `cogview_background` / `cogview_sprite` 包一层（带输出校验，失败返回 `None`）。

**失败兜底（刻意保留，别删）**：CogView/rembg 失败时降级到本地硬编码——`avatar_compose.py`（Pillow 纸娃娃）、`cartoon.py`（AnimeGANv2 + cv2）、`game_packager._draw_sprite`（Pillow 多边形）。所有模型调用都 try/except 吞掉，endpoint 永不因模型失败而 500。

- **形象契约**：`POST /avatars/analyze`（照片 → MediaPipe + GLM-4V → `FaceFeatures` JSON）→ `POST /avatars/compose`（特征 → PNG，落盘 `outputs/avatars/{avatar_id}.png`，返回 `/static` URL）→ `PUT /avatars/{id}/outfit`（换装重生成）。`{avatar_id}.png` 是透明抠图，被游戏 `make_character_frames`（仿射变换做跑跳帧，保留 alpha）和视频 `video_renderer.alpha_composite`（贴到背景上）消费。
- **背景**：`cartoon.cartoonize` 主路径走 GLM-4V 描述上传照片 → CogView 重画（不忠于原照像素），失败回退 AnimeGAN/cv2。
- **视频**：异步任务（`POST /videos/generate` → `job_id`，轮询 `GET /videos/{job_id}`）。`video_renderer.render_video`：卡通化照片（CogView）→ GLM-4V 描述 → GLM-4-Flash 分镜剧本 → edge-tts 配音 → PIL 逐帧合成（Ken Burns + 角色贴图 + 字幕）→ ffmpeg 编码拼接。

## 关键约定

- **接口契约冻结**：`schemas/` 里所有请求/响应字段名与类型不许改（前端依赖）。可改内部实现和图的像素来源，但 endpoint / schema 不动；换图源或风格不算改接口。
- **改艺术风格 = 改 prompt 字符串，不动逻辑**：风格全在 `prompts/__init__.py`（`fancy_avatar_prompt` / `background_image_prompt` / `sprite_prompt`）。形象当前是 Q版卡通人物（不再绑定卡通）。CogView 无 system 概念，所谓“改系统提示词”就是改这些 prompt 字符串。
- **透明度**：CogView 出不透明图；游戏精灵 / 角色帧 / 视频贴图要透明底，透明由 rembg 提供。别把 CogView 不透明图直接喂给需要透明的消费者（会变不透明色块）。
- **降级优先**：任何模型调用都要有兜底，服务不硬崩。
- **`.env` 不入库**（gitignore）；只有 `.env.example` 是模板。
- 模型并发低（`api_concurrency=2`），CogView 单次 10~30s；rembg 首次加载 u2net 约 3~4s。
