# -*- coding: utf-8 -*-
"""Публічна HTML-видача. З неї беремо сайти компаній, каталоги і ЗМІ викидаємо."""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from badscan.domains import domain_from_input, is_blocked_platform, is_skipped_public_sector

# Агрегатори, маркетплейси і ЗМІ. На них оффер «переробимо ваш сайт» не лягає.
SKIP_DIRECTORIES: frozenset[str] = frozenset(
    {
        "olx.ua",
        "prom.ua",
        "rozetka.ua",
        "epicentr.ua",
        "epicentrk.ua",
        "comfy.ua",
        "allo.ua",
        "foxtrot.com.ua",
        "silpo.ua",
        "atbmarket.com",
        "novus.ua",
        "eva.ua",
        "lun.ua",
        "rieltor.ua",
        "dom.ria.com",
        "flatfy.ua",
        "100realty.ua",
        "address.ua",
        "2gis.ua",
        "goldenpages.ua",
        "ua-region.com.ua",
        "spr.ua",
        "firm.ua",
        "list.in.ua",
        "catalog.i.ua",
        "work.ua",
        "rabota.ua",
        "robota.ua",
        "dou.ua",
        "jooble.org",
        "flagma.ua",
        "besplatka.ua",
        "booking.com",
        "tripadvisor.com",
        "pravda.com.ua",
        "rbc.ua",
        "unian.ua",
        "nv.ua",
        "tsn.ua",
        "24tv.ua",
        "korrespondent.net",
        "obozrevatel.com",
        "focus.ua",
        "ukrinform.ua",
        "bbc.com",
        "suspilne.media",
        "duckduckgo.com",
        "bing.com",
        "t.me",
        "telegram.org",
        "tiktok.com",
        "wikipedia.org",
    }
)

SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "uk,ru;q=0.9,en;q=0.5",
}


def unwrap_href(href: str) -> str:
    raw = (href or "").strip()
    if raw.startswith("//"):
        raw = "https:" + raw
    if "uddg=" in raw:
        parsed = urlparse(raw)
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return target
    return raw


def is_skipped_result(domain: str) -> bool:
    if is_blocked_platform(domain) or is_skipped_public_sector(domain):
        return True
    return any(domain == blocked or domain.endswith("." + blocked) for blocked in SKIP_DIRECTORIES)


def parse_ddg_html(html: str) -> tuple[list[tuple[str, str]], dict[str, str] | None]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[tuple[str, str]] = []
    for anchor in soup.select("a.result__a"):
        href = unwrap_href(str(anchor.get("href") or ""))
        title = anchor.get_text(" ", strip=True)
        if href.startswith("http"):
            rows.append((href, title))
    nxt: dict[str, str] | None = None
    for form in soup.select("form"):
        if form.select_one("input[name='s']") is None:
            continue
        data: dict[str, str] = {}
        for field in form.select("input[name]"):
            data[str(field.get("name"))] = str(field.get("value") or "")
        if data.get("q"):
            nxt = data
        break
    return rows, nxt


class SearchBlocked(RuntimeError):
    """Видача закрила доступ капчею або 403. Повторний штурм тільки подовжує бан."""


def _blocked(response: httpx.Response) -> bool:
    if response.status_code in {202, 403, 429, 503}:
        return True
    sample = response.text[:2500].lower()
    return "confirm this search was made by a human" in sample or "bots use duckduckgo" in sample


def search_ddg(client: httpx.Client, query: str, pages: int) -> list[tuple[str, str]]:
    payload: dict[str, str] = {"q": query, "kl": "ua-uk"}
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index in range(max(1, pages)):
        if index:
            time.sleep(2.5)
        response = client.post("https://html.duckduckgo.com/html/", data=payload, timeout=30)
        if _blocked(response):
            raise SearchBlocked(
                "DuckDuckGo закрив видачу капчею. Зачекай близько години і запусти hunt знову. "
                "Поки що візьму локальний список ніш."
            )
        response.raise_for_status()
        batch, nxt = parse_ddg_html(response.text)
        for url, title in batch:
            if url in seen:
                continue
            seen.add(url)
            found.append((url, title))
        if not nxt:
            break
        payload = nxt
    return found


def domain_of_result(url: str) -> str:
    domain = domain_from_input(url)
    if not domain or is_skipped_result(domain):
        return ""
    return domain
