"""FastAPI application: REST API, SSE progress stream and static frontend."""
from __future__ import annotations

import json
import logging
import os
import queue
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, engine, jobs, plan
from .catalog import (
    BASE_MODELS,
    CATEGORIES,
    LORAS,
    POST_LABELS,
    style_by_id,
)
from .catalog import STYLES

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("spriteforge")

app = FastAPI(title="SpriteForge", version="1.0.0", docs_url="/api/docs")


# ------------------------------------------------------------- schemas ------


class GenerateBody(BaseModel):
    prompt: str = ""
    negative: str = ""
    extra_prompt: str = ""
    category: str = "prop"
    style: str = "pixel16"
    base: str | None = None
    loras: list[str] = Field(default_factory=list)
    lora_weight: float | None = None
    seed: int | None = None
    steps: int | None = None
    cfg: float | None = None
    size: int | None = None
    batch: int = 1
    scheduler: str = "default"
    post: list[str] | None = None
    pixel_size: int = 64
    palette_colors: int = 16
    tolerance: int = 42
    sheet_cols: int = 4
    sheet_rows: int = 4
    use_style_prompt: bool = True
    use_style_negative: bool = True
    use_style_loras: bool = True
    use_common_negative: bool = True


# ------------------------------------------------------------- helpers ------


def _resolve_output_path(rel: str) -> Path:
    """Resolve a relative path inside the output tree, blocking traversal."""
    normalised = rel.replace("\\", "/")
    parts = [p for p in normalised.split("/") if p not in ("", ".", "..")]
    if not parts:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if any(p.startswith(".") or ":" in p for p in parts):
        raise HTTPException(status_code=400, detail="Некорректное имя файла")
    for base in sorted(config.OUTPUT_DIR.iterdir(), reverse=True):
        if not base.is_dir():
            continue
        candidate = base.joinpath(*parts)
        if candidate.is_file():
            return candidate
    direct = config.OUTPUT_DIR.joinpath(*parts)
    if direct.is_file():
        return direct
    raise HTTPException(status_code=404, detail="Файл не найден")


# --------------------------------------------------------------- routes -----


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "engine": engine.status(),
        "queue_depth": jobs._JOB_QUEUE.qsize(),
        "models_dir": str(config.MODELS_DIR),
        "output_dir": str(config.OUTPUT_DIR),
    }


@app.get("/api/catalog")
def catalog() -> dict:
    return {
        "styles": [
            {
                "id": s.id,
                "label": s.label,
                "base": s.base,
                "base_label": BASE_MODELS[s.base].label,
                "loras": [
                    {
                        "id": lid,
                        "label": l.label,
                        "weight": l.weight,
                        "trigger": l.trigger,
                        "size_gb": l.size_gb,
                    }
                    for lid in s.loras
                    if (l := LORAS.get(lid))
                ],
                "categories": list(s.categories),
                "post": list(s.post),
                "swatch": s.swatch,
                "tags": list(s.tags),
                "size": s.size,
                "steps": s.steps,
                "cfg": s.cfg,
                "note": s.note,
            }
            for s in STYLES
        ],
        "categories": [
            {
                "id": c["id"],
                "label": c["label"],
                "hint": c["hint"],
                "size": c["size"],
                "post": list(c.get("post", ())),
                "template": c["template"],
            }
            for c in CATEGORIES
        ],
        "bases": [
            {
                "id": b.id,
                "label": b.label,
                "repo": b.repo,
                "size_gb": b.size_gb,
                "steps": b.default_steps,
                "cfg": b.default_cfg,
                "note": b.note,
            }
            for b in BASE_MODELS.values()
        ],
        "loras": [
            {
                "id": l.id,
                "label": l.label,
                "repo": l.repo,
                "base": l.base,
                "trigger": l.trigger,
                "weight": l.weight,
                "size_gb": l.size_gb,
                "license": l.license,
            }
            for l in LORAS.values()
        ],
        "post_labels": POST_LABELS,
        "sizes": list(config.ALLOWED_SIZES),
    }


@app.post("/api/prompt/preview")
def preview_prompt(body: GenerateBody) -> dict:
    payload = body.model_dump()
    prompt, negative, meta = jobs.build_prompt(payload)
    loras = jobs.resolve_loras(payload, meta)
    return {
        "prompt": prompt,
        "negative": negative,
        "meta": meta,
        "loras": [{"id": lid, "weight": w, "label": LORAS[lid].label} for lid, w in loras],
    }


@app.post("/api/generate")
def generate(body: GenerateBody) -> dict:
    if not (body.prompt or body.extra_prompt).strip():
        raise HTTPException(status_code=400, detail="Введите описание: за что генерировать")
    style = style_by_id(body.style)
    if style and body.base is None:
        body.base = style.base
    if body.base and body.base not in BASE_MODELS:
        raise HTTPException(status_code=400, detail=f"Неизвестная база: {body.base}")
    if body.batch < 1 or body.batch > config.MAX_BATCH:
        raise HTTPException(status_code=400, detail=f"Батч должен быть 1..{config.MAX_BATCH}")
    if body.size and body.size not in config.ALLOWED_SIZES:
        raise HTTPException(status_code=400, detail=f"Размер должен быть одним из {config.ALLOWED_SIZES}")
    if body.size is None and style:
        body.size = style.size
    job = jobs.submit(body.model_dump())
    return job.snapshot()


@app.get("/api/jobs")
def list_jobs(limit: int = 40) -> dict:
    return {"jobs": jobs.list_jobs(limit)}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return job.snapshot()


@app.get("/api/stream/{job_id}")
def stream_job(job_id: str) -> StreamingResponse:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    def gen():
        for ev in job.stream():
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/events")
def events() -> StreamingResponse:
    lq = jobs.subscribe()

    def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    ev = lq.get(timeout=15)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            jobs.unsubscribe(lq)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/gallery")
def gallery(limit: int = 60, category: str | None = None) -> dict:
    return {"items": jobs.gallery(limit=limit, category=category)}


@app.delete("/api/gallery/{item_id}")
def delete_item(item_id: str) -> dict:
    removed = False
    for rec in list(jobs._INDEX):
        if rec.get("id") == item_id:
            jobs._INDEX.remove(rec)
            removed = True
    if removed:
        jobs._save_index()
    return {"ok": removed}


@app.get("/api/assets/{rel:path}")
def get_asset(rel: str) -> FileResponse:
    path = _resolve_output_path(rel)
    suffix = path.suffix.lower()
    media = {
        ".png": "image/png",
        ".webp": "image/webp",
        ".json": "application/json",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media, filename=path.name)


@app.get("/api/zip/{name}")
def zip_asset(name: str) -> Response:
    """Bundle a whole generation (main + frames + atlas + metadata) as a zip."""
    import io
    import zipfile

    stem = Path(name).stem
    buf = io.BytesIO()
    found = False
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for base in sorted(config.OUTPUT_DIR.iterdir(), reverse=True):
            if not base.is_dir():
                continue
            files = [p for p in base.glob(stem + "*") if p.is_file()]
            frame_dirs = [p for p in base.glob(stem + "_frames") if p.is_dir()]
            if not files and not frame_dirs:
                continue
            found = True
            for f in files:
                zf.write(f, f.name)
            for d in frame_dirs:
                for f in d.glob("*.png"):
                    zf.write(f, f"{d.name}/{f.name}")
    if not found:
        raise HTTPException(status_code=404, detail="Набор не найден")
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{stem}.zip"'},
    )


@app.get("/api/models")
def models() -> dict:
    return engine.status()


@app.post("/api/models/unload")
def unload() -> dict:
    engine.unload()
    return {"ok": True, "engine": engine.status()}


# ------------------------------------------------------ roadmap widget ------

PLAN_BODY_KEYS = frozenset(
    {
        "done",
        "counters",
        "notes",
        "picks",
        "custom",
        "customDelete",
        "opened",
        "daily",
        "streak",
        "bestStreak",
        "lastDay",
        "surpriseTask",
        "log",
        "gameTitle",
        "gameIdea",
        "dailyNote",
        "sessionNote",
    }
)


@app.get("/api/plan")
def get_plan() -> dict:
    return plan.load()


@app.put("/api/plan")
def put_plan(body: dict[str, Any]) -> dict:
    return plan.update({k: v for k, v in (body or {}).items() if k in PLAN_BODY_KEYS})


@app.post("/api/plan/import")
def import_plan(body: dict[str, Any]) -> dict:
    payload = body.get("state") if isinstance(body, dict) else None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Нужен объект state")
    return plan.replace(payload)


@app.post("/api/plan/reset")
def reset_plan() -> dict:
    return plan.reset()


# ----------------------------------------------------------- static site ----

if config.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")
