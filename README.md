# Планировщик визуальной новеллы

### → Открыть сайт: **[saahka.github.io/spriteforge](https://saahka.github.io/spriteforge/)** ←

Готовый план создания новеллы: 11 этапов, 128 задач, задание дня и случайные челленджи.
Работает прямо в браузере, устанавливать ничего не нужно. Прогресс хранится в браузере — есть кнопки «Экспорт» и «Импорт».

---

# SpriteForge — бесплатный генератор игровых ассетов

Локальный веб-сервис для генерации спрайтов, фонов, персонажей, тайлсетов и UI-иконок для игр. Работает полностью на вашем ПК, без подписок и API-ключей.

## Быстрый старт

```bat
start.bat
```

Откройте http://127.0.0.1:8420 в браузере.

Первый запуск скачивает модели с Hugging Face (2–7 ГБ в зависимости от стиля). Это бесплатно, но требует интернет.

## Планировщик новеллы локально

Тот же сайт, но с сохранением на диск:

```bat
plan.bat
```

Открывает http://127.0.0.1:8420/plan/ — здесь прогресс пишется в `data/plan.json` (плюс бэкап `data/plan.backup.json`), поэтому он не потеряется при смене браузера.

| Что есть | Описание |
|----------|----------|
| 11 этапов, 128 задач | От идеи до релиза, этап открывается после закрытия предыдущего |
| Виды задач | Галочка, счётчик (5/12), выбор варианта, поле для записи, таймер фокуса |
| Задание дня | Случайная задача на сегодня + серия дней подряд |
| Удиви меня | Случайный челлендж, пока не выполнишь предыдущий |
| Свои задачи | Любая задача с привязкой к этапу или без |
| Хранилище | `data/plan.json` + бэкап, экспорт/импорт в JSON |

Сайт из папки `site/` — это те же файлы: на GitHub Pages работает на localStorage, локально — через API.

## Что умеет

| Категория | Примеры |
|-----------|---------|
| Персонаж | рыцарь, слизень, ниндзя, маг, робот |
| Фон | лес, подземелье, город, космос |
| Тайлсет | трава, камень, дерево, снег |
| Проп | меч, зелье, сундук, факел |
| UI | сердце, иконка меча, кнопка, монета |
| Спрайт-лист | 16 кадров анимации + атлас + JSON |
| VFX | огонь, молния, исцеление, портал |

## Стили отрисовки

16 пресетов, включая:
- **Pixel Art 16-bit** (SD 1.5 + LoRA)
- **Pixel Art 64px XL** (SDXL + LoRA)
- **Isometric 2.5D** (SDXL + LoRA)
- **Low Poly 3D** (SDXL + LoRA)
- **Retro Anime 90s** (SDXL + LoRA)
- **JRPG Trainer Sprite** (SDXL)
- **Cartoon Mobile Game** (SDXL + LoRA)
- **Painterly Game Art** (SDXL + LoRA)
- **Clean UI / Icons** (SDXL)
- **Seamless Tileset** (SDXL + LoRA)
- **Sprite Sheet Grid** (SDXL + LoRA)
- **FLUX Game Assets** (FLUX.1-dev, нужна 12+ ГБ VRAM)
- **Turbo Draft** (SDXL-Turbo, 1 секунда)

## Пост-обработка

- **Пикселизация** — честные квадратные пиксели с дайзерингом
- **Ограничение палитры** — 2–64 цвета
- **Вырезка фона** — flood-fill с мягкими краями, PNG с альфа-каналом
- **Бесшовный тайл** — автоматическое сшивание краёв
- **Разрезка спрайт-листа** — сетка N×M → отдельные кадры + атлас + JSON

## Скачивание

- **PNG** — основное изображение с альфа-каналом
- **WebP** — превью для галереи
- **ZIP** — весь набор (основное + кадры + атлас + метаданные)
- **JSON** — метаданные (промпт, сид, стиль, LoRA, параметры)

## Быстрые стили (LCM)

LCM (Latent Consistency Model) LoRA позволяет генерировать за **4 шага** вместо 28–30:

| Стиль | Шагов | Время на RTX 2060 SUPER |
|-------|-------|------------------------|
| LCM Pixel (SD1.5) | 4 | ~3.5 с |
| LCM XL (SDXL) | 4 | ~8 с |
| LCM Anime (SDXL) | 4 | ~8 с |
| LCM Isometric (SDXL) | 4 | ~8 с |
| Обычный (28 шагов) | 28 | ~8–17 с |
| Turbo Draft (SDXL-Turbo) | 4 | ~1 с |

## Оптимизации скорости

- **SDPA** (Scaled Dot Product Attention) — встроен в PyTorch, ускоряет на 20–30%
- **xformers** — memory-efficient attention (если установлен)
- **VAE slicing/tiling** — экономит VRAM на 8GB картах
- **Attention slicing** — fallback для 8GB VRAM
- **fp16 веса** — вдвое меньше скачивание и VRAM

## Требования

- **GPU**: NVIDIA с 8+ ГБ VRAM (RTX 2060 SUPER и выше)
- **RAM**: 16 ГБ
- **Диск**: 10–40 ГБ для моделей
- **Python**: 3.11+ (автоматически создаётся venv)

## Структура проекта

```
app/
  config.py          — настройки путей, VRAM, лимитов
  catalog.py         — каталог стилей, LoRA, базовых моделей
  engine.py          — diffusers-движок с кэшем моделей и LoRA
  postprocess.py     — пикселизация, палитра, вырезка, тайлы
  jobs.py            — очередь задач, промпт-билдер, хранилище
  plan.py            — состояние планировщика (data/plan.json)
  main.py            — FastAPI: REST API, SSE, статика
site/                — сайт планировщика (публикуется на GitHub Pages)
  index.html         — страница планировщика
  plan.css           — тёмная тема
  plan.js            — этапы, чекбоксы, таймеры, задание дня
  plan_tasks.js      — каталог 11 этапов и 128 задач
frontend/
  index.html         — SPA генератора
  styles.css         — тёмная тема
  app.js             — логика UI
data/
  models/            — кэш Hugging Face
  output/            — сгенерированные ассеты
  gallery.json       — индекс галереи
  plan.json          — прогресс планировщика
```

## Как публикуется сайт

`site/` — статика без бэга, GitHub Pages отдаёт её как есть. Сайт сам определяет, есть ли API: если да, прогресс пишется на диск через `/api/plan`, если нет — в localStorage браузера.

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|---------------|----------|
| `SPRITEFORGE_PORT` | `8420` | Порт сервера |
| `SPRITEFORGE_HOST` | `127.0.0.1` | Хост |
| `SPRITEFORGE_DATA` | `./data` | Путь к данным |
| `SPRITEFORGE_FORCE_CPU` | `0` | Принудительный CPU |
| `SPRITEFORGE_KEEP_MODEL` | `1` | Держать модель в памяти |
| `HF_TOKEN` | — | Токен Hugging Face (для gated-моделей) |

## Использованные модели

Все модели скачиваются с [Hugging Face](https://huggingface.co) при первом использовании.

### Базовые модели
- [stable-diffusion-v1-5/stable-diffusion-v1-5](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5) — SD 1.5
- [stabilityai/stable-diffusion-xl-base-1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) — SDXL
- [stabilityai/sdxl-turbo](https://huggingface.co/stabilityai/sdxl-turbo) — SDXL-Turbo
- [sWizad/pokemon-trainer-sprite-pixelart](https://huggingface.co/sWizad/pokemon-trainer-sprite-pixelart) — JRPG спрайты
- [black-forest-labs/FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev) — FLUX (12+ ГБ VRAM)

### LoRA
- [nerijs/pixel-art-xl](https://huggingface.co/nerijs/pixel-art-xl) — Pixel Art XL
- [artificialguybr/PixelArtRedmond](https://huggingface.co/artificialguybr/PixelArtRedmond) — Pixar Pixel
- [artificialguybr/pixelartredmond-1-5v-pixel-art-loras-for-sd-1-5](https://huggingface.co/artificialguybr/pixelartredmond-1-5v-pixel-art-loras-for-sd-1-5) — Pixel Art SD1.5
- [ntc-ai/SDXL-LoRA-slider.spritesheet](https://huggingface.co/ntc-ai/SDXL-LoRA-slider.spritesheet) — Sprite Sheet
- [ntc-ai/SDXL-LoRA-slider.isometric-view](https://huggingface.co/ntc-ai/SDXL-LoRA-slider.isometric-view) — Isometric
- [KappaNeuro/isometric-cutaway](https://huggingface.co/KappaNeuro/isometric-cutaway) — Isometric Cutaway
- [nicolasdistasi/lowpoly-game](https://huggingface.co/nicolasdistasi/lowpoly-game) — Low Poly
- [nDimensional/Shaded-Retro-Style-Anime-with-Natural-Language-SDXL-LoRA](https://huggingface.co/nDimensional/Shaded-Retro-Style-Anime-with-Natural-Language-SDXL-LoRA) — Retro Anime
- [Linaqruf/anime-detailer-xl-lora](https://huggingface.co/Linaqruf/anime-detailer-xl-lora) — Anime Detailer
- [ntc-ai/SDXL-LoRA-slider.extremely-detailed](https://huggingface.co/ntc-ai/SDXL-LoRA-slider.extremely-detailed) — Extremely Detailed
- [ntc-ai/SDXL-LoRA-slider.cartoon](https://huggingface.co/ntc-ai/SDXL-LoRA-slider.cartoon) — Cartoon
- [ntc-ai/SDXL-LoRA-slider.cinematic-lighting](https://huggingface.co/ntc-ai/SDXL-LoRA-slider.cinematic-lighting) — Cinematic Lighting
- [gokaygokay/Flux-Game-Assets-LoRA-v2](https://huggingface.co/gokaygokay/Flux-Game-Assets-LoRA-v2) — FLUX Game Assets
- [multimodalart/isometric-skeumorphic-3d-bnb](https://huggingface.co/multimodalart/isometric-skeumorphic-3d-bnb) — Isometric Skeumorphic

## Альтернативные движки

Если у вас уже установлен **ComfyUI** или **Automatic1111/Forge**, вы можете использовать их как бэкенд. Добавьте адаптер в `app/engine.py` или запустите их отдельно и используйте их API.

## Лицензии

- Код: MIT
- Модели: см. лицензии на Hugging Face (OpenRAIL, CreativeML, Apache 2.0 и др.)
- Сгенерированные изображения: зависит от лицензии модели
