"""Background job queue with progress streaming and asset storage."""
from __future__ import annotations

import json
import queue
import re
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from PIL import Image

from . import config, engine, postprocess
from .catalog import (
    CATEGORY_BY_ID,
    COMMON_NEGATIVE,
    LORAS,
    POST_LABELS,
    base_by_id,
    lora_by_id,
    style_by_id,
)

# ------------------------------------------------------------------ jobs ----


@dataclass
class Job:
    id: str
    payload: dict[str, Any]
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0.0
    message: str = "В очереди"
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    error: str | None = None
    result: dict | None = None
    _events: list[dict] = field(default_factory=list)
    _cond: threading.Condition = field(default_factory=threading.Condition)

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "stage": self.stage,
            "progress": round(self.progress, 3),
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "created": self.created,
            "updated": self.updated,
        }

    def update(self, stage: str, progress: float, message: str = "") -> None:
        with self._cond:
            self.stage = stage
            self.progress = max(0.0, min(1.0, progress))
            if message:
                self.message = message
            self.updated = time.time()
            self._events.append(
                {
                    "type": "progress",
                    "stage": stage,
                    "progress": round(self.progress, 3),
                    "message": self.message,
                }
            )
            self._cond.notify_all()

    def finish(self, result: dict) -> None:
        with self._cond:
            self.status = "done"
            self.stage = "done"
            self.progress = 1.0
            self.message = "Готово"
            self.result = result
            self.updated = time.time()
            self._events.append({"type": "done", "result": result})
            self._cond.notify_all()

    def fail(self, exc: BaseException) -> None:
        detail = f"{type(exc).__name__}: {exc}"
        log = traceback.format_exc(limit=6)
        with self._cond:
            self.status = "error"
            self.stage = "error"
            self.message = "Ошибка"
            self.error = detail
            self.updated = time.time()
            self._events.append({"type": "error", "error": detail, "trace": log})
            self._cond.notify_all()

    def stream(self, timeout: float = 600.0) -> Iterator[dict]:
        """Yield progress events until the job settles."""
        deadline = time.time() + timeout
        idx = 0
        yield {"type": "start", **self.snapshot()}
        while time.time() < deadline:
            with self._cond:
                if idx < len(self._events):
                    events = self._events[idx:]
                    idx = len(self._events)
                else:
                    events = []
                    settled = self.status in ("done", "error")
                    if not settled:
                        self._cond.wait(timeout=1.0)
            for ev in events:
                yield ev
                if ev.get("type") in ("done", "error"):
                    return
            if events:
                continue
            with self._cond:
                if self.status in ("done", "error"):
                    if idx >= len(self._events):
                        yield {"type": self.status, **(self.snapshot())}
                    return


_JOBS: dict[str, Job] = {}
_JOB_QUEUE: "queue.Queue[str | None]" = queue.Queue()
_WORKER: threading.Thread | None = None
_WORKER_LOCK = threading.Lock()
_LISTENERS: list[queue.Queue] = []
_LISTENERS_LOCK = threading.Lock()


def _broadcast(event: dict) -> None:
    with _LISTENERS_LOCK:
        listeners = list(_LISTENERS)
    for lq in listeners:
        try:
            lq.put_nowait(event)
        except queue.Full:
            pass


def subscribe() -> queue.Queue:
    lq: queue.Queue = queue.Queue(maxsize=256)
    with _LISTENERS_LOCK:
        _LISTENERS.append(lq)
    return lq


def unsubscribe(lq: queue.Queue) -> None:
    with _LISTENERS_LOCK:
        if lq in _LISTENERS:
            _LISTENERS.remove(lq)


def get_job(job_id: str) -> Job | None:
    return _JOBS.get(job_id)


def list_jobs(limit: int = 40) -> list[dict]:
    jobs = sorted(_JOBS.values(), key=lambda j: j.created, reverse=True)
    return [j.snapshot() for j in jobs[:limit]]


def queue_position(job_id: str) -> int:
    pending = [jid for jid, j in _JOBS.items() if j.status == "queued"]
    try:
        return pending.index(job_id) + 1
    except ValueError:
        return 0


# -------------------------------------------------------------- prompting ---


# CLIP text encoders truncate at 77 tokens, so the assembled prompt has to be
# budgeted: the subject is the most important part and must never be cut.
# This mirrors the diffusers truncation logic closely enough to size the prompt.
_WORD_RE = re.compile(r"\s+")

# A magenta void is the classic chroma-key colour. Asking for an "isolated
# subject on flat magenta" is far more reliable than "transparent background",
# which SD/SDXL tend to ignore, and the cutout stage removes it cleanly.
CUTOUT_HINT = "single subject centered, isolated on a flat solid magenta background, no scenery, no ground"


def _clip_token_count(text: str) -> int:
    """Approximate CLIP BPE token count for budget checks."""
    try:
        from transformers import CLIPTokenizer

        global _CLIP_TOKENIZER
        if _CLIP_TOKENIZER is None:
            _CLIP_TOKENIZER = CLIPTokenizer.from_pretrained(
                "openai/clip-vit-large-patch14"
            )
        return len(_CLIP_TOKENIZER(_WORD_RE.sub(" ", text))["input_ids"])
    except Exception:
        # Fallback: ~1.35 tokens per whitespace-separated word.
        return int(len(_WORD_RE.split(text)) * 1.35) + 2


_CLIP_TOKENIZER = None


def _clean_segments(parts: list[str]) -> list[str]:
    """Split on commas, drop blanks, dedupe case-insensitively, keep order."""
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        for seg in part.split(","):
            seg = seg.strip(" .;")
            if not seg:
                continue
            key = seg.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(seg)
    return out


def _clip_trim(text: str, max_tokens: int = 74) -> str:
    """Trim text to fit the CLIP context, cutting on segment boundaries."""
    if _clip_token_count(text) <= max_tokens:
        return text
    segs = _clean_segments([text])
    kept: list[str] = []
    for seg in segs:
        candidate = ", ".join([*kept, seg])
        if _clip_token_count(candidate) > max_tokens:
            break
        kept.append(seg)
    return ", ".join(kept) if kept else segs[0]


def build_prompt(payload: dict) -> tuple[str, str, dict]:
    """Assemble the final prompt from the category, style and LoRA settings.

    Order matters: subject first, then category framing, then style tokens, so
    the most important tokens survive CLIP's 77-token window.
    """
    style_id = payload.get("style", "pixel16")
    style = style_by_id(style_id)
    category_id = payload.get("category", "prop")
    category = CATEGORY_BY_ID.get(category_id, CATEGORY_BY_ID["prop"])
    subject = (payload.get("prompt") or "").strip()
    if not subject:
        subject = payload.get("subject") or "a game asset"

    base_id = payload.get("base") or (style.base if style else "sdxl")
    base = base_by_id(base_id)

    template = (category.get("template") or "") if isinstance(category, dict) else ""
    # Category templates still reference {subject}; the style fragments do not.
    category_fragment = template.replace("{subject}", "").strip().strip(",").strip()

    parts: list[str] = [subject]
    if category_fragment:
        parts.append(category_fragment)

    style_fragment = style.prompt if style and payload.get("use_style_prompt", True) else ""

    # If the user asked for a cutout, bias the render toward a chroma-key
    # backdrop so the matting step has a clean, flat background to remove.
    # "transparent background" is dropped because it fights the magenta void.
    post_hint = payload.get("post")
    wants_cutout = bool(post_hint and "cutout" in post_hint) or bool(
        payload.get("force_cutout")
    )
    if wants_cutout:
        style_fragment = re.sub(
            r",?\s*transparent background|,?\s*white background|,?\s*plain background",
            "",
            style_fragment,
            flags=re.IGNORECASE,
        )

    if style_fragment:
        parts.append(style_fragment)
    for lora_id in (payload.get("loras") or []):
        lora = lora_by_id(lora_id) if isinstance(lora_id, str) else None
        if lora and lora.trigger:
            parts.append(lora.trigger)

    if wants_cutout:
        parts.append(CUTOUT_HINT)

    prompt = _clip_trim(", ".join(_clean_segments(parts)), 74)

    neg_parts: list[str] = []
    if style and payload.get("use_style_negative", True) and style.negative:
        neg_parts.append(style.negative)
    user_neg = (payload.get("negative") or "").strip()
    if user_neg:
        neg_parts.append(user_neg)
    if payload.get("use_common_negative", True):
        neg_parts.append(COMMON_NEGATIVE)
    if wants_cutout:
        # Keep the key colour out of the subject itself.
        neg_parts.append("magenta backdrop, pink background, magenta lighting")
    negative = _clip_trim(", ".join(_clean_segments(neg_parts)), 74)

    steps = payload.get("steps")
    cfg = payload.get("cfg")
    meta = {
        "base": base.id,
        "base_label": base.label,
        "style": style.id if style else None,
        "style_label": style.label if style else None,
        "category": category_id,
        "steps": int(steps) if steps else base.default_steps,
        "cfg": float(cfg) if cfg is not None else base.default_cfg,
        "size": int(payload.get("size") or (style.size if style else config.DEFAULT_RES)),
        "scheduler": payload.get("scheduler") or "default",
    }
    return prompt, negative, meta


def resolve_loras(payload: dict, meta: dict) -> tuple[tuple[str, float], ...]:
    ids: list[str] = []
    if payload.get("use_style_loras", True):
        style = style_by_id(payload.get("style", ""))
        if style:
            ids.extend(style.loras)
    for extra in payload.get("loras") or []:
        if isinstance(extra, str) and extra not in ids:
            ids.append(extra)
    out: list[tuple[str, float]] = []
    for lid in ids:
        lora = lora_by_id(lid)
        if lora is None:
            continue
        if lora.base != meta["base"]:
            # Skip LoRAs trained for a different architecture.
            continue
        weight = float(payload.get("lora_weight") or lora.weight)
        out.append((lid, weight))
    return tuple(out)


# --------------------------------------------------------------- storage ----


def _asset_dir() -> Path:
    d = config.OUTPUT_DIR / datetime.now(timezone.utc).strftime("%Y-%m")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(text: str, limit: int = 40) -> str:
    """Create a filesystem-safe slug from text, preserving Cyrillic."""
    import unicodedata
    # Normalize and keep only safe characters
    normalized = unicodedata.normalize('NFKC', text)
    keep = []
    for ch in normalized.strip().lower():
        if ch.isalnum() or ch in ' -_':
            keep.append(ch)
        elif ch == 'ё':
            keep.append('е')
    slug = ''.join(keep).strip('-')
    while '--' in slug:
        slug = slug.replace('--', '-')
    return (slug or 'asset')[:limit]


def store_result(
    job_id: str,
    images: list[Image.Image],
    frames: list[Image.Image],
    meta: dict,
    payload: dict,
) -> dict:
    outdir = _asset_dir()
    stem = f"{meta.get('category', 'asset')}_{_slug(payload.get('prompt', ''))}_{job_id[:8]}"
    items: list[dict] = []

    main_name = f"{stem}.png"
    main_path = outdir / main_name
    images[0].save(main_path, format="PNG", optimize=True)
    items.append(
        {
            "name": main_name,
            "kind": "main",
            "url": f"/api/assets/{main_name}",
            "width": images[0].width,
            "height": images[0].height,
            "colors": postprocess.dominant_colors(images[0], 5),
            "bytes": main_path.stat().st_size,
        }
    )

    for idx, extra in enumerate(images[1:], start=1):
        name = f"{stem}_{idx + 1}.png"
        extra.save(outdir / name, format="PNG", optimize=True)
        items.append(
            {
                "name": name,
                "kind": "variant",
                "url": f"/api/assets/{name}",
                "width": extra.width,
                "height": extra.height,
                "colors": postprocess.dominant_colors(extra, 4),
                "bytes": (outdir / name).stat().st_size,
            }
        )

    # WebP preview for the gallery grid.
    webp_name = f"{stem}.webp"
    postprocess.thumbnail(images[0], 512).save(outdir / webp_name, format="WEBP", quality=84)
    items.append(
        {
            "name": webp_name,
            "kind": "preview",
            "url": f"/api/assets/{webp_name}",
            "width": 512,
            "height": 512,
        }
    )

    frame_meta: dict | None = None
    if frames:
        fdir = outdir / f"{stem}_frames"
        fdir.mkdir(exist_ok=True)
        frame_names = []
        for i, frame in enumerate(frames):
            name = f"frame_{i:03d}.png"
            frame.save(fdir / name, format="PNG", optimize=True)
            frame_names.append(
                {
                    "name": name,
                    "index": i,
                    "w": frame.width,
                    "h": frame.height,
                    "url": f"/api/assets/{fdir.name}/{name}",
                }
            )
        atlas, ameta = postprocess.build_atlas(frames, cols=int(payload.get("sheet_cols", 4)))
        atlas_name = f"{stem}_atlas.png"
        atlas.save(outdir / atlas_name, format="PNG", optimize=True)
        (outdir / f"{stem}_atlas.json").write_text(
            json.dumps(ameta, indent=2), encoding="utf-8"
        )
        frame_meta = {
            "count": len(frames),
            "dir": fdir.name,
            "frames": frame_names,
            "atlas": atlas_name,
            "atlas_url": f"/api/assets/{atlas_name}",
            "atlas_json": f"{stem}_atlas.json",
            "sheet": ameta,
        }

    record = {
        "id": job_id,
        "created": datetime.now(timezone.utc).isoformat(),
        "prompt_used": meta.get("prompt_used"),
        "negative_used": meta.get("negative_used"),
        "style": meta.get("style"),
        "style_label": meta.get("style_label"),
        "base": meta.get("base"),
        "base_label": meta.get("base_label"),
        "category": meta.get("category"),
        "seed": meta.get("seed"),
        "steps": meta.get("steps"),
        "cfg": meta.get("cfg"),
        "size": meta.get("size"),
        "scheduler": meta.get("scheduler"),
        "loras": meta.get("loras", []),
        "post": meta.get("post", []),
        "user_prompt": payload.get("prompt"),
        "images": items,
        "frames": frame_meta,
        "elapsed": meta.get("elapsed"),
    }
    (outdir / f"{stem}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    record["dir"] = outdir.name
    _INDEX.append(record)
    _save_index()
    return record


_INDEX_PATH = config.DATA_DIR / "gallery.json"
_INDEX: list[dict] = []
if _INDEX_PATH.exists():
    try:
        _INDEX = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        _INDEX = []


def _save_index() -> None:
    _INDEX_PATH.write_text(
        json.dumps(_INDEX[-500:], indent=2, ensure_ascii=False), encoding="utf-8"
    )


def gallery(limit: int = 60, category: str | None = None) -> list[dict]:
    items = list(reversed(_INDEX))
    if category:
        items = [i for i in items if i.get("category") == category]
    return items[:limit]


# ----------------------------------------------------------------- worker ---


def submit(payload: dict) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], payload=payload)
    _JOBS[job.id] = job
    _JOB_QUEUE.put(job.id)
    ensure_worker()
    _broadcast({"type": "queued", "job": job.snapshot()})
    return job


def ensure_worker() -> None:
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is not None and _WORKER.is_alive():
            return
        _WORKER = threading.Thread(target=_worker_loop, name="spriteforge-worker", daemon=True)
        _WORKER.start()


def _worker_loop() -> None:  # pragma: no cover - long running
    while True:
        job_id = _JOB_QUEUE.get()
        if job_id is None:
            return
        job = _JOBS.get(job_id)
        if job is None:
            continue
        try:
            _run_job(job)
        except BaseException as exc:  # noqa: BLE001
            job.fail(exc)
            _broadcast({"type": "job", "job": job.snapshot()})


def _run_job(job: Job) -> None:  # pragma: no cover - long running
    payload = job.payload
    job.status = "running"
    pos = queue_position(job.id)
    if pos > 1:
        job.update("queue", 0.01, f"В очереди: перед {pos - 1}")
    else:
        job.update("load", 0.01, "Запуск…")

    t0 = time.time()

    # Post-processing must be resolved first: a cutout changes how the image
    # has to be rendered (chroma backdrop), so the prompt depends on it.
    style = style_by_id(payload.get("style", ""))
    category = CATEGORY_BY_ID.get(payload.get("category", "prop"), CATEGORY_BY_ID["prop"])
    default_post = list(category.get("post", ()) or ())
    if style:
        default_post = list(dict.fromkeys(default_post + list(style.post)))
    steps_post = payload.get("post")
    if not steps_post:
        steps_post = default_post
    post_steps = (
        [s for s in steps_post if s in POST_LABELS] if isinstance(steps_post, list) else []
    )
    if not isinstance(steps_post, list) or not post_steps:
        post_steps = default_post

    prompt, negative, meta = build_prompt({**payload, "post": post_steps})
    loras = resolve_loras(payload, meta)
    seed = payload.get("seed")
    seed = int(seed) if seed not in (None, "", "random") else None
    meta["prompt_used"] = prompt
    meta["negative_used"] = negative
    meta["loras"] = [{"id": lid, "weight": w, "label": lora_by_id(lid).label} for lid, w in loras]
    meta["seed"] = seed

    req = engine.GenerateRequest(
        base=meta["base"],
        prompt=prompt,
        negative=negative,
        loras=loras,
        seed=seed,
        steps=meta["steps"],
        cfg=meta["cfg"],
        size=meta["size"],
        batch=int(payload.get("batch", 1)),
        scheduler=meta["scheduler"],
    )

    def progress(stage: str, value: float, message: str = "") -> None:
        job.update(stage, value, message)
        _broadcast({"type": "progress", "job_id": job.id, "stage": stage,
                    "progress": round(value, 3), "message": message})

    images = engine.generate(req, progress)
    if not images:
        raise RuntimeError("Модель не вернула изображений")

    job.update("post", 0.97, "Пост-обработка…")

    processed: list[Image.Image] = []
    all_frames: list[Image.Image] = []
    for img in images:
        out, frames = postprocess.postprocess(
            img,
            post_steps,
            pixel_size=int(payload.get("pixel_size", 64)),
            palette_colors=int(payload.get("palette_colors", 16)),
            tolerance=int(payload.get("tolerance", 42)),
            sheet_cols=int(payload.get("sheet_cols", 4)),
            sheet_rows=int(payload.get("sheet_rows", 4)),
        )
        processed.append(out)
        all_frames.extend(frames)

    meta["post"] = post_steps
    meta["elapsed"] = round(time.time() - t0, 2)
    job.update("post", 0.99, "Сохранение…")
    record = store_result(job.id, processed, all_frames, meta, payload)
    job.finish(record)
    _broadcast({"type": "job", "job": job.snapshot()})
