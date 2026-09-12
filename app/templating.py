"""Jinja2 environment: shared filters, globals and the common render context."""
from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import seo, utils
from .config import BASE_DIR, settings
from .models import Notification, Page, Status, utcnow
from .site_settings import as_bool, load_settings

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

templates.env.filters.update(
    markdown=utils.render_markdown,
    strip_html=utils.strip_html,
    summarise=utils.summarise,
    fmt_date=utils.fmt_date,
    fmt_datetime=utils.fmt_datetime,
    fmt_event_range=utils.fmt_event_range,
    time_ago=utils.time_ago,
    countdown=utils.countdown_label,
    dt_local=utils.dt_local,
    initials=utils.initials,
    slugify=utils.slugify,
)


def static_url(path: str) -> str:
    """Append a content stamp so browsers pick up CSS/JS edits after a deploy."""
    relative = path.lstrip("/").removeprefix("static/")
    target = BASE_DIR / "static" / relative
    try:
        stamp = int(target.stat().st_mtime)
    except OSError:
        return path
    return f"{path}?v={stamp}"


templates.env.globals.update(
    now=utcnow,
    current_year=lambda: utcnow().year,
    abs_url=seo.absolute_url,
    jsonld=seo.jsonld_graph,
    site_url=settings.SITE_URL,
    static_url=static_url,
)


def nav_pages(db: Session) -> list[Page]:
    stmt = (
        select(Page)
        .where(Page.status == Status.published, Page.show_in_nav.is_(True))
        .order_by(Page.nav_order, Page.title)
    )
    return list(db.execute(stmt).scalars())


def ticker_notifications(db: Session, limit: int = 6) -> list[Notification]:
    now = utcnow()
    stmt = (
        select(Notification)
        .where(
            Notification.status == Status.published,
            Notification.show_in_ticker.is_(True),
            (Notification.expires_at.is_(None)) | (Notification.expires_at > now),
        )
        .order_by(Notification.pinned.desc(), Notification.published_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


def base_context(request: Request, db: Session) -> dict:
    """Context every public template relies on."""
    cfg = load_settings(db)
    return {
        "request": request,
        "cfg": cfg,
        "nav_pages": nav_pages(db),
        "ticker": ticker_notifications(db),
        "analytics": {
            "ga_id": cfg.get("ga_measurement_id", "").strip(),
            "gtm_id": cfg.get("gtm_container_id", "").strip(),
            "anonymize_ip": as_bool(cfg, "analytics_anonymize_ip"),
            "respect_dnt": as_bool(cfg, "analytics_respect_dnt"),
            "cookie_banner": as_bool(cfg, "analytics_cookie_banner"),
        },
        "org_schema": seo.organization_schema(cfg),
        "website_schema": seo.website_schema(cfg),
    }


def build_page_seo(cfg: dict[str, str], request: Request, ctx: dict) -> tuple[dict, list]:
    """Derive <head> metadata and JSON-LD from whatever object the view supplied.

    Views never have to assemble meta tags: hand `render()` an `article`, `event`,
    `note` or `page` object (or a small `meta_spec` dict for index pages) and the
    title, description, canonical URL, share image and structured data follow.
    """
    path = request.url.path
    spec: dict = dict(ctx.get("meta_spec") or {})
    nodes: list = []

    article = ctx.get("article")
    event = ctx.get("event")
    note = ctx.get("note")
    page = ctx.get("page") if not ctx.get("meta_spec") else None

    if article is not None:
        spec = {
            "title": article.meta_title or article.title,
            "description": article.meta_description or article.excerpt or utils.strip_html(article.body_html),
            "path": f"/articles/{article.slug}",
            "image": article.og_image or article.cover_image,
            "kind": "article",
            "published_at": article.published_at,
            "updated_at": article.updated_at,
            "author": article.author.name if article.author else None,
            "canonical": article.canonical_url,
            "noindex": article.noindex,
            "keywords": article.tag_list,
        }
        nodes.append(seo.article_schema(cfg, article))
    elif event is not None:
        spec = {
            "title": event.meta_title or event.title,
            "description": event.meta_description or event.summary or utils.strip_html(event.body_html),
            "path": f"/events/{event.slug}",
            "image": event.og_image or event.cover_image,
            "kind": "article",
            "published_at": event.created_at,
            "updated_at": event.updated_at,
            "canonical": event.canonical_url,
            "noindex": event.noindex,
        }
        nodes.append(seo.event_schema(cfg, event))
    elif note is not None:
        spec = {
            "title": note.meta_title or note.title,
            "description": note.meta_description or note.summary or utils.strip_html(note.body_html),
            "path": f"/notifications/{note.slug}",
            "image": note.og_image,
            "kind": "article",
            "published_at": note.published_at,
            "updated_at": note.updated_at,
            "canonical": note.canonical_url,
            "noindex": note.noindex,
        }
        nodes.append(seo.notification_schema(cfg, note))
    elif page is not None:
        spec = {
            "title": page.meta_title or page.title,
            "description": page.meta_description or page.subtitle or utils.strip_html(page.body_html),
            "path": f"/{page.slug}",
            "image": page.og_image or page.hero_image,
            "updated_at": page.updated_at,
            "canonical": page.canonical_url,
            "noindex": page.noindex,
        }
        nodes.append(seo.page_schema(cfg, page))

    spec.setdefault("title", cfg.get("site_name", settings.APP_NAME))
    spec.setdefault("description", cfg.get("site_description"))
    spec.setdefault("path", path)

    crumbs = seo.breadcrumb_schema(ctx.get("breadcrumbs") or [])
    if crumbs:
        nodes.append(crumbs)

    return seo.build_meta(cfg, **spec), nodes


def render(request: Request, db: Session, template: str, **extra):
    context = base_context(request, db)
    context.update(extra)
    meta, nodes = build_page_seo(context["cfg"], request, context)
    context["meta"] = meta
    context["jsonld_block"] = seo.jsonld_graph(
        context["org_schema"], context["website_schema"], *nodes
    )
    return templates.TemplateResponse(request, template, context)
