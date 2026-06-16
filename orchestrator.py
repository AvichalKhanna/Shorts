"""
FastAPI web service for the YouTube Shorts pipeline.

POST /run        { "url": "https://..." }   → run pipeline for specific URL
POST /run        { "url": "upload_random" } → pull from queue and run pipeline
GET  /status/:id                            → poll job status + result URL
GET  /logs/:id                              → SSE stream of live logs
GET  /jobs                                  → list all jobs
"""

import asyncio
import re
import random
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── Your existing modules ─────────────────────────────────────────────────────
from portfolio import get_portfolio, Portfolio
from recorder import record_portfolio
from generate_script import process_portfolio as generate_script
from generate_speech import generate_speech
from subtitles import process_video
from verify_portfolio import verify_portfolio
from upload_video import upload_video

# ── Config ────────────────────────────────────────────────────────────────────
OUTPUT_DIR  = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
MAX_RETRIES = 5

# ── In-memory job store ───────────────────────────────────────────────────────
# { job_id: { status, url, result_url, error, logs: [], created_at } }
jobs: dict[str, dict] = {}

# SSE subscriber queues: { job_id: [asyncio.Queue, ...] }
log_subscribers: dict[str, list[asyncio.Queue]] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def clean_script(script: str) -> str:
    script = re.sub(r'[-–—*#\[\]()]', '', script)
    script = re.sub(r'\*\*.*?\*\*', '', script)
    script = re.sub(r' +', ' ', script)
    script = re.sub(r'\n+', '\n', script)
    return script.strip()


def push_log(job_id: str, message: str):
    """Append a log line to the job and notify any SSE subscribers."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}"
    jobs[job_id]["logs"].append(line)
    for q in log_subscribers.get(job_id, []):
        q.put_nowait(line)
    print(f"[{job_id[:8]}] {message}")


async def get_valid_portfolio(job_id: str, portfolio_url: Optional[str]) -> Portfolio:
    if portfolio_url:
        portfolio = Portfolio(url=portfolio_url, source="cli")
        result = verify_portfolio(portfolio)
        if not result.is_valid:
            push_log(job_id, f"⚠️  URL failed verification ({result.reason}) — continuing anyway")
        return portfolio

    for attempt in range(1, MAX_RETRIES + 1):
        push_log(job_id, f"📦 Fetching portfolio from queue (attempt {attempt}/{MAX_RETRIES})...")
        portfolio = get_portfolio()
        push_log(job_id, f"🌐 Got: {portfolio.url}")
        result = verify_portfolio(portfolio)
        if result.is_valid:
            push_log(job_id, "✅ Portfolio passed verification")
            return portfolio
        push_log(job_id, f"❌ Failed: {result.reason} — trying next...")

    raise RuntimeError(f"No valid portfolio found after {MAX_RETRIES} attempts")


async def run_pipeline(job_id: str, portfolio_url: Optional[str]):
    """Full pipeline — runs in a background task."""
    job = jobs[job_id]
    job["status"] = "running"

    try:
        # Step 1 ─ Get portfolio
        push_log(job_id, "▶ Step 1/6 — Getting portfolio...")
        portfolio = await get_valid_portfolio(job_id, portfolio_url)
        job["url"] = portfolio.url
        push_log(job_id, f"🌐 Portfolio: {portfolio.url}")
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', portfolio.url.split("//")[-1]).strip('-').lower()

        # Step 2 ─ Record
        push_log(job_id, "▶ Step 2/6 — Recording website...")
        video_path = await record_portfolio(portfolio, phone=False)
        push_log(job_id, f"✅ Video: {video_path}")

        # Step 3 ─ Generate script
        push_log(job_id, "▶ Step 3/6 — Generating script...")
        raw_script = generate_script(str(video_path))
        script = clean_script(raw_script)
        script_path = OUTPUT_DIR / f"{slug}_script.txt"
        script_path.write_text(script, encoding="utf-8")
        push_log(job_id, f"✅ Script saved ({len(script)} chars)")

        # Step 4 ─ Generate speech
        push_log(job_id, "▶ Step 4/6 — Generating voiceover...")
        audio_path = str(OUTPUT_DIR / f"{slug}_audio.wav")
        generate_speech(script, output_file=audio_path)
        push_log(job_id, f"✅ Audio saved: {audio_path}")

        # Step 5 ─ Burn subtitles
        push_log(job_id, "▶ Step 5/6 — Rendering final video with subtitles...")
        final_path = str(OUTPUT_DIR / f"{slug}_final.mp4")
        process_video(str(video_path), audio_path, output_file=final_path)
        push_log(job_id, f"✅ Final video: {final_path}")

        # Step 6 ─ Upload
        push_log(job_id, "▶ Step 6/6 — Uploading to YouTube...")
        title = f"Rating {portfolio.url.split('//')[1].split('/')[0]}'s Portfolio 👀"
        result = upload_video(
            video_path=final_path,
            title=title,
            description=f"Reviewing {portfolio.url}\n",
        )
        youtube_url = result["url"]
        push_log(job_id, f"✅ Uploaded: {youtube_url}")

        job["status"]     = "done"
        job["result_url"] = youtube_url

    except Exception as e:
        push_log(job_id, f"💥 Pipeline failed: {e}")
        job["status"] = "failed"
        job["error"]  = str(e)

    finally:
        # Signal all SSE subscribers that the stream is over
        for q in log_subscribers.pop(job_id, []):
            q.put_nowait(None)   # sentinel → close SSE


# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield   # nothing to set up / tear down for now

app = FastAPI(title="Shorts Pipeline API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / response models ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    url: str   # "upload_random" OR a real portfolio URL


class JobResponse(BaseModel):
    job_id:     str
    status:     str
    url:        Optional[str] = None
    result_url: Optional[str] = None
    error:      Optional[str] = None
    logs:       list[str]     = []
    created_at: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/run", response_model=JobResponse, status_code=202)
async def start_run(body: RunRequest):
    """
    Kick off the pipeline.
    - url = "upload_random"  → pull from queue
    - url = "https://..."    → run for that specific URL
    """
    job_id = str(uuid.uuid4())
    portfolio_url = None if body.url.strip().lower() == "upload_random" else body.url.strip()

    jobs[job_id] = {
        "status":     "queued",
        "url":        portfolio_url,
        "result_url": None,
        "error":      None,
        "logs":       [],
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    # Fire-and-forget — don't await
    asyncio.create_task(run_pipeline(job_id, portfolio_url))

    return JobResponse(job_id=job_id, **{k: v for k, v in jobs[job_id].items() if k != "job_id"})


@app.get("/status/{job_id}", response_model=JobResponse)
async def get_status(job_id: str):
    """Poll job status. Returns result_url when status == 'done'."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return JobResponse(job_id=job_id, **{k: v for k, v in job.items() if k != "job_id"})


@app.get("/logs/{job_id}")
async def stream_logs(job_id: str):
    """
    Server-Sent Events stream of live pipeline logs.
    Connect immediately after POST /run; closes automatically when pipeline finishes.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        # First, replay any logs already emitted
        for line in jobs[job_id]["logs"]:
            yield f"data: {line}\n\n"

        # If job is already finished, close immediately
        if jobs[job_id]["status"] in ("done", "failed"):
            yield "event: close\ndata: stream ended\n\n"
            return

        # Subscribe for future log lines
        q: asyncio.Queue = asyncio.Queue()
        log_subscribers.setdefault(job_id, []).append(q)

        try:
            while True:
                line = await q.get()
                if line is None:   # sentinel — pipeline finished
                    yield "event: close\ndata: stream ended\n\n"
                    break
                yield f"data: {line}\n\n"
        finally:
            subs = log_subscribers.get(job_id, [])
            if q in subs:
                subs.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/jobs")
async def list_jobs():
    """List all jobs with their current status."""
    return [
        {"job_id": jid, **{k: v for k, v in job.items() if k != "logs"}}
        for jid, job in reversed(list(jobs.items()))
    ]


@app.get("/health")
async def health():
    return {"status": "ok", "jobs_in_memory": len(jobs)}