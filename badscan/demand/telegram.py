# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BUDGET_RE = re.compile(
    r"(\d[\d\s\u00a0\u202f]{0,14})\s*(UAH|USD|EUR|грн|uah|usd|eur|\$|€)",
    re.IGNORECASE,
)


def _budget(text: str) -> str:
    match = BUDGET_RE.search(text or "")
    if not match:
        return ""
    amount = re.sub(r"\s+", " ", match.group(1)).strip()
    return f"{amount} {match.group(2)}"


def parse_telegram_html(html: str, channel: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    leads: list[dict[str, Any]] = []
    for message in soup.select("div.tgme_widget_message"):
        external_id = str(message.get("data-post") or "").strip()
        text_node = message.select_one(".tgme_widget_message_text")
        text = text_node.get_text("\n", strip=True) if text_node else ""
        if not external_id or not text:
            continue
        link = message.select_one("a.tgme_widget_message_date")
        url = ""
        if link and link.get("href"):
            url = str(link.get("href"))
        if not url:
            url = f"https://t.me/{external_id}"
        published = ""
        time_node = message.select_one("time")
        if time_node and time_node.get("datetime"):
            published = str(time_node.get("datetime"))
        first_line = text.splitlines()[0][:300]
        leads.append(
            {
                "source": "telegram",
                "external_id": external_id,
                "title": first_line,
                "body": text[:4000],
                "url": url,
                "budget": _budget(text),
                "author": channel,
                "published_at": published,
            }
        )
    return leads


def next_page(html: str, current_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    more = soup.select_one("a.tme_messages_more")
    if more and more.get("href"):
        return urljoin(current_url, str(more.get("href")))
    prev = soup.find("link", attrs={"rel": "prev"})
    if prev and prev.get("href"):
        return urljoin(current_url, str(prev.get("href")))
    return None


def fetch_channel(client: httpx.Client, channel: str, pages: int) -> list[dict[str, Any]]:
    channel = channel.strip().lstrip("@")
    url = f"https://t.me/s/{channel}"
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _ in range(max(1, pages)):
        response = client.get(url, timeout=30)
        response.raise_for_status()
        html = response.text
        for lead in parse_telegram_html(html, channel):
            if lead["external_id"] in seen:
                continue
            seen.add(lead["external_id"])
            collected.append(lead)
        nxt = next_page(html, url)
        if not nxt or nxt == url:
            break
        url = nxt
    return collected
