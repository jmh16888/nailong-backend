"""全局配置：从 .env 读取，前缀 NAILONG_"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # nailong-backend/

# 所有模型下载/缓存一律收进项目目录（服务器开发 → 本地部署整体拷贝即可，
# 不会散落 ~/.cache 等位置）。在 import torch 等库之前设置才有效。
_CACHE = BASE_DIR / ".cache"
os.environ.setdefault("TORCH_HOME", str(_CACHE / "torch"))        # torch.hub（AnimeGANv2 权重）
os.environ.setdefault("HF_HOME", str(_CACHE / "huggingface"))     # HuggingFace 缓存（备用）
os.environ.setdefault("U2NET_HOME", str(_CACHE / "u2net"))        # rembg 抠图模型


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_prefix="NAILONG_", extra="ignore")

    # ---- 智谱开放平台（免费模型三件套）----
    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"
    vlm_model: str = "glm-4v-flash"        # 图像理解（完全免费）
    llm_model: str = "glm-4-flash"         # 文本生成：剧本/游戏配置（免费）
    image_gen_model: str = "cogview-3-flash"  # 文生图：素材制作/精致版彩蛋（免费）
    cogvideo_model: str = "cogvideox-flash"  # 文生视频（免费，纯文本→mp4）

    # ---- 限流（按控制台"速率限制"页调整）----
    api_concurrency: int = 2               # 免费模型并发较低，别贪
    api_max_retries: int = 5

    # ---- 本地资源 ----
    storage_dir: Path = BASE_DIR / "app" / "storage"   # 上传与生成结果
    assets_dir: Path = BASE_DIR / "app" / "assets"     # 奶龙图层素材库/精灵/字体
    animegan_weight: str = "animeganv2_hayao.pt"       # 放 assets/weights/ 下
    device: str = "cuda"                    # 无独显改 "cpu"（AnimeGAN 也能跑）

    # ---- 服务 ----
    cors_origins: list[str] = ["*"]         # 开发期放开，上线收紧

    def ensure_dirs(self) -> None:
        for sub in ("uploads", "outputs"):
            (self.storage_dir / sub).mkdir(parents=True, exist_ok=True)
        (self.assets_dir / "weights").mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
