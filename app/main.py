from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    import app.techniques  # noqa: F401

    s = get_settings()
    pool_size = max(s.bulk_max_concurrency + 4, s.crawl_max_concurrency + 4, 32)
    pool = ThreadPoolExecutor(max_workers=pool_size, thread_name_prefix="phish-worker")
    asyncio.get_running_loop().set_default_executor(pool)

    from app.core.screenshot import get_screenshot_service
    screenshot_service = get_screenshot_service()

    from app.core.job_runner import get_job_runner
    job_runner = get_job_runner()
    await job_runner.startup()

    try:
        yield
    finally:
        await job_runner.shutdown()
        await screenshot_service.stop()
        pool.shutdown(wait=False, cancel_futures=True)


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="Phishing Data Generator",
        description=(
            "Security research tool for generating phishing page variants "
            "across 25 documented techniques. Used for anti-phishing ML "
            "dataset generation and detection system testing."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.routes.techniques import router as techniques_router
    from app.api.routes.analyze import router as analyze_router
    from app.api.routes.generate import router as generate_router
    from app.api.routes.jobs import router as jobs_router
    from app.api.routes.crawl import router as crawl_router
    from app.api.routes.evaluate import router as evaluate_router

    application.include_router(techniques_router, tags=["Techniques"])
    application.include_router(analyze_router, tags=["Analysis"])
    application.include_router(generate_router, tags=["Generation"])
    application.include_router(jobs_router, tags=["Bulk Jobs"])
    application.include_router(crawl_router, tags=["Crawler"])
    application.include_router(evaluate_router, tags=["Evaluation"])

    @application.get("/", tags=["Health"])
    async def root():
        from app.core.registry import TechniqueRegistry
        s = settings
        return {
            "service": "phish_data_generator",
            "status": "ok",
            "techniques_registered": TechniqueRegistry.count(),
            "docs": "/docs",
# hard-coding values on the client.
            "crawl_defaults": {
                "default_concurrency": s.crawl_default_concurrency,
                "max_concurrency": s.crawl_max_concurrency,
                "unreachable_timeout_s": s.crawl_unreachable_timeout_s,
                "partial_timeout_s": s.crawl_partial_timeout_s,
            },
            "bulk_defaults": {
                "default_concurrency": s.bulk_default_concurrency,
                "max_concurrency": s.bulk_max_concurrency,
                "entry_timeout_s": s.bulk_entry_timeout_s,
            },
        }

    @application.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok"}

    @application.get("/check-ai", tags=["Health"])
    async def check_ai():
        """Lightweight AI-availability probe.

        Returns `available=True` when either:
          - any LLM SDK is installed and per-run keys can be supplied via the UI, or
          - an Anthropic key in env is valid and reachable.

        AI techniques validate their actual credentials at apply-time, so this
        check is informational; it never blocks selection.
        """
        sdks: list[str] = []
        try:
            import anthropic  # noqa: F401
            sdks.append("anthropic")
        except ImportError:
            pass
        try:
            import openai  # noqa: F401
            sdks.append("openai")
        except ImportError:
            pass

        if not sdks:
            return {"available": False, "reason": "no LLM SDK installed (anthropic / openai)"}

        try:
            from app.config import get_settings_sync
            api_key = get_settings_sync().anthropic_api_key
        except Exception:
            api_key = ""

        if not api_key:
            return {
                "available": True,
                "reason": f"SDKs installed ({', '.join(sdks)}); supply per-run API key in the UI",
                "needs_runtime_key": True,
            }

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "test"}],
            )
            return {"available": True, "reason": "Anthropic key valid; per-run keys also accepted"}
        except Exception as exc:
            return {
                "available": True,
                "reason": f"Env key check failed ({str(exc)[:80]}); per-run keys still work",
                "needs_runtime_key": True,
            }

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
