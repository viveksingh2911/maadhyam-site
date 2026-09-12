"""Editor-managed site settings stored as key/value rows in the `settings` table."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Setting

# key -> (default value, group, label, input type, help text)
DEFAULTS: dict[str, tuple[str, str, str, str, str]] = {
    # Identity
    "site_name": ("Maadhyam International", "identity", "Site name", "text", "Used in titles and schema."),
    "site_tagline": (
        "Mediation and arbitration, resolved with dignity",
        "identity", "Tagline", "text", "Short line shown beside the logo and in the hero.",
    ),
    "site_description": (
        "Maadhyam International is an institution for mediation, arbitration and "
        "alternative dispute resolution - training neutrals, convening dialogue and "
        "resolving disputes with dignity.",
        "identity", "Default meta description", "textarea",
        "Fallback description for any page without its own. Aim for 150-160 characters.",
    ),
    "site_logo": ("", "identity", "Logo", "media", "Square or wide PNG/SVG shown in the header."),
    "site_favicon": ("", "identity", "Favicon", "media", "32x32 PNG or an SVG."),
    "site_locale": ("en_IN", "identity", "Locale", "text", "Open Graph locale, e.g. en_IN."),
    "site_language": ("en", "identity", "Language code", "text", "Used on the html lang attribute."),

    # Contact
    "contact_email": ("info@maadhyaminternational.com", "contact", "Contact email", "text", ""),
    "contact_phone": ("+91 74474 43877", "contact", "Contact phone", "text", ""),
    "contact_address": ("New Delhi, India", "contact", "Address", "textarea", ""),
    "contact_hours": ("Mon-Fri, 10:00-18:00 IST", "contact", "Office hours", "text", ""),
    "map_embed_url": ("", "contact", "Map embed URL", "text", "Google Maps embed src (optional)."),

    # Social
    "social_x": ("https://x.com/MaadhyamIntADR", "social", "X (Twitter)", "text", ""),
    "social_linkedin": ("https://www.linkedin.com/company/maadhyaminternational/", "social", "LinkedIn", "text", ""),
    "social_instagram": ("https://www.instagram.com/maadhyamintadr", "social", "Instagram", "text", ""),
    "social_facebook": ("https://www.facebook.com/people/Maadhyam-Int-Adr/", "social", "Facebook", "text", ""),
    "social_youtube": ("", "social", "YouTube", "text", ""),
    "social_whatsapp": ("https://wa.me/917447443877", "social", "WhatsApp", "text", ""),

    # SEO
    "seo_title_template": (
        "{title} | {site}", "seo", "Title template", "text",
        "Placeholders: {title} and {site}. Applied to every page automatically.",
    ),
    "seo_default_og_image": ("", "seo", "Default share image", "media", "1200x630 PNG or JPG."),
    "seo_twitter_handle": ("@MaadhyamIntADR", "seo", "X / Twitter handle", "text", ""),
    "seo_organization_type": ("Organization", "seo", "Schema.org type", "text", "e.g. Organization, LegalService, NGO."),
    "seo_google_verification": ("", "seo", "Google Search Console token", "text", "Value of the google-site-verification meta tag."),
    "seo_bing_verification": ("", "seo", "Bing verification token", "text", ""),
    "seo_robots_extra": ("", "seo", "Extra robots.txt lines", "textarea", "Appended to the generated robots.txt."),
    "seo_indexing_enabled": ("1", "seo", "Allow search engines to index the site", "bool",
                             "Turn off while the site is being built, on before launch."),

    # Analytics
    "ga_measurement_id": ("", "analytics", "Google Analytics 4 ID", "text", "Looks like G-XXXXXXXXXX."),
    "gtm_container_id": ("", "analytics", "Google Tag Manager ID", "text", "Looks like GTM-XXXXXXX. Optional."),
    "analytics_anonymize_ip": ("1", "analytics", "Anonymise IP addresses", "bool", "Recommended for GDPR/DPDP alignment."),
    "analytics_respect_dnt": ("1", "analytics", "Respect Do Not Track", "bool", "Skip analytics for visitors who opt out."),
    "analytics_cookie_banner": ("1", "analytics", "Show cookie consent banner", "bool",
                                "Analytics only loads after the visitor accepts."),

    # Homepage content
    "home_hero_eyebrow": ("Alternative Dispute Resolution", "home", "Hero eyebrow", "text", ""),
    "home_hero_title": ("Resolve disputes without losing the relationship.", "home", "Hero title", "text", ""),
    "home_hero_body": (
        "We convene mediators, arbitrators and institutions to settle complex disputes "
        "with speed, confidentiality and mutual respect.",
        "home", "Hero body", "textarea", "",
    ),
    "home_hero_primary_label": ("Explore our events", "home", "Primary button label", "text", ""),
    "home_hero_primary_url": ("/events", "home", "Primary button link", "text", ""),
    "home_hero_secondary_label": ("Read the Knowledge Lab", "home", "Secondary button label", "text", ""),
    "home_hero_secondary_url": ("/articles", "home", "Secondary button link", "text", ""),
    "home_hero_image": ("", "home", "Hero image", "media", "Optional. A clean 4:3 or 16:10 photo works best."),
    "home_hero_image_alt": (
        "", "home", "Hero image alt text", "text",
        "Describe the photo for screen readers and image search. Leave blank only if it is decorative.",
    ),
    "home_stat_1_value": ("500+", "home", "Stat 1 value", "text", ""),
    "home_stat_1_label": ("Disputes mediated", "home", "Stat 1 label", "text", ""),
    "home_stat_2_value": ("120", "home", "Stat 2 value", "text", ""),
    "home_stat_2_label": ("Accredited neutrals", "home", "Stat 2 label", "text", ""),
    "home_stat_3_value": ("18", "home", "Stat 3 value", "text", ""),
    "home_stat_3_label": ("Cities reached", "home", "Stat 3 label", "text", ""),
    "home_stat_4_value": ("94%", "home", "Stat 4 value", "text", ""),
    "home_stat_4_label": ("Settlement rate", "home", "Stat 4 label", "text", ""),
    "newsletter_heading": ("Stay close to the practice", "home", "Newsletter heading", "text", ""),
    "newsletter_body": (
        "Monthly notes on mediation, arbitration and the events worth your calendar.",
        "home", "Newsletter body", "textarea", "",
    ),

    # Footer
    "footer_note": (
        "Maadhyam International is an independent institution for alternative dispute resolution.",
        "footer", "Footer note", "textarea", "",
    ),
    "footer_credit": ("", "footer", "Extra footer credit line", "text", ""),
}

GROUPS = [
    ("identity", "Identity", "Name, logo and the description search engines fall back to."),
    ("seo", "SEO", "Title patterns, share images and verification tokens."),
    ("analytics", "Analytics", "Google Analytics 4, Tag Manager and consent."),
    ("home", "Homepage", "Hero copy, statistics and the newsletter block."),
    ("contact", "Contact", "Details shown in the footer, contact page and schema."),
    ("social", "Social", "Profile links, also emitted as sameAs in structured data."),
    ("footer", "Footer", "Small print."),
]


def load_settings(db: Session) -> dict[str, str]:
    """All settings with defaults filled in for keys that were never saved."""
    values = {key: spec[0] for key, spec in DEFAULTS.items()}
    for row in db.query(Setting).all():
        if row.value is not None:
            values[row.key] = row.value
    return values


def save_settings(db: Session, updates: dict[str, str]) -> None:
    for key, value in updates.items():
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
    db.commit()


def as_bool(values: dict[str, str], key: str) -> bool:
    return str(values.get(key, "")).strip() in {"1", "true", "True", "on", "yes"}
