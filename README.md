# nailong-backend

照片转奶龙卡通系统 —— 后端（FastAPI）

## 快速开始（mock 联调阶段）

```bash
conda create -n nailong python=3.10 -y && conda activate nailong
pip install -r requirements.txt
cp .env.example .env        # 填入智谱 API Key（mock 阶段不填也能跑）
uvicorn app.main:app --reload --port 8000
```

启动后打开 http://127.0.0.1:8000/docs 查看 Swagger 接口文档（全部接口已定义，当前返回 mock 数据）。

## 接口一览（v1 契约已冻结）

| 模块 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 上传 | POST | `/api/v1/uploads` | 上传照片 → photo_id + URL（真实可用） |
| 形象 | POST | `/api/v1/avatars/analyze` | 照片 → 结构化五官特征 JSON |
| 形象 | POST | `/api/v1/avatars/compose` | 特征 JSON → 奶龙形象 PNG |
| 形象 | PUT | `/api/v1/avatars/{avatar_id}/outfit` | 换装/换发型/换表情 |
| 形象 | GET | `/api/v1/assets/wardrobe` | 可换装部件清单 |
| 背景 | POST | `/api/v1/backgrounds/cartoonize` | 照片 → 卡通背景 + 场景标签 |
| 游戏 | POST | `/api/v1/games/package` | 形象+背景+难度 → 素材包+关卡配置 |
| 游戏 | POST/GET | `/api/v1/games/scores` `/api/v1/games/leaderboard` | 免登录排行榜（内存版已可用，后续换 SQLite） |
| 视频 | POST | `/api/v1/videos/generate` | 照片列表 → 动画视频任务 |
| 视频 | GET | `/api/v1/videos/{job_id}` | 任务状态/进度/成片地址 |

## 目录说明

```
app/
├── main.py          # FastAPI 入口（CORS、静态目录、路由）
├── config.py        # pydantic-settings 配置（.env）
├── schemas/         # ★ 接口契约：pydantic 模型 + 枚举（前后端共用词汇表）
│   ├── common.py    #   统一响应包装、图片资源引用
│   ├── avatar.py    #   五官特征 JSON（核心契约）
│   ├── background.py#   场景标签
│   ├── game.py      #   游戏素材包/关卡配置/排行榜
│   └── video.py     #   分镜剧本/任务状态
├── api/v1/          # 路由（当前为 mock 实现，标记 TODO 处接入真实服务）
├── services/        # （下一步）VLM/图像处理/视频渲染等真实实现
├── assets/          # 奶龙图层素材库、游戏精灵、字体
└── storage/         # uploads/（上传）、outputs/（生成结果，/static 挂载）
```

## mock 说明

- 所有接口按 schemas 返回示例数据，图片 URL 为占位路径（前端可正常走通流程）；
- `POST /api/v1/uploads` 和排行榜两个接口是真实实现，可直接用；
- 路由里的 `TODO` 注释标明了后续接入真实服务的位置。
