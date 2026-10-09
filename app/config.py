"""Runtime configuration for the sprite forge backend."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("SPRITEFORGE_DATA", ROOT / "data"))
MODELS_DIR = Path(os.getenv("SPRITEFORGE_MODELS", DATA_DIR / "models"))
OUTPUT_DIR = Path(os.getenv("SPRITEFORGE_OUTPUT", DATA_DIR / "output"))
CACHE_DIR = Path(os.getenv("SPRITEFORGE_CACHE", DATA_DIR / "cache"))

FRONTEND_DIR = ROOT / "frontend"
SITE_DIR = ROOT / "docs"

for _p in (DATA_DIR, MODELS_DIR, OUTPUT_DIR, CACHE_DIR):
    _p.mkdir(parents=True, exist_ok=True)

HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN") or None

# Inference defaults tuned for 8 GB VRAM cards (RTX 2060 SUPER and similar).
DEFAULT_STEPS = 28
DEFAULT_CFG = 6.0
DEFAULT_RES = 1024
MAX_BATCH = 8
ALLOWED_SIZES = (256, 320, 384, 448, 512, 640, 768, 896, 1024, 1152, 1280)

HOST = os.getenv("SPRITEFORGE_HOST", "127.0.0.1")
PORT = int(os.getenv("SPRITEFORGE_PORT", "8420"))

# Set to 0 to force CPU (very slow, but keeps the UI functional).
FORCE_CPU = os.getenv("SPRITEFORGE_FORCE_CPU", "0") == "1"

# Models stay resident between requests. Set to 0 when VRAM is tight.
KEEP_MODEL_LOADED = os.getenv("SPRITEFORGE_KEEP_MODEL", "1") == "1"

HF_ENDPOINT = os.getenv("HF_ENDPOINT", "https://huggingface.co")
