"""HTTP-сервер для пинга (UptimeRobot) на Render.com."""
from __future__ import annotations

import logging
from datetime import datetime

from aiohttp import web

log = logging.getLogger(__name__)


def _build_app(public_url: str) -> web.Application:
    app = web.Application()

    async def head_root(_: web.Request) -> web.Response:
        # UptimeRobot мониторинг типа "HEAD" — отвечаем 200 без тела
        return web.Response(status=200)

    async def get_root(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "service": "dayliki-bot",
                "status": "ok",
                "now": datetime.utcnow().isoformat() + "Z",
                "url": public_url or None,
            }
        )

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="OK")

    app.router.add_route("HEAD", "/", head_root)
    app.router.add_route("GET",  "/", get_root)
    app.router.add_route("HEAD", "/health", head_root)
    app.router.add_route("GET",  "/health", health)
    return app


async def run_web(host: str, port: int, public_url: str) -> web.AppRunner:
    app = _build_app(public_url)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    log.info("HTTP server listening on %s:%s", host, port)
    return runner
