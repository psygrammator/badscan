# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

import httpx

PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


@dataclass
class PageSpeed:
    performance: int | None = None
    seo: int | None = None
    lcp_ms: int | None = None
    crux_lcp_ms: int | None = None
    crux_inp_ms: int | None = None
    crux_cls: float | None = None
    error: str | None = None


def _score_100(category: dict | None) -> int | None:
    if not category:
        return None
    raw = category.get("score")
    if raw is None:
        return None
    try:
        return int(round(float(raw) * 100))
    except (TypeError, ValueError):
        return None


def _audit_ms(audits: dict, key: str) -> int | None:
    audit = audits.get(key) or {}
    value = audit.get("numericValue")
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _crux_percentile(experience: dict | None, metric: str) -> int | None:
    if not experience:
        return None
    metrics = experience.get("metrics") or {}
    item = metrics.get(metric) or {}
    value = item.get("percentile")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_pagespeed(
    client: httpx.Client,
    url: str,
    api_key: str,
    strategy: str,
) -> PageSpeed:
    params = [
        ("url", url),
        ("strategy", strategy or "mobile"),
        ("category", "performance"),
        ("category", "seo"),
        ("locale", "ru"),
        ("key", api_key),
    ]
    try:
        response = client.get(PSI_URL, params=params, timeout=70)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        return PageSpeed(error=str(exc))
    except ValueError as exc:
        return PageSpeed(error=str(exc))

    lighthouse = payload.get("lighthouseResult") or {}
    categories = lighthouse.get("categories") or {}
    audits = lighthouse.get("audits") or {}
    experience = payload.get("loadingExperience") or payload.get("originLoadingExperience") or {}
    cls = None
    cls_raw = _crux_percentile(experience, "CUMULATIVE_LAYOUT_SHIFT_SCORE")
    if cls_raw is not None:
        cls = cls_raw / 100
    return PageSpeed(
        performance=_score_100(categories.get("performance")),
        seo=_score_100(categories.get("seo")),
        lcp_ms=_audit_ms(audits, "largest-contentful-paint"),
        crux_lcp_ms=_crux_percentile(experience, "LARGEST_CONTENTFUL_PAINT_MS"),
        crux_inp_ms=_crux_percentile(experience, "INTERACTION_TO_NEXT_PAINT"),
        crux_cls=cls,
    )
