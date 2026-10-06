# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import io
from typing import Iterable

SITE_EXPORT = (
    "category_title",
    "city",
    "bad_score",
    "ukraine",
    "domain",
    "url",
    "final_url",
    "phones",
    "emails",
    "contact_url",
    "cms",
    "cms_version",
    "ttfb_ms",
    "https",
    "viewport",
    "php_version",
    "psi_performance",
    "psi_lcp_ms",
    "title",
    "issues",
    "pitch",
    "scanned_at",
    "error",
)

DEMAND_EXPORT = (
    "source",
    "published_at",
    "title",
    "budget",
    "url",
    "author",
    "matched",
    "body",
    "fetched_at",
)


def write_csv(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8-sig"))


def rows_to_csv(rows: Iterable[dict], columns: tuple[str, ...]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return buffer.getvalue()
