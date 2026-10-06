# -*- coding: utf-8 -*-
"""Хосты и публичные суффиксы UA. Регистрируемый домен = метка + суффикс."""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Подмножество Public Suffix List для Украины. Нужно, чтобы www.firma.kh.ua
# схлопывался в firma.kh.ua, а не в kh.ua.
UA_PUBLIC_SUFFIXES: frozenset[str] = frozenset(
    {
        "com.ua",
        "co.ua",
        "net.ua",
        "org.ua",
        "in.ua",
        "pp.ua",
        "biz.ua",
        "gov.ua",
        "edu.ua",
        "mil.ua",
        "kiev.ua",
        "kyiv.ua",
        "kh.ua",
        "kharkov.ua",
        "kharkiv.ua",
        "od.ua",
        "odessa.ua",
        "odesa.ua",
        "lviv.ua",
        "dp.ua",
        "dnipro.ua",
        "dnepropetrovsk.ua",
        "zp.ua",
        "zaporozhye.ua",
        "vn.ua",
        "vinnica.ua",
        "cn.ua",
        "chernigov.ua",
        "ck.ua",
        "cherkassy.ua",
        "cv.ua",
        "chernovtsy.ua",
        "if.ua",
        "te.ua",
        "km.ua",
        "pl.ua",
        "rv.ua",
        "uz.ua",
        "zt.ua",
        "mk.ua",
        "nikolaev.ua",
        "ks.ua",
        "kherson.ua",
        "crimea.ua",
        "donetsk.ua",
        "dn.ua",
        "lugansk.ua",
        "sumy.ua",
        "poltava.ua",
        "sm.ua",
        "yalta.ua",
        "sebastopol.ua",
        "uzhgorod.ua",
        "rovno.ua",
        "lutsk.ua",
        "ivano-frankivsk.ua",
        "ternopil.ua",
        "zhytomyr.ua",
    }
)

SKIP_DISCOVER_SUFFIXES: frozenset[str] = frozenset({"gov.ua", "edu.ua", "mil.ua"})

# Площадки, с которых оффер «сделаем вам сайт» бессмысленен.
BLOCK_REGISTRABLE: frozenset[str] = frozenset(
    {
        "google.com",
        "google.com.ua",
        "youtube.com",
        "facebook.com",
        "instagram.com",
        "wikipedia.org",
        "telegram.org",
        "t.me",
        "vk.com",
        "ok.ru",
        "twitter.com",
        "x.com",
        "amazon.com",
        "cloudflare.com",
        "microsoft.com",
        "apple.com",
        "linkedin.com",
        "github.com",
        "gitlab.com",
        "wordpress.org",
        "wordpress.com",
        "blogspot.com",
        "medium.com",
        "tiktok.com",
        "netflix.com",
        "yahoo.com",
        "bing.com",
        "live.com",
        "office.com",
        "adobe.com",
        "cloudfront.net",
        "amazonaws.com",
        "akamaihd.net",
        "doubleclick.net",
    }
)

_HOST_RE = re.compile(r"^[a-z0-9.-]+$")


def canonical_host(host: str) -> str:
    host = (host or "").strip().lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if host.endswith("."):
        host = host[:-1]
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    if not host or not _HOST_RE.match(host):
        return ""
    if ".." in host or host.startswith("-") or host.endswith("-"):
        return ""
    return host


def registrable_domain(host: str) -> str:
    host = canonical_host(host)
    if not host:
        return ""
    labels = host.split(".")
    for i in range(len(labels)):
        suffix = ".".join(labels[i:])
        if suffix in UA_PUBLIC_SUFFIXES and i > 0:
            return ".".join(labels[i - 1 :])
    if len(labels) >= 2:
        return ".".join(labels[-2:])
    return host


def is_skipped_public_sector(domain: str) -> bool:
    return any(domain == suffix or domain.endswith("." + suffix) for suffix in SKIP_DISCOVER_SUFFIXES)


def is_blocked_platform(domain: str) -> bool:
    domain = registrable_domain(domain)
    if domain in BLOCK_REGISTRABLE:
        return True
    return any(domain == blocked or domain.endswith("." + blocked) for blocked in BLOCK_REGISTRABLE)


def host_from_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw or raw.startswith("#"):
        return ""
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""
    if parsed.hostname is None:
        return ""
    return canonical_host(parsed.hostname)


def domain_from_input(line: str) -> str:
    host = host_from_url(line)
    if not host:
        return ""
    return registrable_domain(host)


def load_seed_lines(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        domain = domain_from_input(stripped)
        if not domain or domain in seen:
            continue
        seen.add(domain)
        found.append(domain)
    return found
