"""动画视频生成（真实实现）：异步任务 + 状态轮询"""
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ...schemas.common import ImageRef
from ...schemas.video import JobStatus, Scene, VideoGenerateRequest, VideoJobResponse
from ...services import store, video_renderer

log = logging.getLogger(__name__)
router = APIRouter()


def _job_path(job_id: str):
    return store.output_dir("videos/jobs") / f"{job_id}.json"


def _save_job(job: VideoJobResponse) -> None:
    store.save_json(_job_path(job.job_id), job)


@router.post("/videos/generate", response_model=VideoJobResponse,
             summary="提交视频生成任务（异步，轮询 /videos/{job_id} 取结果）")
def generate_video(req: VideoGenerateRequest, background_tasks: BackgroundTasks) -> VideoJobResponse:
    paths, missing = [], []
    for pid in req.photo_ids:
        p = store.find_upload(pid)
        (paths.append(p) if p else missing.append(pid))
    if missing:
        raise HTTPException(404, f"照片不存在: {missing}（先 POST /uploads）")

    job = VideoJobResponse(job_id=store.new_id(), status=JobStatus.pending,
                           progress=0.0, stage="排队中")
    _save_job(job)
    background_tasks.add_task(_run_pipeline, job.job_id, req, paths)
    return job


@router.get("/videos/{job_id}", response_model=VideoJobResponse, summary="查询任务状态/结果")
def get_video_job(job_id: str) -> VideoJobResponse:
    p = _job_path(job_id)
    if not p.exists():
        raise HTTPException(404, f"任务不存在: {job_id}")
    return VideoJobResponse(**store.load_json(p))


def _run_pipeline(job_id: str, req: VideoGenerateRequest, paths) -> None:
    job = VideoJobResponse(**store.load_json(_job_path(job_id)))
    job.status = JobStatus.processing

    def on_progress(stage: str, progress: float, storyboard: list[Scene] | None = None):
        job.stage, job.progress = stage, round(progress, 3)
        if storyboard is not None:
            job.storyboard = storyboard
        _save_job(job)

    try:
        _save_job(job)
        final, scenes = video_renderer.render_video(job_id, req, paths, on_progress)
        job.status = JobStatus.done
        job.progress = 1.0
        job.stage = "完成"
        job.storyboard = scenes
        job.video = ImageRef(id=job_id, url=store.url_of(final))
    except Exception as e:
        log.exception("视频任务 %s 失败", job_id)
        job.status = JobStatus.failed
        job.stage = "失败"
        job.error = f"{type(e).__name__}: {e}"
    _save_job(job)
