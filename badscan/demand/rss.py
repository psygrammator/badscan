# -*- coding: utf-8 -*-
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import httpx


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _child_text(node: ET.Element, name: str) -> str:
    for child in list(node):
        if _local(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def parse_feed(xml_text: str, feed_url: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    leads: list[dict[str, Any]] = []
    for node in root.iter():
        kind = _local(node.tag)
        if kind not in {"item", "entry"}:
            continue
        title = _child_text(node, "title")
        body = _child_text(node, "description") or _child_text(node, "summary") or _child_text(node, "content")
        link = _child_text(node, "link")
        if not link:
            for child in list(node):
                if _local(child.tag) == "link":
                    link = child.attrib.get("href") or (child.text or "")
                    if link:
                        break
        guid = _child_text(node, "guid") or _child_text(node, "id") or link
        published = (
            _child_text(node, "pubDate")
            or _child_text(node, "published")
            or _child_text(node, "updated")
        )
        if not guid or not (title or body):
            continue
        leads.append(
            {
                "source": "rss",
                "external_id": guid[:500],
                "title": title[:300],
                "body": body[:4000],
                "url": link or feed_url,
                "budget": "",
                "author": feed_url,
                "published_at": published,
            }
        )
    return leads


def fetch_feed(client: httpx.Client, url: str) -> list[dict[str, Any]]:
    response = client.get(url, timeout=30)
    response.raise_for_status()
    return parse_feed(response.text, url)
