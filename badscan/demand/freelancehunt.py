# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any

import httpx

API = "https://api.freelancehunt.com/v2/projects"

TAG_RE = re.compile(r"<[^>]+>")


def _plain(value: object) -> str:
    text = str(value or "")
    text = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _budget(attrs: dict) -> str:
    budget = attrs.get("budget")
    if isinstance(budget, dict):
        amount = budget.get("amount")
        currency = budget.get("currency") or ""
        if amount in (None, "", 0):
            return ""
        return f"{amount} {currency}".strip()
    if budget:
        return str(budget)
    return ""


def _web_url(item: dict, attrs: dict, project_id: str) -> str:
    links = item.get("links") or {}
    for key in ("html", "web", "private"):
        if links.get(key):
            return str(links[key])
    slug = attrs.get("slug") or attrs.get("url")
    if isinstance(slug, str) and slug.startswith("http"):
        return slug
    return f"https://freelancehunt.com/project/{project_id}.html"


def parse_project(item: dict) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else item
    project_id = str(item.get("id") or attrs.get("id") or "").strip()
    if not project_id:
        return None
    title = _plain(attrs.get("name") or attrs.get("title"))
    body = _plain(attrs.get("description") or attrs.get("description_html"))
    skills = attrs.get("skills") or []
    skill_names: list[str] = []
    if isinstance(skills, list):
        for skill in skills:
            if isinstance(skill, dict) and skill.get("name"):
                skill_names.append(str(skill["name"]))
    employer = ""
    relationships = item.get("relationships") or {}
    employer_block = relationships.get("employer") or {}
    employer_data = employer_block.get("data") if isinstance(employer_block, dict) else None
    if isinstance(employer_data, dict):
        employer = str(employer_data.get("id") or "")
    if isinstance(attrs.get("employer"), dict):
        employer = str(attrs["employer"].get("login") or attrs["employer"].get("first_name") or employer)
    published = str(attrs.get("published_at") or attrs.get("published") or "")
    return {
        "source": "freelancehunt",
        "external_id": project_id,
        "title": title[:300],
        "body": body[:4000],
        "url": _web_url(item, attrs, project_id),
        "budget": _budget(attrs),
        "author": employer[:120],
        "published_at": published,
        "skills": ", ".join(skill_names),
    }


def _page_params(page: int, skill_ids: list[int]) -> list[tuple[str, str]]:
    params = [("page[number]", str(page))]
    for skill_id in skill_ids:
        params.append(("filter[skill_id]", str(skill_id)))
    return params


def fetch_projects(client: httpx.Client, token: str, skill_ids: list[int], pages: int) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    collected: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        response = client.get(API, params=_page_params(page, skill_ids), headers=headers, timeout=40)
        if response.status_code == 400 and skill_ids:
            response = client.get(API, params=_page_params(page, []), headers=headers, timeout=40)
            skill_ids = []
        if response.status_code == 401:
            raise PermissionError("Freelancehunt отклонил токен. Возьми новый: https://freelancehunt.com/my/api")
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            break
        for item in items:
            parsed = parse_project(item)
            if parsed:
                collected.append(parsed)
        links = payload.get("links") if isinstance(payload, dict) else None
        if isinstance(links, dict) and not links.get("next"):
            break
    return collected
