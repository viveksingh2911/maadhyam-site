# Maadhyam International — events, notices and knowledge platform

A server-rendered site with a full admin portal, automatic SEO and Google Analytics.
Built with FastAPI, Jinja2 and SQLAlchemy; no build step, no Node.js.

---

## What it does

**Public site**

| Route | What it is |
| --- | --- |
| `/` | Hero, live stats, notice board, upcoming events, featured + latest articles, newsletter |
| `/events` | Upcoming / past / all, with search and category filters |
| `/events/{slug}` | Full detail, speakers, built-in registration form, `.ics` calendar download |
| `/notifications` | Notice board, filterable by urgency; live notices also scroll in the site-wide ticker |
| `/notifications/{slug}` | Full notice with linked page or downloadable attachment |
| `/articles` | Knowledge Lab — own writing plus curated link posts to external coverage |
| `/articles/{slug}` | Article with author card, related reading, share links |
| `/{slug}` | Editable standalone pages (About, Services, policies…) |
| `/contact` | Contact form with honeypot spam trap; messages land in the admin inbox |
| `/search` | Search across events, notices, articles and pages |
| `/sitemap.xml`, `/robots.txt`, `/rss.xml` | Generated live from published content |

**Admin portal** at `/admin`

- Dashboard: what is coming up, unread enquiries, recent signups, SEO health at a glance
- Events, Notifications, Articles and Pages: full create/edit/publish with a markdown
  editor (toolbar, live preview, image picker), scheduling, and per-item SEO
- Registrations per event, exportable as CSV
- Media library with drag-and-drop upload, reusable from any editor
- Categories, newsletter subscribers (CSV export), contact inbox
- Team accounts with administrator / editor roles
- Settings: identity, SEO, analytics, homepage copy, contact details, social links

---

## Automatic SEO

Nothing here needs an editor to remember anything. For every page the app derives:

- `<title>` from the site-wide template, `meta description` from the excerpt or
  summary (or the opening of the body), and a canonical URL from the slug
- Open Graph and Twitter card tags, falling back to the cover image then the
  site default share image
- JSON-LD structured data: `Organization` and `WebSite` on every page, plus
  `BreadcrumbList`, and `Event`, `BlogPosting`/`NewsArticle` or
  `SpecialAnnouncement` on the matching detail pages
- `sitemap.xml` with per-item `lastmod` and sensible priorities, `robots.txt`
  driven by the indexing switch, and an RSS feed
- Slugs, excerpts and reading time when those fields are left blank

Anything derived can be overridden per item in the editor's **SEO overrides**
panel, which also shows a live Google-result preview, character counters and a
health score with specific, fixable warnings. `/admin/seo` ranks every published
page worst-first and carries a launch checklist.

## Google Analytics

Paste a GA4 measurement ID (`G-XXXXXXXXXX`) in **Settings → Analytics** and it is
injected on every page. Google Tag Manager is supported alongside it. The
implementation sets Consent Mode v2 defaults to *denied* before any tag loads,
honours Do Not Track, and — with the consent banner enabled — loads nothing at
all until the visitor accepts.

---

## Branding and design

The design system is original — it does not copy maadhyaminternational.com. Colour
is authored in OKLCH so lightness steps stay perceptually even and the dark theme
is a token swap rather than a second stylesheet. Typography is Fraunces (display)
over Inter (body). Reduced-motion is respected, and the layout is verified down to
375px with no horizontal overflow.

Two brand assets are wired in and live in the media library, so they can be swapped
from **Settings** without touching code:

| Asset | Setting | Notes |
| --- | --- | --- |
| Maadhyam logo (transparent PNG) | `site_logo`, `site_favicon` | Dark ink on transparency, so dark mode gives it a light chip via `.brand-logo` |
| Seminar photograph | `home_hero_image` (+ `home_hero_image_alt`) | Shown at its own aspect ratio; the hero never crops a group shot |

The accent ramp is derived from the terracotta arc in the logo — `#B94927`,
i.e. `oklch(0.550 0.153 37)` — set once as `--hue-accent: 37` in both
`site.css` and `admin.css`.

Two things to note about the supplied files: the logo is 86×107, which is fine at
header size but will look soft on high-density screens — a larger export would
help. And because it contains the wordmark and strapline, it is illegible at 16px
favicon size; a square, mark-only version would read much better in a browser tab.

---

## Running it locally

```bash
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe seed.py
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Or just run `start.ps1`, which does all of the above.

- Public site: <http://127.0.0.1:8000>
- Admin portal: <http://127.0.0.1:8000/admin>

### First login

No password is built into the source. On a fresh database:

- **With `seed.py`** — two demo accounts are created, `admin@maadhyam.local` and
  `editor@maadhyam.local`. Their passwords are generated and printed once when
  the script runs. Set `SEED_ADMIN_PASSWORD` / `SEED_EDITOR_PASSWORD` beforehand
  to choose them yourself.
- **Without `seed.py`** — the first administrator comes from the
  `BOOTSTRAP_ADMIN_*` values in `.env`. Leave `BOOTSTRAP_ADMIN_PASSWORD` empty in
  development and one is generated and printed at startup. In production
  (`ENV=production`) an unset password aborts startup rather than creating a
  guessable account.

Either way the password is shown once, on the console. Change it after logging in.

`seed.py --reset` replaces the demo content.

---

## Project layout

```
app/
  main.py            FastAPI app, bootstrap, error handling, security headers
  config.py          Environment-driven settings
  database.py        Engine, session factory, declarative base
  models.py          Users, Events, Registrations, Notifications, Articles,
                     Pages, Media, Categories, Subscribers, Messages, Settings
  security.py        scrypt password hashing, signed session cookies, CSRF
  seo.py             Metadata derivation, JSON-LD builders, content health audit
  site_settings.py   Editor-managed key/value settings and their form definitions
  templating.py      Jinja environment, filters, and the automatic SEO context
  utils.py           Slugs, markdown, summarising, date formatting, uploads
  routers/
    public.py        Public pages, forms, registration, search
    admin.py         Admin portal
    feeds.py         sitemap.xml, robots.txt, rss.xml
  templates/         Jinja templates (public/, admin/, partials/)
  static/            site.css, admin.css, site.js, admin.js, images, uploads/
seed.py              Demo content
data/site.db         SQLite database (created on first run)
```

---

## Deploying

1. **Point `SITE_URL` at your real domain** in `.env`. Canonical tags, the
   sitemap, RSS and Open Graph URLs are all built from it.
2. Set a long random `SECRET_KEY`:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   Changing it later signs everyone out.
3. Set `DEBUG=false` and `COOKIE_SECURE=true` once you are serving over HTTPS.
4. Run behind a reverse proxy:
   `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2`
5. Serve `app/static/` directly from nginx/Caddy if you want; the app serves it
   otherwise.
6. In **Settings → SEO**, turn indexing on and paste the Search Console
   verification token, then submit `https://yourdomain/sitemap.xml` in Search
   Console.

**PostgreSQL instead of SQLite:** install `psycopg[binary]`, set
`DATABASE_URL=postgresql+psycopg://user:pass@host/dbname`, and change the
`provider` nothing else — SQLAlchemy handles the rest. Back up `data/site.db`
and `app/static/uploads/` if you stay on SQLite; between them they hold
everything.

There are no schema migrations wired up. If you change `models.py` after going
live, add Alembic (`pip install alembic`) before you do.

---

## Security notes

- Passwords are hashed with stdlib `scrypt` (n=16384, r=8, p=1) and a per-user salt.
- Admin sessions are signed, HTTP-only cookies with a 12-hour lifetime.
- Every state-changing admin form carries a per-session CSRF token.
- Uploads are extension-allowlisted, size-capped, and stored under a generated
  filename; deletion is confined to the uploads directory.
- Responses carry `X-Content-Type-Options`, `Referrer-Policy` and `X-Frame-Options`.
- The API docs (`/api/docs`) are exposed only while `DEBUG=true`.
