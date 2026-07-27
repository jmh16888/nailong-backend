"""游戏素材包 + 免登录排行榜（SQLite 持久化）"""
import sqlite3
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from ...config import settings
from ...schemas.background import SceneTags
from ...schemas.game import (
    Difficulty, GamePackageRequest, GamePackageResponse,
    LeaderboardEntry, LeaderboardResponse, ScoreSubmit,
)
from ...services import game_packager, store

router = APIRouter()


@router.post("/games/package", response_model=GamePackageResponse,
             summary="形象+背景+难度 → 游戏素材包 + 关卡配置")
def create_game_package(req: GamePackageRequest) -> GamePackageResponse:
    avatar_png = store.output_dir("avatars") / f"{req.avatar_id}.png"
    if not avatar_png.exists():
        raise HTTPException(404, f"形象不存在: {req.avatar_id}（先 /avatars/compose）")
    bg_png = store.output_dir("backgrounds") / f"{req.background_id}.png"
    if not bg_png.exists():
        raise HTTPException(404, f"背景不存在: {req.background_id}（先 /backgrounds/cartoonize）")

    scene = None
    bg_json = bg_png.with_suffix(".json")
    if bg_json.exists():
        scene = SceneTags(**store.load_json(bg_json))

    return game_packager.build_package(
        game_id=store.new_id(),
        avatar_path=avatar_png,
        background_path=bg_png,
        scene=scene,
        difficulty=req.difficulty,
        duration_sec=req.duration_sec,
        heart_count=req.heart_count,
        coin_count=req.coin_count,
    )


# ---------- 排行榜（免登录，SQLite） ----------

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.storage_dir / "leaderboard.db")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS scores ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " nickname TEXT NOT NULL, score INTEGER NOT NULL,"
        " difficulty TEXT NOT NULL, game_id TEXT,"
        " created_at TEXT NOT NULL)"
    )
    return conn


@router.post("/games/scores", response_model=LeaderboardEntry, summary="提交分数（免登录）")
def submit_score(req: ScoreSubmit) -> LeaderboardEntry:
    now = datetime.now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO scores(nickname, score, difficulty, game_id, created_at)"
            " VALUES (?,?,?,?,?)",
            (req.nickname, req.score, req.difficulty.value, req.game_id,
             now.isoformat(timespec="seconds")),
        )
        # 名次 = 同难度下分数更高的人数 + 1（同分按时间先者优先，近似展示）
        (rank,) = conn.execute(
            "SELECT COUNT(*)+1 FROM scores WHERE difficulty=? AND ("
            " score>? OR (score=? AND created_at<?))",
            (req.difficulty.value, req.score, req.score, now.isoformat(timespec="seconds")),
        ).fetchone()
    return LeaderboardEntry(rank=rank, nickname=req.nickname, score=req.score,
                            difficulty=req.difficulty, created_at=now)


@router.get("/games/leaderboard", response_model=LeaderboardResponse, summary="排行榜")
def leaderboard(
    difficulty: Difficulty = Query(Difficulty.normal),
    limit: int = Query(20, ge=1, le=100),
) -> LeaderboardResponse:
    with _db() as conn:
        rows = conn.execute(
            "SELECT nickname, score, difficulty, created_at FROM scores"
            " WHERE difficulty=? ORDER BY score DESC, created_at ASC LIMIT ?",
            (difficulty.value, limit),
        ).fetchall()
    return LeaderboardResponse(entries=[
        LeaderboardEntry(rank=i + 1, nickname=r[0], score=r[1],
                         difficulty=Difficulty(r[2]), created_at=datetime.fromisoformat(r[3]))
        for i, r in enumerate(rows)
    ])
