# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from badscan.db import Database
from badscan.export import SITE_EXPORT, rows_to_csv, write_csv
from badscan.niches import Niche, niche_by_id, resolve_category
from badscan.report import render_report
from badscan.search import SEARCH_HEADERS, SearchBlocked, domain_of_result, search_ddg


@dataclass
class Lead:
    domain: str
    url: str
    votes: dict[str, int] = field(default_factory=dict)
    cities: set[str] = field(default_factory=set)
    titles: list[str] = field(default_factory=list)

    def category(self) -> str:
        return max(self.votes, key=self.votes.get)

    def search_title(self) -> str:
        return " ".join(self.titles[:4])

    def city_label(self) -> str:
        return ", ".join(sorted(self.cities))


def remember(leads: dict[str, Lead], domain: str, url: str, niche_id: str, city: str, title: str) -> bool:
    fresh = domain not in leads
    lead = leads.get(domain)
    if lead is None:
        lead = Lead(domain=domain, url=url)
        leads[domain] = lead
    lead.votes[niche_id] = lead.votes.get(niche_id, 0) + 1
    if city:
        lead.cities.add(city)
    if title and title not in lead.titles:
        lead.titles.append(title)
    return fresh


def collect_leads(
    niches: list[Niche],
    cities: list[str],
    pages: int,
) -> tuple[dict[str, Lead], str | None]:
    leads: dict[str, Lead] = {}
    blocked: str | None = None
    client = httpx.Client(headers=SEARCH_HEADERS, follow_redirects=True, timeout=30)
    stop = False
    try:
        for niche in niches:
            if stop:
                break
            for city in cities:
                if stop:
                    break
                for phrase in niche.queries:
                    query = f"{phrase} {city}"
                    try:
                        rows = search_ddg(client, query, pages)
                    except SearchBlocked as exc:
                        blocked = str(exc)
                        print(blocked, flush=True)
                        stop = True
                        break
                    except httpx.HTTPError as exc:
                        print(f"поиск «{query}»: {exc}", flush=True)
                        time.sleep(2.5)
                        continue
                    added = 0
                    for url, title in rows:
                        domain = domain_of_result(url)
                        if not domain:
                            continue
                        if remember(leads, domain, url, niche.id, city, title):
                            added += 1
                    print(f"{niche.title} / {city} / {phrase}: +{added}, усього {len(leads)}", flush=True)
                    time.sleep(2.5)
    finally:
        client.close()
    return leads, blocked


def load_seed_leads(path: Path, niches: list[Niche], leads: dict[str, Lead]) -> int:
    allowed = {niche.id for niche in niches}
    if not path.exists():
        return 0
    added = 0
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t")
        if len(parts) < 3:
            continue
        niche_id, city, url = parts[0].strip(), parts[1].strip(), parts[2].strip()
        title = parts[3].strip() if len(parts) > 3 else ""
        if niche_id not in allowed:
            continue
        domain = domain_of_result(url)
        if not domain:
            continue
        if remember(leads, domain, url, niche_id, city, title):
            added += 1
    return added


def text_for(lead: Lead, row: dict | None) -> str:
    parts = [lead.search_title()]
    if row:
        parts.append(str(row.get("title") or ""))
        parts.append(str(row.get("snippet") or ""))
    return " ".join(parts)


def stamp(db: Database, lead: Lead, row: dict | None = None) -> str:
    niche_id = resolve_category(lead.category(), text_for(lead, row))
    niche = niche_by_id(niche_id) or niche_by_id(lead.category())
    if niche is None:
        return lead.category()
    db.set_category(lead.domain, niche.id, niche.title, lead.city_label())
    return niche.id


def attach_meta(row: dict, lead: Lead | None) -> None:
    if lead is None:
        return
    niche_id = resolve_category(lead.category(), text_for(lead, row))
    niche = niche_by_id(niche_id) or niche_by_id(lead.category())
    if niche is None:
        return
    row["category"] = niche.id
    row["category_title"] = niche.title
    row["city"] = lead.city_label()


def write_outputs(db: Database, report_path: Path) -> tuple[int, dict[str, int]]:
    rows = [dict(row) for row in db.list_categorized()]
    counts: dict[str, int] = {}
    for row in rows:
        title = row.get("category_title") or row.get("category") or "?"
        counts[title] = counts.get(title, 0) + 1
    csv_path = Path.cwd() / "data" / "sites.csv"
    write_csv(csv_path, rows_to_csv(rows, SITE_EXPORT))
    from badscan.db import utc_now

    all_sites = [dict(row) for row in db.list_sites(0)]
    demand = [dict(row) for row in db.list_demand()]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(all_sites, demand, utc_now()), encoding="utf-8")
    print(f"csv {csv_path} — {len(rows)} сайтів з нішею", flush=True)
    print(f"звіт {report_path}", flush=True)
    for title, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {count:>4}  {title}", flush=True)
    return len(rows), counts
