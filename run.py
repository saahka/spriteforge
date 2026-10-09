"""Entry point: python run.py  ->  http://127.0.0.1:8420"""
from __future__ import annotations

import sys
import webbrowser
from threading import Timer

import uvicorn

from app import config


def main() -> None:
    url = f"http://{'127.0.0.1' if config.HOST in ('0.0.0.0', '127.0.0.1') else config.HOST}:{config.PORT}"
    print("=" * 58)
    print("  SpriteForge — генератор игровых ассетов")
    print(f"  Открываю {url}")
    print("  Ctrl+C для остановки")
    print("=" * 58)

    if "--no-browser" not in sys.argv:
        Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
