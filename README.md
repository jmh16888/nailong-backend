# nailong-backend

照片转奶龙卡通系统 —— 后端（FastAPI）

## 快速开始

```bash
conda activate DN        # 或新建：conda create -n DN python=3.10 -y
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

## 接口一览（v1 契约已冻结）

详细字段/枚举/示例见 **[docs/api.md](docs/api.md)**（给前端的接口文档）。

| 模块 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 上传 | POST | `/api/v1/uploads` | 上传照片 → photo_id + URL |
| 形象 | POST | `/api/v1/avatars/analyze` | 照片 → MediaPipe 信号 + GLM-4V 结构化五官特征 |
| 形象 | POST | `/api/v1/avatars/compose` | 特征 JSON → 奶龙形象 PNG（纸娃娃合成） |
| 形象 | PUT | `/api/v1/avatars/{avatar_id}/outfit` | 换装/换发型/换表情 |
| 形象 | GET | `/api/v1/assets/wardrobe` | 可换装部件清单 |
| 背景 | POST | `/api/v1/backgrounds/cartoonize` | AnimeGANv2 卡通化 + GLM-4V 场景标签 |
| 游戏 | POST | `/api/v1/games/package` | 形象+背景+难度 → 素材包+关卡配置 |
| 游戏 | POST/GET | `/api/v1/games/scores` `/api/v1/games/leaderboard` | 免登录排行榜（SQLite 持久化） |
| 视频 | POST | `/api/v1/videos/generate` | 照片列表 → 动画视频任务（异步） |
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
- **完整运行环境**（含 `.cache/` 模型缓存、`storage/` 产物、`.env`）：不进 git，
  用 rsync 在服务器与本地之间直传（在**本地机器**上执行）：

```bash
rsync -avz --progress <服务器登录>:/root/ND/nailong-backend/ ./nailong-backend/
```

重跑同一条命令即增量同步。本地拿到后按"快速开始"装依赖即可跑，
`TORCH_HOME` 等已指向项目内 `.cache/`，AnimeGANv2 权重不用重下。
