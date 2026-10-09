"""Catalog of base models, LoRAs and art-style presets for game asset generation.

Every entry here points at a public Hugging Face repository that is downloaded
lazily on first use. The LoRA tokens were taken from the model cards, so the
prompts stay close to what each LoRA was trained on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BaseId = Literal["sd15", "sdxl", "sdxl-turbo", "sdxl-pokemon", "flux-game"]

Category = Literal[
    "character",
    "background",
    "tileset",
    "prop",
    "ui",
    "sprite_sheet",
    "vfx",
]


@dataclass(frozen=True)
class BaseModel:
    id: str
    label: str
    repo: str
    kind: str = "sd"
    # Rough download size in GB, shown in the UI before the first fetch.
    size_gb: float = 2.0
    default_steps: int = 28
    default_cfg: float = 6.0
    # Free-form notes surfaced in the UI.
    note: str = ""


BASE_MODELS: dict[str, BaseModel] = {
    "sd15": BaseModel(
        id="sd15",
        label="Stable Diffusion 1.5",
        repo="stable-diffusion-v1-5/stable-diffusion-v1-5",
        size_gb=2.1,
        note="Самая лёгкая база. Быстро на 8 ГБ VRAM.",
    ),
    "sdxl": BaseModel(
        id="sdxl",
        label="Stable Diffusion XL Base 1.0",
        repo="stabilityai/stable-diffusion-xl-base-1.0",
        size_gb=7.0,
        default_steps=30,
        default_cfg=7.0,
        note="Лучшее качество деталей. Нужно ~8 ГБ VRAM.",
    ),
    "sdxl-turbo": BaseModel(
        id="sdxl-turbo",
        label="SDXL Turbo (1-4 steps)",
        repo="stabilityai/sdxl-turbo",
        size_gb=7.0,
        default_steps=4,
        default_cfg=1.0,
        note="Мгновенные черновики, слабее следование промпту.",
    ),
    "sdxl-pokemon": BaseModel(
        id="sdxl-pokemon",
        label="Pokemon Trainer Sprites (SDXL)",
        repo="sWizad/pokemon-trainer-sprite-pixelart",
        size_gb=7.0,
        note="Готовые JRPG-спрайты персонажей.",
    ),
    "flux-game": BaseModel(
        id="flux-game",
        label="FLUX.1-dev + Game Assets",
        repo="black-forest-labs/FLUX.1-dev",
        kind="flux",
        size_gb=33.0,
        default_steps=24,
        default_cfg=3.5,
        note="Требует 12+ ГБ VRAM. Максимальное качество.",
    ),
}


@dataclass(frozen=True)
class Lora:
    id: str
    repo: str
    filename: str
    label: str
    base: str = "sdxl"
    # Trigger words injected into the prompt when the LoRA is enabled.
    trigger: str = ""
    weight: float = 0.9
    size_gb: float = 0.2
    license: str = ""


LORAS: dict[str, Lora] = {
    "pixel-art-xl": Lora(
        id="pixel-art-xl",
        repo="nerijs/pixel-art-xl",
        filename="pixel-art-xl.safetensors",
        label="Pixel Art XL (64px)",
        base="sdxl",
        trigger="pixel art, 64x64 sprite",
        weight=1.0,
    ),
    "lcm-sdxl": Lora(
        id="lcm-sdxl",
        repo="latent-consistency/lcm-lora-sdxl",
        filename="pytorch_lora_weights.safetensors",
        label="LCM SDXL (4 шага)",
        base="sdxl",
        trigger="",
        weight=1.0,
    ),
    "lcm-sd15": Lora(
        id="lcm-sd15",
        repo="latent-consistency/lcm-lora-sdv1-5",
        filename="pytorch_lora_weights.safetensors",
        label="LCM SD1.5 (4 шага)",
        base="sd15",
        trigger="",
        weight=1.0,
    ),
    "pixelart-redmond": Lora(
        id="pixelart-redmond",
        repo="artificialguybr/PixelArtRedmond",
        filename="PixelArtRedmond-Lite64.safetensors",
        label="Redmond PIXARFK Lite64",
        base="sdxl",
        trigger="pixar disney style, pixar",
        weight=0.85,
    ),
    "pixelart-128": Lora(
        id="pixelart-128",
        repo="artificialguybr/pixelartredmond-1-5v-pixel-art-loras-for-sd-1-5",
        filename="PixelArtRedmond15V-PixelArt-PIXARFK.safetensors",
        label="Redmond PIXARFK 128px (SD1.5)",
        base="sd15",
        trigger="pixar disney style, pixar",
        weight=0.9,
    ),
    "spritesheet": Lora(
        id="spritesheet",
        repo="ntc-ai/SDXL-LoRA-slider.spritesheet",
        filename="spritesheet.safetensors",
        label="Sprite Sheet Layout",
        base="sdxl",
        trigger="spritesheet",
        weight=0.8,
    ),
    "isometric-view": Lora(
        id="isometric-view",
        repo="ntc-ai/SDXL-LoRA-slider.isometric-view",
        filename="isometric view.safetensors",
        label="Isometric View",
        base="sdxl",
        trigger="isometric view",
        weight=0.85,
    ),
    "isometric-cutaway": Lora(
        id="isometric-cutaway",
        repo="KappaNeuro/isometric-cutaway",
        filename="Isometric Cutaway.safetensors",
        label="Isometric Cutaway",
        base="sdxl",
        trigger="isometric cutaway, cutaway room",
        weight=0.85,
    ),
    "lowpoly-game": Lora(
        id="lowpoly-game",
        repo="nicolasdistasi/lowpoly-game",
        filename="lowpoly-game.safetensors",
        label="Low Poly Game",
        base="sdxl",
        trigger="low poly game art",
        weight=0.9,
    ),
    "retro-anime": Lora(
        id="retro-anime",
        repo="nDimensional/Shaded-Retro-Style-Anime-with-Natural-Language-SDXL-LoRA",
        filename="Shaded-Retro-Anime.safetensors",
        label="Shaded Retro Anime",
        base="sdxl",
        trigger="shaded retro anime, 90s anime style",
        weight=0.9,
    ),
    "anime-detailer": Lora(
        id="anime-detailer",
        repo="Linaqruf/anime-detailer-xl-lora",
        filename="anime-detailer-xl.safetensors",
        label="Anime Detailer XL",
        base="sdxl",
        trigger="anime style",
        weight=0.75,
    ),
    "extremely-detailed": Lora(
        id="extremely-detailed",
        repo="ntc-ai/SDXL-LoRA-slider.extremely-detailed",
        filename="extremely detailed.safetensors",
        label="Extremely Detailed",
        base="sdxl",
        trigger="extremely detailed",
        weight=0.6,
    ),
    "cartoon": Lora(
        id="cartoon",
        repo="ntc-ai/SDXL-LoRA-slider.cartoon",
        filename="cartoon.safetensors",
        label="Cartoon",
        base="sdxl",
        trigger="cartoon",
        weight=0.75,
    ),
    "cinematic-lighting": Lora(
        id="cinematic-lighting",
        repo="ntc-ai/SDXL-LoRA-slider.cinematic-lighting",
        filename="cinematic lighting.safetensors",
        label="Cinematic Lighting",
        base="sdxl",
        trigger="cinematic lighting",
        weight=0.7,
    ),
    "flux-game-assets": Lora(
        id="flux-game-assets",
        repo="gokaygokay/Flux-Game-Assets-LoRA-v2",
        filename="game_asst.safetensors",
        label="FLUX Game Assets v2",
        base="flux-game",
        trigger="game asset, 2d game art",
        weight=1.0,
    ),
    "isometric-skeumorphic": Lora(
        id="isometric-skeumorphic",
        repo="multimodalart/isometric-skeumorphic-3d-bnb",
        filename="isometric-skeumorphic-3d-bnb.safetensors",
        label="Isometric Skeumorphic 3D",
        base="flux-game",
        trigger="isometric 3d render",
        weight=1.0,
    ),
}


@dataclass(frozen=True)
class StylePreset:
    """A style preset.

    `prompt` and `negative` are pure *style fragments*: they must never repeat
    the subject, otherwise the subject gets diluted and CLIP runs out of tokens.
    """

    id: str
    label: str
    base: str
    loras: tuple[str, ...] = ()
    prompt: str = ""
    negative: str = ""
    categories: tuple[str, ...] = ("character", "prop", "background")
    # Rendering hints surfaced as recommended post-processing steps.
    post: tuple[str, ...] = ()
    swatch: str = "#6d5efc"
    tags: tuple[str, ...] = ()
    # Recommended size for this style, in pixels on the short side.
    size: int = 1024
    steps: int | None = None
    cfg: float | None = None
    note: str = ""


STYLES: tuple[StylePreset, ...] = (
    StylePreset(
        id="pixel16",
        label="Pixel Art 16-bit",
        base="sd15",
        loras=("pixelart-128",),
        prompt="16-bit pixel art sprite, limited 16 color palette, crisp pixel edges, "
        "dithering, no anti-aliasing, game sprite, transparent background",
        negative="blurry, anti-aliased, photorealistic, 3d render, watermark, text, "
        "smooth gradients, jpeg artifacts, extra limbs",
        categories=("character", "prop", "tileset", "sprite_sheet"),
        post=("pixelate", "palette", "cutout"),
        swatch="#4ec9b0",
        tags=("pixel", "retro", "16-bit"),
        size=512,
        steps=28,
        note="Классика для 2D-игр. Пост-обработка даёт честные пиксели.",
    ),
    StylePreset(
        id="pixel64-xl",
        label="Pixel Art 64px (XL)",
        base="sdxl",
        loras=("pixel-art-xl",),
        prompt="pixel art, 64x64 sprite, limited color palette, black outline, "
        "crisp square pixels, dithered shading, transparent background, game asset",
        negative="smooth, blurry, anti-aliasing, photo, 3d render, gradient, text, watermark, "
        "realistic lighting",
        categories=("character", "prop", "tileset", "sprite_sheet"),
        post=("pixelate", "palette", "cutout"),
        swatch="#3fb950",
        tags=("pixel", "xl"),
        size=1024,
        steps=30,
    ),
    StylePreset(
        id="pixel-pixar",
        label="Pixar Pixel Fusion",
        base="sdxl",
        loras=("pixelart-redmond", "pixel-art-xl"),
        prompt="pixel art, pixar disney style, rounded shapes, expressive lighting, "
        "crisp pixels, game character, transparent background",
        negative="blurry, photo, realistic skin, jpeg artifacts, text, watermark, noisy",
        categories=("character", "prop"),
        post=("pixelate", "cutout"),
        swatch="#f0883e",
        tags=("pixel", "pixar"),
        size=1024,
    ),
    StylePreset(
        id="isometric",
        label="Isometric 2.5D",
        base="sdxl",
        loras=("isometric-view",),
        prompt="isometric view, 2.5d game art, 45 degree top-down angle, "
        "orthographic projection, clean vector-like shading, soft ambient occlusion, "
        "game asset, no background",
        negative="perspective distortion, side view, photo, blurry, text, watermark, humans",
        categories=("prop", "background", "tileset"),
        post=("cutout",),
        swatch="#58a6ff",
        tags=("isometric", "2.5d", "rts"),
        size=1024,
    ),
    StylePreset(
        id="isometric-cutaway",
        label="Isometric Cutaway Room",
        base="sdxl",
        loras=("isometric-cutaway",),
        prompt="isometric cutaway, cross-section interior, 2.5d game room, "
        "open walls, top-down 45 degree, soft lighting, clean lines, game background art",
        negative="exterior, photo, blurry, text, watermark, fisheye",
        categories=("background", "tileset"),
        post=(),
        swatch="#a371f7",
        tags=("isometric", "interior", "cutaway"),
        size=1024,
    ),
    StylePreset(
        id="lowpoly",
        label="Low Poly 3D",
        base="sdxl",
        loras=("lowpoly-game",),
        prompt="low poly game art, flat shaded 3d render, faceted geometry, "
        "simple materials, bright key light, pastel palette, game asset, transparent background",
        negative="high poly, photo, realistic texture, noisy, blurry, text, watermark",
        categories=("prop", "character", "background"),
        post=("cutout",),
        swatch="#d29922",
        tags=("lowpoly", "3d"),
        size=1024,
    ),
    StylePreset(
        id="retro-anime",
        label="Retro Anime (90s)",
        base="sdxl",
        loras=("retro-anime",),
        prompt="shaded retro anime, 90s anime style, cel shading, airbrush gradient, "
        "vintage screentone, vibrant colors, character illustration, transparent background",
        negative="photo, 3d, modern anime, blurry, text, watermark, extra fingers",
        categories=("character", "prop"),
        post=("cutout",),
        swatch="#f778ba",
        tags=("anime", "retro", "jrpg"),
        size=1024,
    ),
    StylePreset(
        id="anime",
        label="Modern Anime",
        base="sdxl",
        loras=("anime-detailer",),
        prompt="anime style, clean lineart, cel shaded, vibrant, "
        "studio quality character art, transparent background",
        negative="photo, 3d render, blurry, text, watermark, bad anatomy",
        categories=("character", "prop"),
        post=("cutout",),
        swatch="#db61a2",
        tags=("anime", "character"),
        size=1024,
    ),
    StylePreset(
        id="pokemon",
        label="JRPG Trainer Sprite",
        base="sdxl-pokemon",
        prompt="pokemon trainer sprite, pokemon style creature design, "
        "full body, simple background, vibrant colors, clean outline, game art",
        negative="photo, realistic, blurry, text, watermark, multiple characters",
        categories=("character", "prop"),
        post=("pixelate", "cutout"),
        swatch="#f85149",
        tags=("jrpg", "pokemon", "creature"),
        size=1024,
    ),
    StylePreset(
        id="cartoon",
        label="Cartoon Mobile Game",
        base="sdxl",
        loras=("cartoon", "extremely-detailed"),
        prompt="cartoon game art, bold clean outlines, flat vibrant colors, "
        "soft shading, mobile game asset, transparent background, extremely detailed",
        negative="photo, gritty, noisy, blurry, text, watermark, horror",
        categories=("prop", "character", "ui"),
        post=("cutout",),
        swatch="#39c5cf",
        tags=("cartoon", "mobile"),
        size=1024,
    ),
    StylePreset(
        id="paintoon",
        label="Painterly Game Art",
        base="sdxl",
        loras=("cinematic-lighting", "extremely-detailed"),
        prompt="painterly game art, hand-painted textures, cinematic lighting, "
        "volumetric light, highly detailed, concept art quality, game background",
        negative="flat, vector, pixel art, photo, blurry, text, watermark, low quality",
        categories=("background", "prop"),
        post=(),
        swatch="#bc8cff",
        tags=("painterly", "background", "concept"),
        size=1152,
        steps=34,
    ),
    StylePreset(
        id="ui-clean",
        label="Clean UI / Icons",
        base="sdxl",
        prompt="clean flat vector game ui icon, minimal geometric shapes, "
        "bold silhouette, single accent color, soft drop shadow, white background, "
        "centered, app icon",
        negative="photo, 3d render, noisy, busy background, text, letters, watermark, "
        "complex details, gradient mesh",
        categories=("ui", "prop"),
        post=("cutout",),
        swatch="#79c0ff",
        tags=("ui", "icon", "flat"),
        size=768,
    ),
    StylePreset(
        id="tileset",
        label="Seamless Tileset",
        base="sdxl",
        loras=("isometric-view",),
        prompt="seamless tileable game tileset, top-down, repeating pattern, "
        "orthographic top view, even lighting, no borders, flat design, rpg terrain",
        negative="perspective, border, frame, text, watermark, vignette, uneven lighting",
        categories=("tileset", "background"),
        post=("seamless",),
        swatch="#2ea043",
        tags=("tileset", "terrain", "seamless"),
        size=1024,
    ),
    StylePreset(
        id="spritesheet",
        label="Sprite Sheet Grid",
        base="sdxl",
        loras=("spritesheet",),
        prompt="spritesheet, 4x4 grid of animation frames, consistent character "
        "design, side view, walk cycle, game sprite sheet, uniform frame size, "
        "flat background, evenly spaced",
        negative="inconsistent design, different characters, text, watermark, photo, blurry, "
        "overlapping frames",
        categories=("sprite_sheet",),
        post=("split",),
        swatch="#8957e5",
        tags=("spritesheet", "animation", "frames"),
        size=1024,
        steps=32,
        note="Генерирует сетку кадров; кнопка «Разрезать» нарежет её на отдельные PNG.",
    ),
    StylePreset(
        id="flux-game",
        label="FLUX Game Assets",
        base="flux-game",
        loras=("flux-game-assets", "isometric-skeumorphic"),
        prompt="2d game asset, clean professional game art, crisp details, "
        "centered subject, production ready, transparent background",
        negative="photo, blurry, text, watermark, low quality, cropped",
        categories=("prop", "character", "background", "tileset"),
        post=("cutout",),
        swatch="#e3b341",
        tags=("flux", "quality"),
        size=1024,
        note="Нужна видеокарта от 12 ГБ. Скачивает ~35 ГБ.",
    ),
    StylePreset(
        id="turbo-draft",
        label="Turbo Draft (быстро)",
        base="sdxl-turbo",
        prompt="game asset art, clean, high quality, detailed",
        negative="blurry, low quality, text, watermark",
        categories=("character", "prop", "background", "ui", "tileset", "vfx", "sprite_sheet"),
        post=(),
        swatch="#8b949e",
        tags=("fast", "draft"),
        size=768,
        steps=4,
        cfg=1.0,
        note="Быстрые черновики за 1 секунду. Финальные картинки делайте другими стилями.",
    ),
    StylePreset(
        id="lcm-pixel",
        label="LCM Pixel (4 шага)",
        base="sd15",
        loras=("pixelart-128", "lcm-sd15"),
        prompt="16-bit pixel art sprite, limited 16 color palette, crisp pixel edges, "
        "dithering, no anti-aliasing, game sprite",
        negative="blurry, anti-aliased, photorealistic, 3d render, watermark, text, "
        "smooth gradients, jpeg artifacts, extra limbs",
        categories=("character", "prop", "tileset", "sprite_sheet"),
        post=("pixelate", "palette", "cutout"),
        swatch="#4ec9b0",
        tags=("pixel", "fast", "lcm"),
        size=512,
        steps=4,
        cfg=1.0,
        note="LCM LoRA: 4 шага вместо 28. В 4 раза быстрее.",
    ),
    StylePreset(
        id="lcm-xl",
        label="LCM XL (4 шага)",
        base="sdxl",
        loras=("pixel-art-xl", "lcm-sdxl"),
        prompt="pixel art, 64x64 sprite, limited color palette, black outline, "
        "crisp square pixels, dithered shading, game asset",
        negative="smooth, blurry, anti-aliasing, photo, 3d render, gradient, text, watermark, "
        "realistic lighting",
        categories=("character", "prop", "tileset", "sprite_sheet"),
        post=("pixelate", "palette", "cutout"),
        swatch="#3fb950",
        tags=("pixel", "xl", "fast", "lcm"),
        size=1024,
        steps=4,
        cfg=1.0,
        note="LCM LoRA на SDXL: 4 шага, высокое качество.",
    ),
    StylePreset(
        id="lcm-anime",
        label="LCM Anime (4 шага)",
        base="sdxl",
        loras=("retro-anime", "lcm-sdxl"),
        prompt="shaded retro anime, 90s anime style, cel shading, airbrush gradient, "
        "vintage screentone, vibrant colors, character illustration",
        negative="photo, 3d, modern anime, blurry, text, watermark, extra fingers",
        categories=("character", "prop"),
        post=("cutout",),
        swatch="#f778ba",
        tags=("anime", "fast", "lcm"),
        size=1024,
        steps=4,
        cfg=1.0,
        note="Быстрый аниме-стиль за 4 шага.",
    ),
    StylePreset(
        id="lcm-iso",
        label="LCM Isometric (4 шага)",
        base="sdxl",
        loras=("isometric-view", "lcm-sdxl"),
        prompt="isometric view, 2.5d game art, 45 degree top-down angle, "
        "orthographic projection, clean vector-like shading, soft ambient occlusion, "
        "game asset",
        negative="perspective distortion, side view, photo, blurry, text, watermark, humans",
        categories=("prop", "background", "tileset"),
        post=("cutout",),
        swatch="#58a6ff",
        tags=("isometric", "fast", "lcm"),
        size=1024,
        steps=4,
        cfg=1.0,
        note="Быстрая изометрия за 4 шага.",
    ),
)


CATEGORIES: tuple[dict, ...] = (
    {
        "id": "character",
        "label": "Персонаж",
        "hint": "hero, enemy, npc",
        "size": 1024,
        "post": ("cutout",),
        "template": "full body game character, {subject}, single character, centered",
    },
    {
        "id": "background",
        "label": "Фон / окружение",
        "hint": "forest, dungeon, city",
        "size": 1152,
        "post": (),
        "template": "game background art, {subject}, environment scene, no characters, wide shot",
    },
    {
        "id": "tileset",
        "label": "Тайлсет",
        "hint": "grass, stone, wood",
        "size": 1024,
        "post": ("seamless",),
        "template": "seamless tileable game tileset, {subject}, top-down view, repeating",
    },
    {
        "id": "prop",
        "label": "Проп / предмет",
        "hint": "sword, potion, chest",
        "size": 1024,
        "post": ("cutout",),
        "template": "game item, {subject}, single object, centered, product shot",
    },
    {
        "id": "ui",
        "label": "UI / Иконка",
        "hint": "heart, sword icon, button",
        "size": 768,
        "post": ("cutout",),
        "template": "game ui icon, {subject}, flat vector, minimal, centered",
    },
    {
        "id": "sprite_sheet",
        "label": "Спрайт-лист",
        "hint": "walk cycle, attack",
        "size": 1024,
        "post": ("split",),
        "template": "spritesheet, {subject}, 4x4 grid of animation frames, walk cycle",
    },
    {
        "id": "vfx",
        "label": "Эффект / VFX",
        "hint": "fire, slash, magic",
        "size": 1024,
        "post": ("cutout",),
        "template": "game vfx effect, {subject}, glowing magical effect, isolated, transparent",
    },
)

CATEGORY_BY_ID = {c["id"]: c for c in CATEGORIES}

# Negative prompts are merged with the style's own negative prompt.
COMMON_NEGATIVE = (
    "watermark, signature, text, logo, username, jpeg artifacts, low quality, blurry, "
    "out of frame, cropped, deformed"
)

POST_LABELS = {
    "pixelate": "Пикселизация",
    "palette": "Ограничение палитры",
    "cutout": "Вырезать фон (PNG)",
    "seamless": "Бесшовный тайл",
    "split": "Разрезать на кадры",
    "upscale": "Апскейл x2",
}


def style_by_id(style_id: str) -> StylePreset | None:
    for s in STYLES:
        if s.id == style_id:
            return s
    return None


def base_by_id(base_id: str) -> BaseModel:
    return BASE_MODELS.get(base_id, BASE_MODELS["sd15"])


def lora_by_id(lora_id: str) -> Lora | None:
    return LORAS.get(lora_id)
