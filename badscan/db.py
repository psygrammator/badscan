# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


SITE_COLUMNS: tuple[str, ...] = (
    "domain",
    "url",
    "final_url",
    "status_code",
    "ttfb_ms",
    "https",
    "tls_error",
    "cms",
    "cms_version",
    "title",
    "snippet",
    "lang",
    "html_bytes",
    "compressed",
    "viewport",
    "jquery",
    "php_version",
    "server",
    "generator",
    "redirect_count",
    "ukraine",
    "bad_score",
    "issues",
    "phones",
    "emails",
    "contact_url",
    "pitch",
    "psi_performance",
    "psi_seo",
    "psi_lcp_ms",
    "crux_lcp_ms",
    "crux_inp_ms",
    "crux_cls",
    "scanned_at",
    "error",
    "category",
    "category_title",
    "city",
)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def close(self) -> None:
        self.conn.close()

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sites (
                domain TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                final_url TEXT,
                status_code INTEGER,
                ttfb_ms INTEGER,
                https INTEGER NOT NULL DEFAULT 0,
                tls_error INTEGER NOT NULL DEFAULT 0,
                cms TEXT,
                cms_version TEXT,
                title TEXT,
                lang TEXT,
                html_bytes INTEGER,
                compressed INTEGER,
                viewport INTEGER,
                jquery TEXT,
                php_version TEXT,
                server TEXT,
                generator TEXT,
                redirect_count INTEGER,
                ukraine INTEGER NOT NULL DEFAULT 0,
                bad_score INTEGER NOT NULL DEFAULT 0,
                issues TEXT,
                phones TEXT,
                emails TEXT,
                contact_url TEXT,
                pitch TEXT,
                psi_performance INTEGER,
                psi_seo INTEGER,
                psi_lcp_ms INTEGER,
                crux_lcp_ms INTEGER,
                crux_inp_ms INTEGER,
                crux_cls REAL,
                scanned_at TEXT NOT NULL,
                error TEXT,
                category TEXT,
                category_title TEXT,
                city TEXT,
                snippet TEXT
            );
            CREATE TABLE IF NOT EXISTS site_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                bad_score INTEGER,
                ttfb_ms INTEGER,
                status_code INTEGER,
                scanned_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS discovered (
                domain TEXT PRIMARY KEY,
                source TEXT,
                sample_url TEXT,
                found_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS demand (
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT,
                body TEXT,
                url TEXT,
                budget TEXT,
                author TEXT,
                published_at TEXT,
                matched TEXT,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (source, external_id)
            );
            """
        )
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(sites)")}
        for name, ddl in (
            ("snippet", "TEXT"),
            ("category", "TEXT"),
            ("category_title", "TEXT"),
            ("city", "TEXT"),
        ):
            if name not in existing:
                self.conn.execute(f"ALTER TABLE sites ADD COLUMN {name} {ddl}")
        self.conn.commit()

    def recently_scanned(self, domain: str, within_days: int) -> bool:
        if within_days <= 0:
            return False
        row = self.conn.execute("SELECT scanned_at FROM sites WHERE domain = ?", (domain,)).fetchone()
        if row is None or not row["scanned_at"]:
            return False
        try:
            scanned = datetime.fromisoformat(row["scanned_at"])
        except ValueError:
            return False
        if scanned.tzinfo is None:
            scanned = scanned.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - scanned < timedelta(days=within_days)

    def upsert_site(self, row: dict[str, Any]) -> None:
        payload = {column: row.get(column) for column in SITE_COLUMNS}
        if not payload.get("category"):
            previous = self.conn.execute(
                "SELECT category, category_title, city FROM sites WHERE domain = ?",
                (payload["domain"],),
            ).fetchone()
            if previous and previous["category"]:
                payload["category"] = previous["category"]
                payload["category_title"] = payload.get("category_title") or previous["category_title"]
                payload["city"] = payload.get("city") or previous["city"]
        columns = ", ".join(SITE_COLUMNS)
        placeholders = ", ".join(f":{column}" for column in SITE_COLUMNS)
        updates = ", ".join(f"{column} = excluded.{column}" for column in SITE_COLUMNS if column != "domain")
        self.conn.execute(
            f"INSERT INTO sites ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(domain) DO UPDATE SET {updates}",
            payload,
        )
        self.conn.execute(
            """
            INSERT INTO site_scans (domain, bad_score, ttfb_ms, status_code, scanned_at)
            VALUES (:domain, :bad_score, :ttfb_ms, :status_code, :scanned_at)
            """,
            payload,
        )
        self.conn.commit()

    def add_discovered(self, domain: str, source: str, sample_url: str) -> None:
        self.conn.execute(
            """
            INSERT INTO discovered (domain, source, sample_url, found_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(domain) DO NOTHING
            """,
            (domain, source, sample_url, utc_now()),
        )
        self.conn.commit()

    def discovered_domains(self) -> list[str]:
        rows = self.conn.execute("SELECT domain FROM discovered ORDER BY found_at DESC").fetchall()
        return [row["domain"] for row in rows]

    def upsert_demand(self, lead: dict[str, Any]) -> bool:
        existing = self.conn.execute(
            "SELECT 1 FROM demand WHERE source = ? AND external_id = ?",
            (lead["source"], lead["external_id"]),
        ).fetchone()
        self.conn.execute(
            """
            INSERT INTO demand (
                source, external_id, title, body, url, budget, author, published_at, matched, fetched_at
            ) VALUES (
                :source, :external_id, :title, :body, :url, :budget, :author, :published_at, :matched, :fetched_at
            )
            ON CONFLICT(source, external_id) DO UPDATE SET
                title = excluded.title,
                body = excluded.body,
                url = excluded.url,
                budget = excluded.budget,
                author = excluded.author,
                published_at = excluded.published_at,
                matched = excluded.matched
            """,
            lead,
        )
        self.conn.commit()
        return existing is None

    def list_sites(self, min_score: int = 0) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM sites
            WHERE bad_score >= ?
            ORDER BY (category IS NOT NULL AND category != '') DESC,
                     category_title,
                     bad_score DESC,
                     ttfb_ms DESC
            """,
            (min_score,),
        ).fetchall()

    def list_categorized(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM sites
            WHERE category IS NOT NULL AND category != ''
            ORDER BY category_title, bad_score DESC, domain
            """
        ).fetchall()

    def get_site(self, domain: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM sites WHERE domain = ?", (domain,)).fetchone()

    def set_category(self, domain: str, category: str, category_title: str, city: str) -> None:
        self.conn.execute(
            """
            UPDATE sites
            SET category = ?, category_title = ?, city = ?
            WHERE domain = ?
            """,
            (category, category_title, city, domain),
        )
        self.conn.commit()

    def list_demand(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM demand ORDER BY COALESCE(published_at, fetched_at) DESC"
        ).fetchall()

    def stats(self) -> dict[str, int]:
        sites = self.conn.execute("SELECT COUNT(*) AS n FROM sites").fetchone()["n"]
        hot = self.conn.execute("SELECT COUNT(*) AS n FROM sites WHERE bad_score >= 50").fetchone()["n"]
        with_phone = self.conn.execute(
            "SELECT COUNT(*) AS n FROM sites WHERE phones IS NOT NULL AND phones != ''"
        ).fetchone()["n"]
        demand = self.conn.execute("SELECT COUNT(*) AS n FROM demand").fetchone()["n"]
        discovered = self.conn.execute("SELECT COUNT(*) AS n FROM discovered").fetchone()["n"]
        return {
            "sites": sites,
            "hot": hot,
            "with_phone": with_phone,
            "demand": demand,
            "discovered": discovered,
        }
