# -*- coding: utf-8 -*-
from __future__ import annotations

import json

import httpx

from badscan.domains import (
    UA_PUBLIC_SUFFIXES,
    canonical_host,
    host_from_url,
    is_blocked_platform,
    is_skipped_public_sector,
    registrable_domain,
)
from badscan.net import make_client

COLLINFO = "https://index.commoncrawl.org/collinfo.json"


def resolve_crawl_id(client: httpx.Client, crawl_id: str) -> str:
    if crawl_id and crawl_id != "latest":
        return crawl_id
    response = client.get(COLLINFO, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and str(item.get("id", "")).startswith("CC-MAIN-"):
                return str(item["id"])
    raise RuntimeError("Common Crawl не отдал id коллекции")


def consider_domain(host: str, zone: str = "") -> str | None:
    domain = registrable_domain(host)
    if not domain or domain in UA_PUBLIC_SUFFIXES or domain.count(".") < 1:
        return None
    if is_skipped_public_sector(domain) or is_blocked_platform(domain):
        return None
    if zone and not (domain == zone or domain.endswith("." + zone)):
        return None
    return domain


def parse_cdx_line(line: str) -> str | None:
    line = line.strip()
    if not line:
        return None
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    url = str(payload.get("url") or "")
    host = host_from_url(url)
    if not host:
        return None
    return consider_domain(host)


def domains_from_crt(records: list, zone: str, limit: int) -> list[str]:
    zone = canonical_host(zone.lstrip("*."))
    found: list[str] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        blob = str(record.get("name_value") or record.get("common_name") or "")
        for line in blob.splitlines():
            name = line.strip().lower()
            if not name or name.startswith("*."):
                continue
            domain = consider_domain(name, zone)
            if not domain or domain in seen:
                continue
            seen.add(domain)
            found.append(domain)
            if len(found) >= limit:
                return found
    return found


def discover_crt(client: httpx.Client, zone: str, limit: int) -> list[tuple[str, str]]:
    zone = canonical_host(zone.lstrip("*.").strip())
    if not zone:
        return []
    response = client.get(
        "https://crt.sh/",
        params={"q": f"%.{zone}", "output": "json", "exclude": "expired"},
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []
    return [(domain, f"https://{domain}/") for domain in domains_from_crt(payload, zone, limit)]


def discover_zone(
    client: httpx.Client,
    crawl_id: str,
    zone: str,
    limit: int,
) -> list[tuple[str, str]]:
    zone = canonical_host(zone.lstrip("*.").strip())
    if not zone:
        return []
    endpoint = f"https://index.commoncrawl.org/{crawl_id}-index"
    pages = 1
    try:
        info = client.get(endpoint, params={"url": f"*.{zone}", "showNumPages": "true"}, timeout=30)
        if info.status_code == 200:
            pages = max(1, int(info.json().get("pages") or 1))
    except (httpx.HTTPError, ValueError, TypeError):
        pages = 1
    pages = min(pages, 12)
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for page in range(pages):
        try:
            response = client.get(
                endpoint,
                params=[
                    ("url", f"*.{zone}"),
                    ("output", "json"),
                    ("fl", "url"),
                    ("page", str(page)),
                ],
                timeout=40,
            )
        except httpx.HTTPError:
            continue
        if response.status_code != 200 or response.text.lstrip().startswith("<"):
            continue
        for line in response.text.splitlines():
            domain = parse_cdx_line(line)
            if not domain or domain in seen:
                continue
            if not (domain == zone or domain.endswith("." + zone)):
                continue
            seen.add(domain)
            found.append((domain, f"https://{domain}/"))
            if len(found) >= limit:
                return found
    return found


def make_discover_client(user_agent: str) -> httpx.Client:
    return make_client(user_agent, 40)
