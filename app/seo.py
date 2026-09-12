"""Automatic SEO: derived metadata, structured data and content health checks.

Nothing here needs an editor to fill anything in. Titles, descriptions, canonical
URLs, Open Graph tags and JSON-LD are all derived from the content itself; the
optional per-item SEO fields simply override the derived values.
"""
from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urljoin

from .config import settings
from .models import Article, Event, Notification, Page
from .utils import fmt_date, strip_html, summarise

MAX_TITLE = 60
MIN_TITLE = 20
MAX_DESC = 160
MIN_DESC = 70


def absolute_url(path: str | None) -> str:
    if not path:
        return settings.SITE_URL
    if path.startswith(("http://", "https://")):
        return path
    return urljoin(settings.SITE_URL + "/", path.lstrip("/"))


def _iso(value: datetime | None) -> str | None:
    return value.replace(microsecond=0).isoformat() if value else None


def build_meta(
    cfg: dict[str, str],
    *,
    title: str,
    description: str | None = None,
    path: str = "/",
    image: str | None = None,
    kind: str = "website",
    published_at: datetime | None = None,
    updated_at: datetime | None = None,
    author: str | None = None,
    canonical: str | None = None,
    noindex: bool = False,
    keywords: list[str] | None = None,
) -> dict:
    """Everything the <head> needs, with sensible fallbacks for every field."""
    site_name = cfg.get("site_name") or settings.APP_NAME
    template = cfg.get("seo_title_template") or "{title} | {site}"
    full_title = (
        site_name
        if not title or title.strip().lower() == site_name.strip().lower()
        else template.replace("{title}", title.strip()).replace("{site}", site_name)
    )

    desc = summarise(description or cfg.get("site_description", ""), MAX_DESC)
    share_image = absolute_url(image or cfg.get("seo_default_og_image") or "/static/img/og-default.svg")
    indexing_off = str(cfg.get("seo_indexing_enabled", "1")) not in {"1", "true", "on", "yes"}

    return {
        "title": full_title,
        "raw_title": title,
        "description": desc,
        "canonical": canonical or absolute_url(path),
        "image": share_image,
        "type": kind,
        "site_name": site_name,
        "locale": cfg.get("site_locale") or "en_IN",
        "twitter_handle": cfg.get("seo_twitter_handle") or "",
        "published_time": _iso(published_at),
        "modified_time": _iso(updated_at or published_at),
        "author": author,
        "keywords": ", ".join(keywords) if keywords else "",
        "robots": "noindex, nofollow" if (noindex or indexing_off) else "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1",
    }


# --------------------------------------------------------------------------- #
# JSON-LD builders
# --------------------------------------------------------------------------- #

def _clean(obj):
    """Drop None/empty values so the emitted JSON-LD stays tidy."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if v not in (None, "", [], {})}
    if isinstance(obj, list):
        return [_clean(v) for v in obj if v not in (None, "", [], {})]
    return obj


def organization_schema(cfg: dict[str, str]) -> dict:
    same_as = [
        cfg.get(key)
        for key in (
            "social_x", "social_linkedin", "social_instagram",
            "social_facebook", "social_youtube",
        )
        if cfg.get(key)
    ]
    return _clean({
        "@type": cfg.get("seo_organization_type") or "Organization",
        "@id": f"{settings.SITE_URL}/#organization",
        "name": cfg.get("site_name"),
        "url": settings.SITE_URL,
        "description": cfg.get("site_description"),
        "logo": absolute_url(cfg.get("site_logo")) if cfg.get("site_logo") else None,
        "email": cfg.get("contact_email"),
        "telephone": cfg.get("contact_phone"),
        "address": {"@type": "PostalAddress", "streetAddress": cfg.get("contact_address")}
        if cfg.get("contact_address") else None,
        "sameAs": same_as,
    })


def website_schema(cfg: dict[str, str]) -> dict:
    return _clean({
        "@type": "WebSite",
        "@id": f"{settings.SITE_URL}/#website",
        "url": settings.SITE_URL,
        "name": cfg.get("site_name"),
        "description": cfg.get("site_description"),
        "inLanguage": cfg.get("site_language") or "en",
        "publisher": {"@id": f"{settings.SITE_URL}/#organization"},
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{settings.SITE_URL}/search?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    })


def breadcrumb_schema(trail: list[tuple[str, str]]) -> dict | None:
    if len(trail) < 2:
        return None
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": absolute_url(url)}
            for i, (name, url) in enumerate(trail, start=1)
        ],
    }


def article_schema(cfg: dict[str, str], article: Article) -> dict:
    return _clean({
        "@type": "NewsArticle" if article.source_name else "BlogPosting",
        "@id": absolute_url(f"/articles/{article.slug}") + "#article",
        "headline": article.title[:110],
        "description": article.meta_description or summarise(article.excerpt or article.body_html),
        "image": absolute_url(article.cover_image) if article.cover_image else None,
        "datePublished": _iso(article.published_at or article.created_at),
        "dateModified": _iso(article.updated_at),
        "inLanguage": cfg.get("site_language") or "en",
        "keywords": ", ".join(article.tag_list) or None,
        "wordCount": len(strip_html(article.body_html).split()) or None,
        "articleSection": article.category.name if article.category else None,
        "author": {"@type": "Person", "name": article.author.name} if article.author
        else {"@id": f"{settings.SITE_URL}/#organization"},
        "publisher": {"@id": f"{settings.SITE_URL}/#organization"},
        "mainEntityOfPage": {"@type": "WebPage", "@id": absolute_url(f"/articles/{article.slug}")},
        "isBasedOn": article.external_url or None,
    })


def event_schema(cfg: dict[str, str], event: Event) -> dict:
    mode_map = {
        "online": "https://schema.org/OnlineEventAttendanceMode",
        "hybrid": "https://schema.org/MixedEventAttendanceMode",
        "in_person": "https://schema.org/OfflineEventAttendanceMode",
    }
    if event.mode == "online":
        location = {"@type": "VirtualLocation", "url": event.online_url or absolute_url(f"/events/{event.slug}")}
    else:
        location = {
            "@type": "Place",
            "name": event.venue_name or cfg.get("site_name"),
            "address": _clean({
                "@type": "PostalAddress",
                "streetAddress": event.address,
                "addressLocality": event.city,
                "addressCountry": event.country,
            }),
        }
    return _clean({
        "@type": "Event",
        "@id": absolute_url(f"/events/{event.slug}") + "#event",
        "name": event.title,
        "description": event.meta_description or summarise(event.summary or event.body_html),
        "image": absolute_url(event.cover_image) if event.cover_image else None,
        "startDate": _iso(event.start_at),
        "endDate": _iso(event.end_at),
        "eventAttendanceMode": mode_map.get(event.mode),
        "eventStatus": "https://schema.org/EventScheduled",
        "location": location,
        "url": absolute_url(f"/events/{event.slug}"),
        "organizer": {
            "@type": "Organization",
            "name": event.organizer or cfg.get("site_name"),
            "url": settings.SITE_URL,
        },
        "performer": [{"@type": "Person", "name": s.split(" - ")[0].strip()} for s in event.speaker_list] or None,
        "maximumAttendeeCapacity": event.capacity,
        "offers": _clean({
            "@type": "Offer",
            "price": "0" if event.is_free else (event.price or None),
            "priceCurrency": event.currency,
            "availability": "https://schema.org/InStock",
            "url": event.registration_url or absolute_url(f"/events/{event.slug}"),
            "validFrom": _iso(event.created_at),
        }),
    })


def notification_schema(cfg: dict[str, str], note: Notification) -> dict:
    return _clean({
        "@type": "SpecialAnnouncement",
        "@id": absolute_url(f"/notifications/{note.slug}") + "#announcement",
        "name": note.title,
        "text": summarise(note.summary or note.body_html, 300),
        "datePosted": _iso(note.published_at or note.created_at),
        "expires": _iso(note.expires_at),
        "url": absolute_url(f"/notifications/{note.slug}"),
        "publisher": {"@id": f"{settings.SITE_URL}/#organization"},
    })


def page_schema(cfg: dict[str, str], page: Page) -> dict:
    return _clean({
        "@type": "WebPage",
        "@id": absolute_url(f"/{page.slug}"),
        "name": page.title,
        "description": page.meta_description or summarise(page.subtitle or page.body_html),
        "dateModified": _iso(page.updated_at),
        "isPartOf": {"@id": f"{settings.SITE_URL}/#website"},
    })


def jsonld_graph(*nodes) -> str:
    graph = [n for n in nodes if n]
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Content health checks (surfaced in the admin portal)
# --------------------------------------------------------------------------- #

def audit_item(obj, cfg: dict[str, str]) -> list[dict]:
    """Return actionable SEO issues for a single piece of content."""
    issues: list[dict] = []

    def add(level: str, field: str, message: str) -> None:
        issues.append({"level": level, "field": field, "message": message})

    # Messages read as a sentence after the field name, so they never repeat it.
    title = (getattr(obj, "meta_title", None) or getattr(obj, "title", "") or "").strip()
    if not title:
        add("error", "title", "Missing.")
    elif len(title) > MAX_TITLE:
        add("warn", "title", f"{len(title)} characters - Google usually truncates past {MAX_TITLE}.")
    elif len(title) < MIN_TITLE:
        add("warn", "title", "Very short - add context so it reads well in results.")

    desc = (getattr(obj, "meta_description", None) or "").strip()
    fallback = summarise(
        getattr(obj, "excerpt", None) or getattr(obj, "summary", None) or getattr(obj, "body_html", None)
    )
    effective = desc or fallback
    if not effective:
        add("error", "meta_description", "Nothing to fall back on - add an excerpt or write one here.")
    elif len(effective) < MIN_DESC:
        add("warn", "meta_description", f"Only {len(effective)} characters - aim for {MIN_DESC} to {MAX_DESC}.")
    elif len(effective) > MAX_DESC + 20:
        add("warn", "meta_description", "Too long - it will be cut off in search results.")

    image = getattr(obj, "og_image", None) or getattr(obj, "cover_image", None) or getattr(obj, "hero_image", None)
    if not image and not cfg.get("seo_default_og_image"):
        add("warn", "share_image", "None set - links will look plain when shared.")
    if getattr(obj, "cover_image", None) and not (getattr(obj, "cover_alt", None) or "").strip():
        add("warn", "cover_alt", "Missing - needed for screen readers and image search.")

    body = strip_html(getattr(obj, "body_html", None) or "")
    if isinstance(obj, Article) and not obj.external_url and len(body.split()) < 300:
        add("info", "body", f"Only {len(body.split())} words - long-form pieces rank more reliably.")

    if getattr(obj, "noindex", False):
        add("info", "noindex", "Excluded from search engines on purpose.")

    keyword = (getattr(obj, "focus_keyword", None) or "").strip().lower()
    if keyword:
        if keyword not in title.lower():
            add("warn", "focus_keyword", "Does not appear in the title.")
        if keyword not in body.lower():
            add("info", "focus_keyword", "Does not appear in the body text.")

    slug = getattr(obj, "slug", "") or ""
    if len(slug) > 75:
        add("info", "slug", "Long - shorter URLs are easier to share.")

    return issues


def score_from_issues(issues: list[dict]) -> int:
    penalty = sum({"error": 25, "warn": 10, "info": 3}.get(i["level"], 5) for i in issues)
    return max(0, 100 - penalty)


def score_band(score: int) -> str:
    if score >= 90:
        return "good"
    if score >= 70:
        return "ok"
    return "poor"


def sitemap_entry(loc: str, lastmod: datetime | None, changefreq: str, priority: str) -> dict:
    return {
        "loc": absolute_url(loc),
        "lastmod": fmt_date(lastmod, "%Y-%m-%d") if lastmod else None,
        "changefreq": changefreq,
        "priority": priority,
    }
