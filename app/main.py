"""FastAPI 入口：CORS、静态目录、路由挂载。

启动：uvicorn app.main:app --reload --port 8000
文档：http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.v1 import avatars, backgrounds, games, uploads, videos
from .config import settings

app = FastAPI(
    title="照片转奶龙卡通系统 API",
    version="0.1.0",
    description=(
        "后端接口 v1（契约已冻结，当前为 mock 实现）。\n\n"
        "模块：奶龙形象生成/换装 · 背景卡通化 · 游戏素材包/排行榜 · 动画视频生成"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 生成结果/上传文件的静态访问：/static/uploads/xxx.jpg, /static/outputs/xxx.png
app.mount("/static", StaticFiles(directory=settings.storage_dir), name="static")
# 素材库静态访问（衣橱部件预览等）：/assets/nailong/glasses/round.png
settings.assets_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=settings.assets_dir), name="assets")

app.include_router(uploads.router, prefix="/api/v1", tags=["上传"])
app.include_router(avatars.router, prefix="/api/v1", tags=["奶龙形象"])
app.include_router(backgrounds.router, prefix="/api/v1", tags=["背景卡通化"])
app.include_router(games.router, prefix="/api/v1", tags=["游戏"])
app.include_router(videos.router, prefix="/api/v1", tags=["动画视频"])


@app.get("/api/health", tags=["系统"])
def health() -> dict:
    return {
        "status": "ok",
        "zhipu_key_configured": bool(settings.zhipu_api_key),
        "models": {
            "vlm": settings.vlm_model,
            "llm": settings.llm_model,
            "image_gen": settings.image_gen_model,
        },
    }
