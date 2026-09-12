"""Machine-readable endpoints: sitemap, robots.txt, RSS and the events feed.

These are generated from live content, so a newly published item appears in the
sitemap and feed immediately - no manual step, no plugin.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import seo
from ..database import get_db
from ..models import Article, Event, Notification, Page, Status, utcnow
from ..site_settings import as_bool, load_settings
from ..utils import summarise

router = APIRouter()

XML_HEADERS = {"Cache-Control": "public, max-age=3600"}


def _xml(body: str) -> Response:
    return Response(body, media_type="application/xml", headers=XML_HEADERS)


@router.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)):
    entries: list[dict] = [
        seo.sitemap_entry("/", utcnow(), "daily", "1.0"),
        seo.sitemap_entry("/events", utcnow(), "daily", "0.9"),
        seo.sitemap_entry("/articles", utcnow(), "daily", "0.9"),
        seo.sitemap_entry("/notifications", utcnow(), "daily", "0.8"),
        seo.sitemap_entry("/contact", None, "yearly", "0.5"),
    ]

    for page in db.execute(
        select(Page).where(Page.status == Status.published, Page.noindex.is_(False))
    ).scalars():
        entries.append(seo.sitemap_entry(f"/{page.slug}", page.updated_at, "monthly", "0.7"))

    for article in db.execute(
        select(Article).where(Article.status == Status.published, Article.noindex.is_(False))
        .order_by(Article.published_at.desc())
    ).scalars():
        entries.append(seo.sitemap_entry(f"/articles/{article.slug}", article.updated_at, "monthly", "0.8"))

    for event in db.execute(
        select(Event).where(Event.status == Status.published, Event.noindex.is_(False))
        .order_by(Event.start_at.desc())
    ).scalars():
        priority = "0.9" if not event.is_past else "0.6"
        entries.append(seo.sitemap_entry(f"/events/{event.slug}", event.updated_at, "weekly", priority))

    for note in db.execute(
        select(Notification).where(Notification.status == Status.published, Notification.noindex.is_(False))
        .order_by(Notification.published_at.desc())
    ).scalars():
        entries.append(seo.sitemap_entry(f"/notifications/{note.slug}", note.updated_at, "weekly", "0.6"))

    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for entry in entries:
        parts.append("  <url>")
        parts.append(f"    <loc>{escape(entry['loc'])}</loc>")
        if entry["lastmod"]:
            parts.append(f"    <lastmod>{entry['lastmod']}</lastmod>")
        parts.append(f"    <changefreq>{entry['changefreq']}</changefreq>")
        parts.append(f"    <priority>{entry['priority']}</priority>")
        parts.append("  </url>")
    parts.append("</urlset>")
    return _xml("\n".join(parts))


@router.get("/robots.txt")
def robots(db: Session = Depends(get_db)):
    cfg = load_settings(db)
    lines = ["User-agent: *"]
    if as_bool(cfg, "seo_indexing_enabled"):
        lines += [
            "Allow: /",
            "Disallow: /admin",
            "Disallow: /search",
            "Disallow: /*?q=",
        ]
    else:
        lines.append("Disallow: /")
    extra = (cfg.get("seo_robots_extra") or "").strip()
    if extra:
        lines.append(extra)
    lines += ["", f"Sitemap: {seo.absolute_url('/sitemap.xml')}"]
    return Response("\n".join(lines) + "\n", media_type="text/plain", headers=XML_HEADERS)


@router.get("/rss.xml")
def rss(db: Session = Depends(get_db)):
    cfg = load_settings(db)
    articles = list(
        db.execute(
            select(Article).where(Article.status == Status.published)
            .order_by(Article.published_at.desc()).limit(30)
        ).scalars()
    )
    items = []
    for a in articles:
        link = a.external_url or seo.absolute_url(f"/articles/{a.slug}")
        pub = (a.published_at or a.created_at).strftime("%a, %d %b %Y %H:%M:%S +0000")
        items.append(
            "    <item>\n"
            f"      <title>{escape(a.title)}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f"      <guid isPermaLink=\"true\">{escape(seo.absolute_url(f'/articles/{a.slug}'))}</guid>\n"
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <description>{escape(summarise(a.excerpt or a.body_html, 300))}</description>\n"
            "    </item>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{escape(cfg.get('site_name', ''))} - Knowledge Lab</title>\n"
        f"    <link>{escape(seo.absolute_url('/articles'))}</link>\n"
        f"    <description>{escape(cfg.get('site_description', ''))}</description>\n"
        f"    <language>{escape(cfg.get('site_language', 'en'))}</language>\n"
        f"    <atom:link href=\"{escape(seo.absolute_url('/rss.xml'))}\" rel=\"self\" type=\"application/rss+xml\"/>\n"
        + "\n".join(items) +
        "\n  </channel>\n</rss>"
    )
    return _xml(body)
