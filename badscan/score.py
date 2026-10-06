# -*- coding: utf-8 -*-
"""Чистая оценка главной. Чем выше bad_score, тем слабее сайт и тем уместнее оффер."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PARKED_RE = re.compile(
    r"(домен\s+(?:прода|не\s+прив)|domain\s+(?:is\s+)?for sale|sedoparking|hugedomains|"
    r"this domain (?:may be|is) for sale|припаркован|related searches|buy this domain)",
    re.IGNORECASE,
)

APACHE_OLD_RE = re.compile(r"Apache/2\.[0-2]", re.IGNORECASE)
IIS_OLD_RE = re.compile(r"IIS/[5-7]\.", re.IGNORECASE)
PHP_RE = re.compile(r"PHP/(\d+)\.(\d+)", re.IGNORECASE)
WP_VER_RE = re.compile(r"wordpress\s*(\d+)\.(\d+(?:\.\d+)*)", re.IGNORECASE)
JQUERY_RE = re.compile(r"jquery(?:-(\d+)\.(\d+)(?:\.\d+)?|/(\d+)\.(\d+))", re.IGNORECASE)


@dataclass
class Features:
    domain: str
    requested_url: str
    final_url: str = ""
    status_code: int | None = None
    ttfb_ms: int | None = None
    https: bool = False
    tls_error: bool = False
    redirect_count: int = 0
    html_bytes: int = 0
    compressed: bool = False
    viewport: bool = False
    title: str = ""
    snippet: str = ""
    lang: str = ""
    cms: str | None = None
    cms_version: str | None = None
    generator: str | None = None
    jquery: str | None = None
    php_version: str | None = None
    server: str | None = None
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    contact_url: str | None = None
    ukraine: int = 0
    visible_chars: int = 0
    parked: bool = False
    error: str | None = None


@dataclass
class Scored:
    features: Features
    bad_score: int
    issues: list[str]
    pitch: str


def _php_major(php_version: str | None) -> int | None:
    if not php_version:
        return None
    match = re.match(r"(\d+)", php_version)
    if not match:
        return None
    return int(match.group(1))


def _wp_major(version: str | None) -> int | None:
    if not version:
        return None
    match = re.match(r"(\d+)", version)
    if not match:
        return None
    return int(match.group(1))


def _jquery_major(jquery: str | None) -> int | None:
    if not jquery:
        return None
    match = re.match(r"(\d+)", jquery)
    if not match:
        return None
    return int(match.group(1))


def score_features(features: Features) -> Scored:
    if features.error and features.status_code is None:
        return Scored(features, 0, [], "")
    if features.parked:
        return Scored(features, 0, ["домен на парковке, не клиент"], "")

    issues: list[str] = []
    score = 0

    def add(points: int, text: str) -> None:
        nonlocal score
        score += points
        issues.append(text)

    if features.tls_error:
        add(14, "битый TLS")
    elif not features.https:
        add(18, "нет HTTPS")

    if features.status_code is not None and features.status_code >= 500:
        add(26, f"HTTP {features.status_code}")
    elif features.status_code is not None and features.status_code >= 400:
        add(10, f"HTTP {features.status_code}")

    ttfb = features.ttfb_ms
    if ttfb is not None:
        if ttfb >= 5000:
            add(28, f"TTFB {ttfb / 1000:.1f} с")
        elif ttfb >= 3000:
            add(22, f"TTFB {ttfb / 1000:.1f} с")
        elif ttfb >= 1500:
            add(14, f"TTFB {ttfb / 1000:.1f} с")
        elif ttfb >= 800:
            add(8, f"TTFB {ttfb / 1000:.1f} с")

    cms = (features.cms or "").lower()
    version = features.cms_version or ""
    if cms == "wordpress":
        major = _wp_major(version)
        if major is not None and major < 6:
            add(22, f"старый WordPress {version}")
        elif version:
            add(16, f"WordPress {version}")
        else:
            add(16, "WordPress")
    elif cms in {"tilda", "wix", "ucoz", "nethouse", "weblium"}:
        add(14, cms.capitalize())
    elif cms == "prom":
        add(14, "витрина на Prom, своего сайта нет")
    elif cms in {"joomla", "bitrix", "opencart", "prestashop", "magento", "modx", "drupal", "horoshop"}:
        label = f"{cms} {version}".strip()
        add(12, label)

    php_major = _php_major(features.php_version)
    if php_major is not None and php_major < 8:
        add(10, f"PHP {features.php_version}")

    if not features.viewport and features.status_code and features.status_code < 400:
        add(12, "нет viewport, мобильные отваливаются")

    if not features.compressed and features.html_bytes > 80_000:
        add(6, "без сжатия")

    if features.html_bytes > 800_000:
        add(8, f"HTML {features.html_bytes / 1_000_000:.1f} МБ")
    elif features.html_bytes > 400_000:
        add(4, f"HTML {features.html_bytes // 1000} КБ")

    jq = _jquery_major(features.jquery)
    if jq == 1:
        add(8, f"jQuery {features.jquery}")
    elif jq == 2:
        add(4, f"jQuery {features.jquery}")

    if features.redirect_count >= 3:
        add(6, f"{features.redirect_count} редиректа")

    server = features.server or ""
    if APACHE_OLD_RE.search(server) or IIS_OLD_RE.search(server):
        add(6, f"старый {server.split()[0]}")

    if (
        features.status_code == 200
        and features.visible_chars < 180
        and features.html_bytes < 25_000
        and not features.error
    ):
        add(14, "пустая заглушка")

    if not (features.title or "").strip() and features.status_code == 200:
        add(4, "пустой title")

    score = max(0, min(100, score))
    pitch = ""
    if score >= 25 and issues:
        pitch = (
            "; ".join(issues[:4])
            + ". Аудит: скорость, мобильная воронка, что чинить первым."
        )
    return Scored(features, score, issues, pitch)


def apply_pagespeed(scored: Scored, performance: int | None, lcp_ms: int | None) -> Scored:
    issues = list(scored.issues)
    score = scored.bad_score
    if performance is not None:
        if performance <= 30:
            score += 16
            issues.append(f"Lighthouse {performance}/100")
        elif performance <= 49:
            score += 10
            issues.append(f"Lighthouse {performance}/100")
        elif performance <= 70:
            score += 4
            issues.append(f"Lighthouse {performance}/100")
    if lcp_ms is not None and lcp_ms >= 4000:
        score += 6
        issues.append(f"LCP {lcp_ms / 1000:.1f} с")
    elif lcp_ms is not None and lcp_ms >= 2500:
        score += 3
        issues.append(f"LCP {lcp_ms / 1000:.1f} с")
    score = max(0, min(100, score))
    pitch = ""
    if score >= 25 and issues:
        pitch = "; ".join(issues[:4]) + ". Аудит: скорость, мобильная воронка, что чинить первым."
    return Scored(scored.features, score, issues, pitch)


def looks_parked(title: str, text: str) -> bool:
    blob = f"{title}\n{text[:1500]}"
    return PARKED_RE.search(blob) is not None
