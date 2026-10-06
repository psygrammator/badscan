# -*- coding: utf-8 -*-
from __future__ import annotations

import re

from badscan.db import utc_now

_LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁёІіЇїЄєҐґ]")


def readable_title(title: str, body: str) -> str:
    chunks = []
    if title:
        chunks.extend(title.splitlines())
    if body:
        chunks.extend(body.splitlines())
    for line in chunks:
        stripped = line.strip()
        if _LETTER_RE.search(stripped):
            return stripped[:300]
    return (title or body or "").strip()[:300]


def lead_row(raw: dict, matched: list[str]) -> dict:
    return {
        "source": raw["source"],
        "external_id": raw["external_id"],
        "title": readable_title(raw.get("title") or "", raw.get("body") or ""),
        "body": raw.get("body") or "",
        "url": raw.get("url") or "",
        "budget": raw.get("budget") or "",
        "author": raw.get("author") or "",
        "published_at": raw.get("published_at") or "",
        "matched": ", ".join(matched[:12]),
        "fetched_at": utc_now(),
    }


def format_digest(leads: list[dict]) -> str:
    lines = [f"Новые заявки на сайт: {len(leads)}"]
    for lead in leads[:15]:
        budget = f" · {lead['budget']}" if lead.get("budget") else ""
        title = (lead.get("title") or "").replace("\n", " ")
        lines.append(f"• {title[:140]}{budget}\n{lead.get('url') or ''}")
    if len(leads) > 15:
        lines.append(f"…ещё {len(leads) - 15} в отчёте")
    text = "\n".join(lines)
    return text[:3900]


def send_telegram(token: str, chat_id: str, text: str, user_agent: str) -> None:
    import httpx

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = httpx.post(
        url,
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        headers={"User-Agent": user_agent},
        timeout=30,
    )
    response.raise_for_status()
