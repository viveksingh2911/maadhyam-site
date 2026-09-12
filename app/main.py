"""FastAPI application entrypoint."""
from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .config import BASE_DIR, settings
from .database import Base, SessionLocal, engine
from .models import Role, User
from .routers import admin, feeds, public
from .security import hash_password
from .templating import render, templates


def _bootstrap_password() -> str:
    """The first administrator's password, or refuse to invent one in production."""
    configured = settings.BOOTSTRAP_ADMIN_PASSWORD.strip()
    if configured:
        return configured
    if settings.IS_PRODUCTION:
        raise RuntimeError(
            "BOOTSTRAP_ADMIN_PASSWORD is not set and no administrator exists yet. "
            "Set it in the environment before first start; refusing to create an "
            "account with a guessable password."
        )
    generated = secrets.token_urlsafe(18)
    print("")
    print("  No BOOTSTRAP_ADMIN_PASSWORD set. Created the first administrator with:")
    print(f"    {settings.BOOTSTRAP_ADMIN_EMAIL}")
    print(f"    {generated}")
    print("  This is shown once. Change it after logging in.")
    print("", flush=True)
    return generated


def bootstrap() -> None:
    """Create tables and, on a fresh install, the first administrator."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.execute(select(User).limit(1)).first() is None:
            db.add(User(
                email=settings.BOOTSTRAP_ADMIN_EMAIL.lower(),
                name=settings.BOOTSTRAP_ADMIN_NAME,
                password_hash=hash_password(_bootstrap_password()),
                role=Role.admin,
                is_active=True,
            ))
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(admin.router)
app.include_router(feeds.router)
app.include_router(public.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Auth guards raise a 307 carrying a Location header; honour it.
    location = (exc.headers or {}).get("Location")
    if location:
        return RedirectResponse(location, status_code=303)

    if exc.status_code == 404:
        with SessionLocal() as db:
            response = render(
                request, db, "public/404.html",
                meta_spec={"title": "Page not found", "path": str(request.url.path), "noindex": True},
                breadcrumbs=[],
            )
            response.status_code = 404
            return response

    if request.url.path.startswith("/admin"):
        return templates.TemplateResponse(
            request, "admin/error.html",
            {"request": request, "status": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )

    return HTMLResponse(
        f"<h1>{exc.status_code}</h1><p>{exc.detail}</p>", status_code=exc.status_code
    )
