# -*- coding: utf-8 -*-
"""Отпечаток CMS, контакты с публичной главной, признак украинского бизнеса."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from badscan.score import PHP_RE, WP_VER_RE, JQUERY_RE, looks_parked

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+380[\s\-()]*\d{2}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}"
    r"|0\d{2}[\s\-()]\d{3}[\s\-()]\d{2}[\s\-()]\d{2})(?!\d)"
)
CONTACT_HREF_RE = re.compile(r"(contact|kontak|контакт|зворотн|feedback)", re.IGNORECASE)
CITY_RE = re.compile(
    r"(харків|харьков|київ|киев|одес|львів|львов|дніпро|днепр|запоріж|запорож|"
    r"вінниц|винниц|полтав|суми|черніг|черкас|микола|херсон|івано-франк|терноп|"
    r"рівне|луцьк|ужгород|житомир|кропивницьк|чернівц|україн|украин)",
    re.IGNORECASE,
)

SKIP_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "sentry.io",
    "wixpress.com",
    "domain.com",
    "email.com",
    "mysite.com",
    "test.com",
    "schema.org",
    "wordpress.org",
    "w3.org",
    "sentry-next.wixpress.com",
}
SKIP_EMAIL_LOCAL = {"noreply", "no-reply", "donotreply", "wordpress", "wix", "email"}

CMS_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("wordpress", ("/wp-content/", "/wp-includes/", "/wp-json")),
    ("tilda", ("tildacdn.com", "tilda.ws", "t-records")),
    ("wix", ("wixstatic.com", "wix.com/site", "x-wix-")),
    ("bitrix", ("/bitrix/", "bitrix/js/", "x-powered-cms: bitrix")),
    ("opencart", ("catalog/view/theme", "index.php?route=")),
    ("horoshop", ("horoshop.ua", "/static/horoshop")),
    ("joomla", ("/media/system/js/", "/components/com_")),
    ("prestashop", ("var prestashop", "prestashop.min.js")),
    ("magento", ("mage/cookies", "magento_cache", "x-magento")),
    ("drupal", ("drupal.js", "sites/default/files", "drupal-settings")),
    ("weblium", ("weblium.com", "wl-page")),
    ("ucoz", ("ucoz.net", "ucoz.ru", "u-design")),
    ("nethouse", ("nethouse.ru", "nethouse.id")),
    ("modx", ("modxrevolution",)),
)


def decode_html(raw: bytes, content_type: str) -> str:
    head = raw[:4096].decode("latin1", errors="replace")
    charset = ""
    header_match = re.search(r"charset=\s*['\"]?([\w\-]+)", content_type or "", re.IGNORECASE)
    meta_match = re.search(
        r"charset\s*=\s*['\"]?\s*([\w\-]+)|charset=['\"]\s*([\w\-]+)",
        head,
        re.IGNORECASE,
    )
    if meta_match:
        charset = next(group for group in meta_match.groups() if group)
    elif header_match:
        charset = header_match.group(1)
    if charset:
        try:
            return raw.decode(charset, errors="replace")
        except LookupError:
            pass
    return raw.decode("utf-8", errors="replace")


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("380") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 10:
        return "+38" + digits
    return ""


def _keep_email(email: str) -> bool:
    email = email.lower().strip(".")
    if "@" not in email:
        return False
    local, _, domain = email.partition("@")
    if domain in SKIP_EMAIL_DOMAINS or domain.endswith(".png") or domain.endswith(".jpg"):
        return False
    if local in SKIP_EMAIL_LOCAL:
        return False
    if len(local) < 2 or len(domain) < 4:
        return False
    return True


def detect_cms(html: str, generator: str, header_blob: str) -> tuple[str | None, str | None]:
    blob = f"{html}\n{header_blob}".lower()
    gen = generator or ""
    gen_l = gen.lower()
    version = None
    cms = None
    if "wordpress" in gen_l or any(sig in blob for sig in CMS_RULES[0][1]):
        cms = "wordpress"
        match = WP_VER_RE.search(gen)
        if match:
            version = match.group(1) + "." + match.group(2)
    elif "tilda" in gen_l:
        cms = "tilda"
    elif "wix" in gen_l:
        cms = "wix"
    elif "bitrix" in gen_l or "1c-bitrix" in gen_l:
        cms = "bitrix"
    elif "joomla" in gen_l:
        cms = "joomla"
    else:
        for name, signatures in CMS_RULES:
            if name == "wordpress":
                continue
            if any(sig in blob for sig in signatures):
                cms = name
                break
    if cms is None and "cdn.prom.ua" in blob:
        cms = "prom"
    return cms, version


def ukraine_confidence(domain: str, lang: str, text: str, phones: list[str]) -> int:
    score = 0
    host = domain.lower()
    if host.endswith(".ua") or ".ua." in host:
        score += 45
    lang_l = (lang or "").lower()
    if lang_l.startswith("uk"):
        score += 25
    elif lang_l.startswith("ru") and host.endswith(".ua"):
        score += 10
    if phones:
        score += 20
    sample = text[:8000]
    if CITY_RE.search(sample):
        score += 15
    if re.search(r"(грн|₴|\buah\b)", sample, re.IGNORECASE):
        score += 10
    return min(100, score)


def analyze_html(
    html: str,
    final_url: str,
    headers: dict[str, str],
    domain: str,
) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    generator = ""
    gen_tag = soup.find("meta", attrs={"name": re.compile(r"^generator$", re.I)})
    if gen_tag and gen_tag.get("content"):
        generator = str(gen_tag.get("content")).strip()
    viewport = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)}) is not None
    title_tag = soup.find("title")
    title = title_tag.get_text(" ", strip=True) if title_tag else ""
    html_tag = soup.find("html")
    lang = ""
    if html_tag and html_tag.get("lang"):
        lang = str(html_tag.get("lang")).strip()

    phones: list[str] = []
    emails: list[str] = []
    contact_url = None
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        low = href.lower()
        if low.startswith("mailto:"):
            mail = href.split(":", 1)[1].split("?", 1)[0]
            if _keep_email(mail):
                emails.append(mail.lower())
        elif low.startswith("tel:"):
            phone = _normalize_phone(href.split(":", 1)[1])
            if phone:
                phones.append(phone)
        elif contact_url is None and CONTACT_HREF_RE.search(href):
            contact_url = urljoin(final_url, href)

    for match in EMAIL_RE.findall(html):
        if _keep_email(match):
            emails.append(match.lower())
    for match in PHONE_RE.findall(html):
        phone = _normalize_phone(match)
        if phone:
            phones.append(phone)

    def uniq(items: list[str], limit: int) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
            if len(out) >= limit:
                break
        return out

    phones = uniq(phones, 5)
    emails = uniq(emails, 5)

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible = soup.get_text(" ", strip=True)

    header_blob = "\n".join(f"{key}: {value}" for key, value in headers.items())
    cms, cms_version = detect_cms(html, generator, header_blob)
    if domain.endswith(".prom.ua") or domain == "prom.ua":
        cms = "prom"

    jquery = None
    jq = JQUERY_RE.search(html)
    if jq:
        major = jq.group(1) or jq.group(3)
        minor = jq.group(2) or jq.group(4)
        if major and minor:
            jquery = f"{major}.{minor}"

    php_version = None
    php = PHP_RE.search(header_blob)
    if php:
        php_version = f"{php.group(1)}.{php.group(2)}"

    server = headers.get("server") or headers.get("Server")
    ukraine = ukraine_confidence(domain, lang, f"{title}\n{visible}", phones)
    return {
        "title": title[:300],
        "snippet": re.sub(r"\s+", " ", visible)[:500],
        "lang": lang[:32],
        "generator": generator[:180] or None,
        "viewport": viewport,
        "cms": cms,
        "cms_version": cms_version,
        "jquery": jquery,
        "php_version": php_version,
        "server": (server or "")[:120] or None,
        "phones": phones,
        "emails": emails,
        "contact_url": contact_url,
        "ukraine": ukraine,
        "visible_chars": len(visible),
        "parked": looks_parked(title, visible),
    }
