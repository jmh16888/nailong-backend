# nailong-backend

照片转奶龙卡通系统 —— 后端（FastAPI）

## 快速开始

```bash
conda activate ND        # 或新建：conda create -n ND python=3.10 -y
pip install -r requirements.txt
cp .env.example .env     # 填入智谱 API Key（不填也能跑，VLM/剧本相关自动降级）
uvicorn app.main:app --reload --port 8000
```

启动后打开 http://127.0.0.1:8000/docs 查看 Swagger 接口文档。

**端到端冒烟测试**（另开一个终端，先改脚本顶部 CONFIG 区的照片路径）：

```bash
python scripts/e2e_test.py                # 全链路（含视频生成）
python scripts/e2e_test.py --skip-video   # 跳过视频，快速冒烟
```

## 测试流程

> 前提：已完成「快速开始」（依赖装好、`.env` 配好 key、后端已 `uvicorn` 起在 8000）。
> 生图走 CogView-3-Flash + rembg 抠透明，单次请求 10~30s；首次 rembg 会加载 u2net 权重（已缓存在 `.cache/u2net/`）。

### 0. 健康检查

```bash
curl -s http://127.0.0.1:8000/api/health
# 期望：{"status":"ok","zhipu_key_configured":true,"models":{...}}
```

`zhipu_key_configured: false` → `.env` 的 key 没生效，生图会走兜底（纸娃娃/AnimeGAN）。

### 1. 自动端到端冒烟

改 `scripts/e2e_test.py` 顶部 CONFIG 区的照片路径，然后：

```bash
python scripts/e2e_test.py --skip-video   # 快速冒烟（跳过视频）
python scripts/e2e_test.py                # 全链路（含视频，慢）
```

覆盖 analyze → compose → 换装 → 背景 → 游戏 → 视频。主图走 CogView+rembg（GLM-4V 特征→GLM-4 扩写→写死 Q版卡通风→CogView→rembg 抠透明）。

### 2. 手动分步验证（curl）

准备默认特征 JSON（或先 `POST /avatars/analyze` 上传照片拿真实特征）：

```bash
FEAT='{"gender_style":"neutral","age_group":"young_adult","face_shape":"oval","hair_style":"short","hair_color":"black","glasses":"none","expression":"happy","skin_tone":"light","accessories":[],"outfit":"cape","notes":""}'
```

**a) 形象合成**（CogView + rembg，~12~30s）→ 512×512 透明 PNG：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/avatars/compose \
  -H 'Content-Type: application/json' \
  -d "{\"features\":$FEAT}" | python -m json.tool
```

**b) 背景生成**（用户 prompt → CogView，~20s）→ 1024×1024 背景 + 场景标签：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/backgrounds/cartoonize \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"校园操场，阳光明媚"}' | python -m json.tool
```

**c) 游戏素材包**（CogView 精灵 + rembg，~45s）→ 96×96 透明精灵 + 角色跑跳帧：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/games/package \
  -H 'Content-Type: application/json' \
  -d '{"avatar_id":"<a 的 avatar_id>","background_id":"<b 的 background_id>","difficulty":"normal"}' \
  | python -m json.tool
```

**d) 视频**（异步，CogVideoX-Flash 文生视频，~1-3 分钟）：`POST /api/v1/videos/generate` 传 `photo_ids` + `theme`（`avatar_id`/`with_narration` 等兼容保留但忽略），拿 `job_id` 后轮询：

```bash
curl -s http://127.0.0.1:8000/api/v1/videos/<job_id> | python -m json.tool
# status: processing → done；done 后取 video.url（mp4，含 AI 音效）
```

### 3. 兜底/降级测试

把 `.env` 的 `NAILONG_ZHIPU_API_KEY` 改成无效值，重启后端，再跑 a/b：

- 应仍返回 **HTTP 200**（不报 500）；
- 形象回退纸娃娃、背景回退 AnimeGAN/cv2；
- 后端日志出现 `CogView ... 生成失败，回退` 警告。

验完改回真 key 重启。

### 4. 产物自检

- `image.url`（`/static/outputs/avatars/<id>.png`）：用 PIL 看应 `mode=RGBA`、四周透明、主体居中；CogView 插画风、文件 ~100KB+（区别于纸娃娃兜底 ~6KB）。
- 游戏精灵（`/static/outputs/games/<gid>/obstacle_*.png`）：96×96 RGBA 透明。
- 后端日志无 `回退` 警告 = 主路径（CogView+rembg）正常跑通。

## 接口一览（v1 契约已冻结）

详细字段/枚举/示例见 **[docs/api.md](docs/api.md)**（给前端的接口文档）。

| 模块 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 上传 | POST | `/api/v1/uploads` | 上传照片 → photo_id + URL |
| 形象 | POST | `/api/v1/avatars/analyze` | 照片 → MediaPipe 信号 + GLM-4V 结构化五官特征 |
| 形象 | POST | `/api/v1/avatars/compose` | 特征 JSON → 形象 PNG（CogView 生图 + rembg 抠透明，失败回退纸娃娃） |
| 形象 | PUT | `/api/v1/avatars/{avatar_id}/outfit` | 换装/换发型/换表情 |
| 形象 | GET | `/api/v1/assets/wardrobe` | 可换装部件清单 |
| 背景 | POST | `/api/v1/backgrounds/cartoonize` | 用户 prompt → CogView 生图 + GLM-4 场景标签 |
| 游戏 | POST | `/api/v1/games/package` | 形象+背景+难度 → 素材包+关卡配置 |
| 游戏 | POST/GET | `/api/v1/games/scores` `/api/v1/games/leaderboard` | 免登录排行榜（SQLite 持久化） |
| 视频 | POST | `/api/v1/videos/generate` | 照片→GLM-4 剧本→CogVideoX-Flash 文生视频（异步，~1-3 分钟） |
| 视频 | GET | `/api/v1/videos/{job_id}` | 任务状态/进度/成片地址 |

## 目录说明

```
app/
├── main.py          # FastAPI 入口（CORS、静态目录、路由）
├── config.py        # pydantic-settings 配置（.env）；模型缓存收进项目 .cache/
├── schemas/         # ★ 接口契约：pydantic 模型 + 枚举（前后端共用词汇表）
│   ├── common.py    #   统一响应包装、图片资源引用
│   ├── avatar.py    #   五官特征 JSON（核心契约）
│   ├── background.py#   场景标签
│   ├── game.py      #   游戏素材包/关卡配置/排行榜
│   └── video.py     #   分镜剧本/任务状态
├── api/v1/          # 路由层（接 services 真实实现）
├── services/        # MediaPipe 人脸/纸娃娃合成/AnimeGANv2/游戏打包/视频渲染/智谱API
├── assets/          # 奶龙图层素材库、游戏精灵、字体、模型权重
└── storage/         # uploads/（上传）、outputs/（生成结果，/static 挂载）
docs/api.md          # 前端接口文档
scripts/e2e_test.py  # 端到端冒烟测试脚本
```

## 同步与部署

- **代码**：走 GitHub 私有仓库（`git pull/push`），版本管理与协作。
- **完整运行环境**（含项目内 `.cache/` 模型缓存、`storage/` 产物、`.env`）：不进 git，
  直接在服务器与本地之间拷贝整个项目目录。

### 下载到本地（在自己电脑的终端执行）

```bash
scp -rC <服务器登录>:/root/ND/nailong-backend ./
```

- 只要 `nailong-backend` 这一个目录（约 51MB）；`scp -r` 会连隐藏目录一起拷，
  项目内 `.cache/` 里的 AnimeGANv2 权重自动带上，本地不用重下。
- **不要**拷 `/root/ND/.cache/`（约 2.9GB，那是 pip 装包的 wheel 缓存，
  本地 `pip install` 会自己重新下载）。
- 以后增量同步（只传差异）可用：`rsync -avz --progress <服务器登录>:/root/ND/nailong-backend/ ./nailong-backend/`

### 本地首次配置

```bash
cd nailong-backend
conda create -n ND python=3.10 -y && conda activate ND   # 已有 ND 环境则跳过创建

# 有 NVIDIA 显卡：先装 CUDA 版 torch
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt        # 无独显直接跑这步即可（装 CPU 版 torch）

cp .env.example .env                   # 然后编辑 .env：
#   NAILONG_ZHIPU_API_KEY=你的key      # 智谱控制台 https://www.bigmodel.cn/ → API keys
#   NAILONG_DEVICE=cpu                 # 仅无独显时加这行

uvicorn app.main:app --port 8000
```

验证：浏览器打开 http://127.0.0.1:8000/docs ；再改 `scripts/e2e_test.py`
顶部 CONFIG 区的照片路径，跑 `python scripts/e2e_test.py --skip-video` 冒烟。

> 不填 API key 也能启动，VLM/剧本相关步骤会自动降级走默认结果；
> 访问 `GET /api/health` 可看 `zhipu_key_configured` 确认 key 是否生效。
