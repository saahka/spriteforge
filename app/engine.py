"""Diffusers inference engine with lazy model + LoRA loading and VRAM guards."""
from __future__ import annotations

import gc
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import torch
from PIL import Image

from . import config
from .catalog import BASE_MODELS, LORAS, BaseModel, Lora, base_by_id, lora_by_id

log = logging.getLogger("spriteforge.engine")

ProgressFn = Callable[[str, float, str], None]

_PIPELINES: dict[str, object] = {}
_LORAS_LOADED: set[str] = set()
# Base models whose repos do not publish *.fp16.safetensors weights.
_NO_FP16: set[str] = set()
_LOCK = threading.RLock()
_ACTIVE_BASE: str | None = None


def _noop(stage: str, progress: float, message: str = "") -> None:  # pragma: no cover
    return None


def device() -> torch.device:
    if config.FORCE_CPU or not torch.cuda.is_available():
        return torch.device("cpu")
    return torch.device("cuda")


def device_name() -> str:
    if device().type == "cuda":
        return torch.cuda.get_device_name(0)
    return "CPU"


def free_vram_gb() -> float:
    if device().type != "cuda":
        return 0.0
    return torch.cuda.mem_get_info(0)[1] / (1024**3)


@dataclass
class GenerateRequest:
    base: str
    prompt: str
    negative: str = ""
    loras: tuple[tuple[str, float], ...] = ()
    seed: int | None = None
    steps: int = 28
    cfg: float = 6.0
    size: int = 1024
    batch: int = 1
    scheduler: str = "default"


def _resolve_dtype():
    if device().type == "cpu":
        return torch.float32
    return torch.float16


def _pick_scheduler(pipe, name: str):
    if name in (None, "", "default"):
        return pipe
    key = name.lower()
    try:
        if key in ("dpm++2m", "dpmpp2m", "dpm++ 2m karras"):
            from diffusers import DPMSolverMultistepScheduler

            return DPMSolverMultistepScheduler.from_config(
                pipe.scheduler.config, use_karras_sigmas=True, algorithm_type="dpmsolver++"
            )
        if key in ("euler", "eulera"):
            from diffusers import EulerAncestralDiscreteScheduler

            return EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
        if key == "euler-a":
            from diffusers import EulerDiscreteScheduler

            return EulerDiscreteScheduler.from_config(pipe.scheduler.config)
        if key in ("dpm++sde", "dpm-sde"):
            from diffusers import DPMSolverSDEScheduler

            return DPMSolverSDEScheduler.from_config(pipe.scheduler.config)
        if key == "lcm":
            from diffusers import LCMScheduler

            return LCMScheduler.from_config(pipe.scheduler.config)
        if key in ("ddim",):
            from diffusers import DDIMScheduler

            return DDIMScheduler.from_config(pipe.scheduler.config)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("scheduler %s unavailable: %s", name, exc)
    return pipe


def _unload_all() -> None:
    global _ACTIVE_BASE
    for key in list(_PIPELINES):
        pipe = _PIPELINES.pop(key)
        try:
            pipe.to("cpu")  # type: ignore[union-attr]
        except Exception:
            pass
        del pipe
    _LORAS_LOADED.clear()
    _ACTIVE_BASE = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()


def _load_base(base_id: str, progress: ProgressFn) -> object:
    """Load (or reuse) a pipeline for the given base model."""
    global _ACTIVE_BASE

    base: BaseModel = base_by_id(base_id)
    with _LOCK:
        if _ACTIVE_BASE != base_id:
            _unload_all()

        cached = _PIPELINES.get(base_id)
        if cached is not None:
            progress("model", 0.6, f"{base.label} уже в памяти")
            return cached

        progress("model", 0.05, f"Загрузка {base.label}…")
        t0 = time.time()
        token = config.HF_TOKEN
        common: dict = {"torch_dtype": _resolve_dtype(), "use_safetensors": True}
        if token:
            common["token"] = token

        if base.kind == "flux":
            from diffusers import FluxPipeline as loader
        else:
            from diffusers import AutoPipelineForText2Image as loader

        # Prefer the fp16 weight variant: it halves the download and the disk
        # footprint. Not every repo publishes it, so remember the outcome and
        # stop paying for a failed attempt on every reload.
        attempts: tuple[dict, ...] = ({},) if base_id in _NO_FP16 else ({"variant": "fp16"}, {})
        pipe = None
        errors: list[str] = []
        for extra in attempts:
            try:
                pipe = loader.from_pretrained(base.repo, **common, **extra)
                break
            except Exception as exc:  # noqa: PERF203
                if extra:
                    _NO_FP16.add(base_id)
                errors.append(f"{extra or 'default'}: {type(exc).__name__}: {exc}")
                pipe = None
        if pipe is None:
            raise RuntimeError(
                f"Не удалось загрузить {base.repo}: " + " | ".join(errors[-2:])
            )

        if base.kind != "flux":
            # Asset generation has no need for the NSFW classifier, and it
            # frees VRAM on 8 GB cards. Only null the attribute: calling
            # register_modules() here would change the pipeline's expected
            # component signature and break __call__.
            try:
                pipe.safety_checker = None
            except Exception:
                pass

        pipe = pipe.to(device())
        try:
            pipe.set_progress_bar_config(disable=True)
        except Exception:
            pass

        # --- Speed optimizations (in order of impact) ---
        # 1. xformers memory-efficient attention (biggest speedup on 8GB)
        try:
            pipe.enable_xformers_memory_efficient_attention()
        except Exception:
            pass
        # 2. PyTorch SDPA (built-in, no extra deps)
        try:
            from diffusers.models.attention_processor import AttnProcessor2_0
            pipe.unet.set_attn_processor(AttnProcessor2_0())
        except Exception:
            pass
        # 3. VAE optimizations
        try:
            pipe.vae.enable_slicing()
        except Exception:
            pass
        try:
            pipe.vae.enable_tiling()
        except Exception:
            pass
        # 4. torch.compile for UNet (20-40% speedup, one-time cost)
        #    Disabled on Windows: torch.compile requires Triton which is
        #    not available on Windows. SDPA + xformers give most of the win.
        if device().type == "cuda" and not config.FORCE_CPU and os.name != "nt":
            try:
                pipe.unet = torch.compile(pipe.unet, mode="reduce-overhead", fullgraph=False)
            except Exception:
                pass
        # 5. Attention slicing as fallback for 8GB VRAM
        try:
            pipe.enable_attention_slicing("max" if device().type == "cpu" else "auto")
        except Exception:
            pass
        try:
            pipe.enable_vae_slicing()
        except Exception:
            pass

        _PIPELINES[base_id] = pipe
        _ACTIVE_BASE = base_id
        log.info("loaded %s in %.1fs", base_id, time.time() - t0)
        progress("model", 0.6, f"{base.label} готова ({time.time() - t0:.0f} с)")
        return pipe


def _resolve_lora_path(lora: Lora) -> Path:
    from huggingface_hub import hf_hub_download

    kwargs = {"repo_id": lora.repo, "filename": lora.filename}
    if config.HF_TOKEN:
        kwargs["token"] = config.HF_TOKEN
    return Path(hf_hub_download(**kwargs))


def _apply_loras(
    pipe, loras: Iterable[tuple[str, float]], base_id: str, progress: ProgressFn
) -> None:
    pairs: list[tuple[str, float]] = []
    for lora_id, weight in loras:
        lora = lora_by_id(lora_id)
        if lora is None:
            log.warning("unknown lora %s", lora_id)
            continue
        pairs.append((lora_id, weight))

    wanted = {lid for lid, _ in pairs}
    stale = [lid for lid in _LORAS_LOADED if lid not in wanted]
    if stale:
        try:
            pipe.unload_lora_weights()
            _LORAS_LOADED.clear()
        except Exception as exc:  # pragma: no cover
            log.warning("unload failed: %s", exc)
    if not pairs:
        return

    progress("model", 0.7, "Подключение LoRA…")
    adapters: list[str] = []
    weights: list[float] = []
    for idx, (lora_id, weight) in enumerate(pairs):
        lora = lora_by_id(lora_id)
        if lora is None:
            continue
        path = _resolve_lora_path(lora)
        progress("model", 0.7 + 0.2 * (idx + 1) / len(pairs), f"LoRA {lora.label}")
        try:
            # Use a stable adapter name derived from the LoRA id
            adapter_name = f"lora_{lora_id}"
            pipe.load_lora_weights(str(path), adapter_name=adapter_name)
            adapters.append(adapter_name)
            weights.append(weight)
            _LORAS_LOADED.add(lora_id)
        except Exception as exc:
            log.warning("lora %s failed: %s", lora_id, exc)
    if adapters:
        try:
            pipe.set_adapters(adapters, adapter_weights=weights)
        except Exception as exc:  # pragma: no cover
            log.warning("set_adapters failed: %s", exc)
        progress("model", 0.92, f"LoRA подключены: {len(adapters)}")


def _snap_to(value: int, allowed: Iterable[int]) -> int:
    allowed = sorted(allowed)
    return min(allowed, key=lambda a: abs(a - value))


def generate(req: GenerateRequest, progress: ProgressFn = _noop) -> list[Image.Image]:
    """Run text-to-image and return PIL images."""
    base = base_by_id(req.base)
    size = _snap_to(req.size, config.ALLOWED_SIZES)
    # FLUX and SDXL prefer a square-ish canvas with /8 alignment.
    if base.id in ("sdxl", "sdxl-turbo", "sdxl-pokemon", "flux-game"):
        size = min(size, 1152)

    progress("load", 0.02, "Подготовка модели…")
    pipe = _load_base(req.base, progress)
    _apply_loras(pipe, req.loras, req.base, progress)

    # LCM LoRA requires LCMScheduler for proper 4-step generation
    has_lcm = any("lcm" in lid for lid, _ in req.loras)
    if has_lcm:
        try:
            from diffusers import LCMScheduler
            pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
        except Exception:
            pass
    elif req.scheduler and req.scheduler != "default":
        pipe.scheduler = _pick_scheduler(pipe, req.scheduler)

    steps = max(1, min(80, int(req.steps or base.default_steps)))
    cfg = max(0.0, min(20.0, float(req.cfg if req.cfg is not None else base.default_cfg)))
    batch = max(1, min(config.MAX_BATCH, int(req.batch)))

    generator_device = device()
    seeds: list[int] = []
    if req.seed is None:
        import random

        base_seed = random.randint(0, 2**31 - 1)
        seeds = [base_seed + i for i in range(batch)]
    else:
        seeds = [int(req.seed) + i for i in range(batch)]

    kwargs = {
        "prompt": req.prompt,
        "negative_prompt": req.negative or None,
        "num_inference_steps": steps,
        "guidance_scale": cfg,
        "num_images_per_prompt": batch,
        "generator": [
            torch.Generator(device=generator_device).manual_seed(s) for s in seeds
        ],
    }
    if base.id in ("sdxl", "sdxl-turbo", "sdxl-pokemon"):
        kwargs["height"] = size
        kwargs["width"] = size
    elif base.kind == "flux":
        kwargs["height"] = size
        kwargs["width"] = size
        kwargs["max_sequence_length"] = 256
    else:
        kwargs["height"] = size
        kwargs["width"] = size

    if base.id == "sdxl-turbo":
        kwargs["guidance_scale"] = 0.0
        kwargs["num_inference_steps"] = max(1, min(8, steps))

    def _cb(pipe_ref, step, timestep, cb_kwargs):
        # callback_on_step_end reports a 0-based index after each finished step.
        done = min(step + 1, steps)
        pct = done / max(1, steps)
        progress("render", 0.05 + 0.9 * pct, f"Шаг {done}/{steps}")
        return cb_kwargs

    progress("render", 0.05, f"Генерация {batch} шт. · {steps} шагов · {size}px")
    t0 = time.time()
    with torch.inference_mode():
        try:
            out = pipe(**kwargs, callback_on_step_end=_cb)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            gc.collect()
            # Retry once with aggressive memory saving
            try:
                pipe.enable_attention_slicing(1)
                pipe.enable_vae_tiling()
                pipe.enable_vae_slicing()
            except Exception:
                pass
            out = pipe(**kwargs, callback_on_step_end=_cb)
    images = list(out.images)
    progress("render", 0.97, f"Готово за {time.time() - t0:.1f} с")
    return images


def status() -> dict:
    dev = device()
    info = {
        "device": dev.type,
        "device_name": device_name(),
        "torch": torch.__version__,
        "vram_gb": round(free_vram_gb(), 2) if dev.type == "cuda" else 0.0,
        "loaded_base": _ACTIVE_BASE,
        "loaded_loras": sorted(_LORAS_LOADED),
        "available_bases": list(BASE_MODELS),
    }
    return info


def unload() -> None:
    with _LOCK:
        _unload_all()
