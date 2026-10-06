# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from typing import Any

import httpx

from badscan.config import Settings
from badscan.db import utc_now
from badscan.extract import analyze_html, decode_html
from badscan.net import RateLimiter, make_client
from badscan.pagespeed import fetch_pagespeed
from badscan.score import Features, apply_pagespeed, score_features

MAX_BYTES = 1_200_000


def _header_map(headers: httpx.Headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        out[key.lower()] = value
    return out


def _is_tls_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("certificate", "tls", "ssl", "handshake"))


def _read_capped(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if size >= MAX_BYTES:
            break
    return b"".join(chunks)[:MAX_BYTES]


def fetch_home(client: httpx.Client, url: str, limiter: RateLimiter) -> tuple[httpx.Response, bytes, int]:
    limiter.wait()
    started = time.perf_counter()
    with client.stream("GET", url) as response:
        ttfb_ms = int((time.perf_counter() - started) * 1000)
        body = _read_capped(response)
        return response, body, ttfb_ms


def _candidate_urls(domain: str) -> list[str]:
    hosts = [domain]
    if not domain.startswith("www."):
        hosts.append("www." + domain)
    urls: list[str] = []
    for host in hosts:
        urls.append(f"https://{host}/")
    for host in hosts:
        urls.append(f"http://{host}/")
    return urls


def probe_domain(domain: str, settings: Settings, limiter: RateLimiter, *, use_psi: bool = True) -> dict[str, Any]:
    tls_error = False
    last_error = "нет ответа"
    client = make_client(settings.user_agent, settings.timeout_sec, verify=True)
    insecure_client: httpx.Client | None = None
    try:
        for url in _candidate_urls(domain):
            active = client
            try:
                response, body, ttfb_ms = fetch_home(active, url, limiter)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                if url.startswith("https://") and _is_tls_error(exc):
                    tls_error = True
                    if insecure_client is None:
                        insecure_client = make_client(settings.user_agent, settings.timeout_sec, verify=False)
                    try:
                        response, body, ttfb_ms = fetch_home(insecure_client, url, limiter)
                    except httpx.HTTPError as retry_exc:
                        last_error = str(retry_exc)
                        continue
                else:
                    continue
            return _record_from_response(
                domain,
                url,
                response,
                body,
                ttfb_ms,
                tls_error,
                settings,
                limiter,
                use_psi=use_psi,
            )
    finally:
        client.close()
        if insecure_client is not None:
            insecure_client.close()

    features = Features(
        domain=domain,
        requested_url=f"https://{domain}/",
        tls_error=tls_error,
        error=last_error[:400],
    )
    scored = score_features(features)
    return _row(scored, psi=None, error=features.error)


def _record_from_response(
    domain: str,
    requested_url: str,
    response: httpx.Response,
    body: bytes,
    ttfb_ms: int,
    tls_error: bool,
    settings: Settings,
    limiter: RateLimiter,
    *,
    use_psi: bool,
) -> dict[str, Any]:
    del limiter
    headers = _header_map(response.headers)
    content_type = headers.get("content-type", "").lower()
    stripped = body.lstrip()
    looks_html = (
        not content_type
        or "html" in content_type
        or content_type.startswith("text/")
        or stripped.startswith((b"<", b"<!"))
    )
    if content_type.startswith(("image/", "video/", "audio/")) or "application/pdf" in content_type:
        looks_html = False
    html = decode_html(body, content_type) if looks_html else ""
    extracted = analyze_html(html, str(response.url), headers, domain) if html else {
        "title": "",
        "snippet": "",
        "lang": "",
        "generator": None,
        "viewport": False,
        "cms": None,
        "cms_version": None,
        "jquery": None,
        "php_version": None,
        "server": headers.get("server"),
        "phones": [],
        "emails": [],
        "contact_url": None,
        "ukraine": 45 if domain.endswith(".ua") else 0,
        "visible_chars": 0,
        "parked": False,
    }
    encoding = headers.get("content-encoding", "")
    compressed = any(token in encoding.lower() for token in ("gzip", "br", "deflate", "zstd"))
    final_url = str(response.url)
    features = Features(
        domain=domain,
        requested_url=requested_url,
        final_url=final_url,
        status_code=response.status_code,
        ttfb_ms=ttfb_ms,
        https=final_url.startswith("https://"),
        tls_error=tls_error,
        redirect_count=len(response.history),
        html_bytes=len(body),
        compressed=compressed,
        viewport=bool(extracted["viewport"]),
        title=extracted["title"],
        snippet=extracted.get("snippet") or "",
        lang=extracted["lang"],
        cms=extracted["cms"],
        cms_version=extracted["cms_version"],
        generator=extracted["generator"],
        jquery=extracted["jquery"],
        php_version=extracted["php_version"],
        server=extracted["server"],
        phones=list(extracted["phones"]),
        emails=list(extracted["emails"]),
        contact_url=extracted["contact_url"],
        ukraine=int(extracted["ukraine"]),
        visible_chars=int(extracted["visible_chars"]),
        parked=bool(extracted["parked"]),
        error=None,
    )
    scored = score_features(features)
    psi = None
    if (
        use_psi
        and settings.pagespeed_key
        and scored.bad_score >= settings.pagespeed_min_local_score
        and features.status_code
        and features.status_code < 400
    ):
        psi_client = make_client(settings.user_agent, settings.timeout_sec)
        try:
            psi = fetch_pagespeed(psi_client, final_url, settings.pagespeed_key, settings.pagespeed_strategy)
        finally:
            psi_client.close()
        if psi and not psi.error:
            scored = apply_pagespeed(scored, psi.performance, psi.lcp_ms)
    return _row(scored, psi=psi, error=None)


def _row(scored, psi, error: str | None) -> dict[str, Any]:
    features = scored.features
    return {
        "domain": features.domain,
        "url": features.requested_url,
        "final_url": features.final_url or None,
        "status_code": features.status_code,
        "ttfb_ms": features.ttfb_ms,
        "https": 1 if features.https else 0,
        "tls_error": 1 if features.tls_error else 0,
        "cms": features.cms,
        "cms_version": features.cms_version,
        "title": features.title or None,
        "snippet": features.snippet or None,
        "lang": features.lang or None,
        "html_bytes": features.html_bytes,
        "compressed": 1 if features.compressed else 0,
        "viewport": 1 if features.viewport else 0,
        "jquery": features.jquery,
        "php_version": features.php_version,
        "server": features.server,
        "generator": features.generator,
        "redirect_count": features.redirect_count,
        "ukraine": features.ukraine,
        "bad_score": scored.bad_score,
        "issues": " | ".join(scored.issues),
        "phones": "; ".join(features.phones),
        "emails": "; ".join(features.emails),
        "contact_url": features.contact_url,
        "pitch": scored.pitch,
        "psi_performance": None if psi is None else psi.performance,
        "psi_seo": None if psi is None else psi.seo,
        "psi_lcp_ms": None if psi is None else psi.lcp_ms,
        "crux_lcp_ms": None if psi is None else psi.crux_lcp_ms,
        "crux_inp_ms": None if psi is None else psi.crux_inp_ms,
        "crux_cls": None if psi is None else psi.crux_cls,
        "scanned_at": utc_now(),
        "error": error,
    }
