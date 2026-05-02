"""Website-scraping implementation of ``enrich.find_email``.

Strategy (in order, first hit wins):

1. Fetch the homepage. Parse all ``<a href="mailto:...">`` links.
   These are explicit — high confidence.
2. If no mailto links on the homepage, fetch the most likely contact-
   ish pages (``/contact``, ``/contact-us``, ``/about``, ``/about-us``,
   ``/team``). Same mailto check.
3. As a last-resort fallback, regex-scan the fetched HTML for raw
   ``foo@bar.tld`` strings. Filter out obvious noise (image filenames,
   ``example.com``, ``sentry.io``, common asset CDNs). Medium confidence.

Polite by default: 5s connect / 10s read timeout, single short
User-Agent, NO recursive crawling. We fetch at most 6 pages per lead
(home + 5 candidate paths), then give up."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from blufire.http import build_session
from blufire.logging_setup import get_logger
from blufire.runtime.context import RunContext
from blufire.runtime.tool import ToolRegistry
from blufire.runtime.tools._base import BaseTool
from blufire.runtime.tools.enrich import FindEmailInput, FindEmailOutput

USER_AGENT = "BlufireBot/1.0 (+contact: blufire ops)"
TIMEOUT = (5, 10)  # (connect, read)
CANDIDATE_PATHS = ("", "/contact", "/contact-us", "/about", "/about-us", "/team")

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Domains that are almost never the prospect's own contact email — they
# show up because of analytics, error reporting, support widgets, image
# CDNs, or common attribution links. Filter aggressively.
_BLOCKED_DOMAINS = frozenset(
    [
        "example.com",
        "example.org",
        "sentry.io",
        "wordpress.com",
        "squarespace.com",
        "wixsite.com",
        "godaddy.com",
        "google.com",
        "googleapis.com",
        "gmail.com",  # owners rarely use gmail.com on a corp site as the contact
        "facebook.com",
        "twitter.com",
        "instagram.com",
        "linkedin.com",
        "youtube.com",
        "vimeo.com",
        "intercom.io",
        "zendesk.com",
        "salesforce.com",
        "hubspot.com",
        "mailchimp.com",
    ]
)

# Filename-looking strings the email regex sometimes catches.
_BLOCKED_PATTERNS = (
    re.compile(r"\.(png|jpg|jpeg|gif|webp|svg|css|js|woff2?|ttf|eot)\b", re.I),
    re.compile(r"@\d+x\b"),  # retina image suffixes
    re.compile(r"sentry@"),
)


def _looks_real(email: str) -> bool:
    domain = email.split("@", 1)[1].lower() if "@" in email else ""
    if domain in _BLOCKED_DOMAINS:
        return False
    return all(not pat.search(email) for pat in _BLOCKED_PATTERNS)


def _normalize(url: str) -> str:
    """Coerce a raw website field (often missing scheme) into an https URL."""
    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url


class WebsiteFindEmailTool(BaseTool[FindEmailInput, FindEmailOutput]):
    name = "enrich.find_email"
    description = "Scrape a website for mailto links + obvious email patterns."
    input_schema = FindEmailInput
    output_schema = FindEmailOutput

    def invoke(self, ctx: RunContext, payload: FindEmailInput) -> FindEmailOutput:
        if not payload.website_url:
            return FindEmailOutput(email=None, confidence="none", source="no_website")

        log = get_logger("blufire.enrich.website").bind(tenant_id=ctx.tenant.id)
        session = build_session()
        session.headers.update({"User-Agent": USER_AGENT})

        base = _normalize(payload.website_url)
        candidates: list[tuple[str, BeautifulSoup, str]] = []

        for path in CANDIDATE_PATHS:
            url = urljoin(base, path) if path else base
            try:
                resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
            except requests.RequestException as exc:
                log.debug("enrich_fetch_failed", path=path, error_class=type(exc).__name__)
                continue
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            candidates.append((url, soup, resp.text))

            # Pass 1: mailto links from THIS page only — return immediately
            # on the first hit (highest confidence).
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.lower().startswith("mailto:"):
                    email = href.split(":", 1)[1].split("?")[0].strip()
                    if _looks_real(email):
                        return FindEmailOutput(
                            email=email.lower(), confidence="high", source=f"mailto:{path or '/'}"
                        )

        # Pass 2: regex-scan all the HTML we already fetched. Lower
        # confidence — these can be misfires.
        for url, _, html in candidates:
            for hit in _EMAIL_RE.findall(html):
                if _looks_real(hit):
                    return FindEmailOutput(
                        email=hit.lower(),
                        confidence="medium",
                        source=f"regex:{urlparse(url).path or '/'}",
                    )

        return FindEmailOutput(email=None, confidence="none", source="not_found")


def register(tools: ToolRegistry) -> None:
    """Register the website-scraping enrichment tool. Called by bootstrap
    when ``settings.enrich.provider == "website"``."""
    if tools.get("enrich.find_email") is None:
        tools.register(WebsiteFindEmailTool())
