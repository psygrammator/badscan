# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from badscan.config import load_settings, project_root
from badscan.db import Database
from badscan.demand.collect import format_digest, lead_row, send_telegram
from badscan.demand.freelancehunt import fetch_projects
from badscan.demand.match import accept_lead
from badscan.demand.rss import fetch_feed
from badscan.demand.telegram import fetch_channel
from badscan.discover import discover_crt, discover_zone, make_discover_client, resolve_crawl_id
from badscan.domains import load_seed_lines
from badscan.export import DEMAND_EXPORT, SITE_EXPORT, rows_to_csv, write_csv
from badscan.hunt import attach_meta, collect_leads, load_seed_leads, stamp, write_outputs
from badscan.niches import DEFAULT_CITIES, NICHES, parse_niche_ids
from badscan.net import RateLimiter
from badscan.probe import probe_domain
from badscan.report import render_report


def _stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _print_row(row: dict) -> None:
    detail = row.get("issues") or row.get("error") or "чисто"
    niche = row.get("category") or "-"
    print(f"{row['bad_score']:>3}  {niche:<14} {row['domain']}  {detail}", flush=True)


def scan_domains(
    settings,
    db: Database,
    domains: list[str],
    *,
    force: bool,
    use_psi: bool,
    meta: dict | None = None,
) -> int:
    domains = [domain for domain in _dedupe(domains) if "." in domain]
    if not force:
        domains = [domain for domain in domains if not db.recently_scanned(domain, settings.rescan_days)]
    if not domains:
        print("нечего сканировать. новый список или --force")
        return 0
    print(f"скан {len(domains)} доменов, пауза {settings.delay_sec} с, потоков {settings.workers}", flush=True)
    limiter = RateLimiter(settings.delay_sec)
    done = 0
    with ThreadPoolExecutor(max_workers=settings.workers) as pool:
        futures = {
            pool.submit(probe_domain, domain, settings, limiter, use_psi=use_psi): domain for domain in domains
        }
        for future in as_completed(futures):
            domain = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001 — один домен не валит пачку
                print(f"FAIL {domain}: {exc}", flush=True)
                continue
            if meta is not None:
                attach_meta(row, meta.get(domain))
            db.upsert_site(row)
            _print_row(row)
            done += 1
    print(f"готово: {done}", flush=True)
    return 0


def collect_demand(settings, db: Database) -> list[dict]:
    fresh: list[dict] = []
    client = httpx.Client(
        headers={"User-Agent": settings.user_agent, "Accept-Language": "uk,ru;q=0.9,en;q=0.5"},
        follow_redirects=True,
        timeout=40,
    )
    try:
        if settings.fh_token:
            try:
                projects = fetch_projects(client, settings.fh_token, settings.fh_skill_ids, settings.fh_pages)
            except PermissionError as exc:
                print(exc, flush=True)
                projects = []
            except httpx.HTTPError as exc:
                print(f"freelancehunt: {exc}", flush=True)
                projects = []
            kept = 0
            for project in projects:
                text = f"{project.get('title', '')}\n{project.get('body', '')}\n{project.get('skills', '')}"
                terms = accept_lead(text, source="freelancehunt", extra_keywords=settings.extra_keywords)
                if not terms:
                    continue
                lead = lead_row(project, terms)
                if db.upsert_demand(lead):
                    fresh.append(lead)
                kept += 1
            print(f"freelancehunt: проектов {len(projects)}, про сайт {kept}", flush=True)
        else:
            print("freelancehunt: нет токена в config.toml, пропуск", flush=True)

        for channel in settings.tg_channels:
            try:
                posts = fetch_channel(client, channel, settings.tg_pages)
            except httpx.HTTPError as exc:
                print(f"telegram @{channel}: {exc}", flush=True)
                continue
            kept = 0
            for post in posts:
                text = f"{post.get('title', '')}\n{post.get('body', '')}"
                terms = accept_lead(text, source="telegram", extra_keywords=settings.extra_keywords)
                if not terms:
                    continue
                lead = lead_row(post, terms)
                if db.upsert_demand(lead):
                    fresh.append(lead)
                kept += 1
            print(f"telegram @{channel}: постов {len(posts)}, про сайт {kept}", flush=True)

        for url in settings.rss_urls:
            try:
                posts = fetch_feed(client, url)
            except httpx.HTTPError as exc:
                print(f"rss {url}: {exc}", flush=True)
                continue
            kept = 0
            for post in posts:
                text = f"{post.get('title', '')}\n{post.get('body', '')}"
                terms = accept_lead(text, source="rss", extra_keywords=settings.extra_keywords)
                if not terms:
                    continue
                lead = lead_row(post, terms)
                if db.upsert_demand(lead):
                    fresh.append(lead)
                kept += 1
            print(f"rss: записей {len(posts)}, про сайт {kept}", flush=True)
    finally:
        client.close()

    if fresh and settings.bot_token and settings.bot_chat_id:
        try:
            send_telegram(settings.bot_token, settings.bot_chat_id, format_digest(fresh), settings.user_agent)
            print(f"в telegram отправлен дайджест: {len(fresh)}", flush=True)
        except httpx.HTTPError as exc:
            print(f"дайджест не ушёл: {exc}", flush=True)
    elif fresh:
        print(f"новых заявок: {len(fresh)}. бот не настроен, смотри report", flush=True)
    else:
        print("новых заявок нет", flush=True)
    return fresh


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="badscan",
        description="Слабые сайты в UA и открытые заявки на разработку. Локальная база, без рассылки.",
    )
    parser.add_argument("--config", help="путь к config.toml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="создать config.toml из примера")

    scan = sub.add_parser("scan", help="снять главные и посчитать bad_score")
    scan.add_argument("--seeds", help="файл, домен или URL на строку")
    scan.add_argument("--domains", help="домены через запятую")
    scan.add_argument("--discovered", action="store_true", help="взять домены из discover")
    scan.add_argument("--force", action="store_true", help="сканить даже если домен свежий")
    scan.add_argument("--no-psi", action="store_true", help="не звать PageSpeed, даже если ключ есть")

    discover = sub.add_parser("discover", help="домены из публичного индекса Common Crawl")
    discover.add_argument("--zones", help="kh.ua,od.ua — вместо списка в конфиге")
    discover.add_argument("--limit", type=int, help="уникальных доменов на зону")
    discover.add_argument(
        "--source",
        choices=("crt", "cc", "both"),
        default="crt",
        help="crt = живые сертификаты crt.sh, cc = Common Crawl, both = оба",
    )
    discover.add_argument("--scan", action="store_true", help="сразу прогнать найденное")
    discover.add_argument("--force", action="store_true")
    discover.add_argument("--no-psi", action="store_true")

    hunt = sub.add_parser("hunt", help="найти компании по нишам и разложить по категориям")
    hunt.add_argument("--niches", default="all", help="realty,building или all")
    hunt.add_argument("--cities", help="Харків,Київ — иначе шесть крупных городов")
    hunt.add_argument("--pages", type=int, default=1, help="страниц выдачи на запрос")
    hunt.add_argument("--force", action="store_true")
    hunt.add_argument("--no-psi", action="store_true")
    hunt.add_argument("--report", default="data/report.html")

    niches_cmd = sub.add_parser("niches", help="список категорий")
    niches_cmd.set_defaults(list_niches=True)

    demand = sub.add_parser("demand", help="собрать заявки «сделайте сайт»")
    demand.add_argument("--loop", type=int, default=0, help="повторять каждые N минут")

    export = sub.add_parser("export", help="CSV для Excel, UTF-8 BOM")
    export.add_argument("--what", choices=("sites", "demand"), required=True)
    export.add_argument("--min-score", type=int, default=0)
    export.add_argument("--out", required=True)

    report = sub.add_parser("report", help="локальный HTML-отчёт")
    report.add_argument("--out", default="data/report.html")
    report.add_argument("--open", action="store_true")

    sub.add_parser("stats", help="сколько уже лежит в базе")
    return parser


def cmd_niches() -> int:
    for niche in NICHES:
        queries = ", ".join(niche.queries)
        print(f"{niche.id:<14} {niche.title} — {queries}")
    return 0


def cmd_hunt(args, settings) -> int:
    niches = parse_niche_ids(args.niches)
    if args.cities:
        cities = [part.strip() for part in args.cities.split(",") if part.strip()]
    else:
        cities = list(DEFAULT_CITIES)
    if not cities:
        print("дай хоча б одне місто")
        return 2
    names = ", ".join(niche.title for niche in niches)
    print(f"ніші: {names}", flush=True)
    print(f"міста: {', '.join(cities)}; сторінок видачі: {args.pages}", flush=True)
    leads, blocked = collect_leads(niches, cities, max(1, args.pages))
    seeded = load_seed_leads(project_root() / "seeds" / "niches.tsv", niches, leads)
    if blocked:
        print(f"локальний список додав {seeded} доменів", flush=True)
    elif seeded:
        print(f"локальний список додав ще {seeded}", flush=True)
    print(f"унікальних доменів: {len(leads)}", flush=True)
    db = Database(settings.db_path)
    try:
        pending = [
            domain
            for domain in leads
            if args.force or not db.recently_scanned(domain, settings.rescan_days)
        ]
        if pending:
            scan_domains(
                settings,
                db,
                pending,
                force=True,
                use_psi=not args.no_psi,
                meta=leads,
            )
        else:
            print("свіжих доменів немає, оновлюю тільки категорії", flush=True)
        for lead in leads.values():
            current = db.get_site(lead.domain)
            if current is None:
                continue
            stamp(db, lead, dict(current))
        report = Path(args.report)
        if not report.is_absolute():
            report = Path.cwd() / report
        write_outputs(db, report)
    finally:
        db.close()
    return 0


def cmd_init() -> int:
    target = Path.cwd() / "config.toml"
    example = project_root() / "config.example.toml"
    if target.exists():
        print(f"уже есть {target}")
        return 0
    shutil.copyfile(example, target)
    print(f"создал {target}")
    return 0


def cmd_scan(args, settings) -> int:
    domains: list[str] = []
    db = Database(settings.db_path)
    try:
        if args.seeds:
            domains.extend(load_seed_lines(Path(args.seeds).read_text(encoding="utf-8-sig")))
        if args.domains:
            domains.extend(load_seed_lines(args.domains.replace(",", "\n")))
        if args.discovered:
            domains.extend(db.discovered_domains())
        if not domains:
            print("дай --seeds, --domains или --discovered")
            return 2
        return scan_domains(settings, db, domains, force=args.force, use_psi=not args.no_psi)
    finally:
        db.close()


def cmd_discover(args, settings) -> int:
    if args.zones:
        zones = [part.strip().lstrip("*.") for part in args.zones.split(",") if part.strip()]
    else:
        zones = list(settings.zones)
    if not zones:
        print("нет зон. --zones kh.ua,od.ua или discover.zones в config.toml")
        return 2
    limit = args.limit or settings.limit_per_zone
    db = Database(settings.db_path)
    client = make_discover_client(settings.user_agent)
    found: list[str] = []
    try:
        crawl_id = ""
        if args.source in {"cc", "both"}:
            try:
                crawl_id = resolve_crawl_id(client, settings.crawl_id)
            except httpx.HTTPError as exc:
                print(f"Common Crawl collinfo: {exc}")
                if args.source == "cc":
                    db.close()
                    return 1
            else:
                print(f"индекс {crawl_id}", flush=True)
        for zone in zones:
            pairs: list[tuple[str, str]] = []
            if args.source in {"crt", "both"}:
                try:
                    pairs.extend(discover_crt(client, zone, limit))
                except (httpx.HTTPError, ValueError) as exc:
                    print(f"crt.sh {zone}: {exc}", flush=True)
            if args.source in {"cc", "both"} and crawl_id:
                try:
                    pairs.extend(discover_zone(client, crawl_id, zone, limit))
                except httpx.HTTPError as exc:
                    print(f"common crawl {zone}: {exc}", flush=True)
            seen_zone: set[str] = set()
            added = 0
            for domain, sample in pairs:
                if domain in seen_zone:
                    continue
                seen_zone.add(domain)
                db.add_discovered(domain, args.source, sample)
                found.append(domain)
                added += 1
            print(f"{zone}: {added} доменов", flush=True)
            time.sleep(max(settings.delay_sec, 2))
    finally:
        client.close()
    print(f"в очереди новых записей этой сессии: {len(found)}", flush=True)
    if args.scan and found:
        try:
            return scan_domains(settings, db, found, force=args.force, use_psi=not args.no_psi)
        finally:
            db.close()
    db.close()
    return 0


def cmd_demand(args, settings) -> int:
    db = Database(settings.db_path)
    try:
        while True:
            try:
                collect_demand(settings, db)
            except KeyboardInterrupt:
                print("стоп")
                return 0
            if not args.loop:
                return 0
            print(f"сон {args.loop} мин", flush=True)
            try:
                time.sleep(args.loop * 60)
            except KeyboardInterrupt:
                print("стоп")
                return 0
    finally:
        db.close()


def cmd_export(args, settings) -> int:
    db = Database(settings.db_path)
    try:
        if args.what == "sites":
            rows = [dict(row) for row in db.list_sites(args.min_score)]
            text = rows_to_csv(rows, SITE_EXPORT)
        else:
            rows = [dict(row) for row in db.list_demand()]
            text = rows_to_csv(rows, DEMAND_EXPORT)
    finally:
        db.close()
    out = Path(args.out)
    write_csv(out, text)
    print(f"{out} — {len(rows)} строк")
    return 0


def cmd_report(args, settings) -> int:
    db = Database(settings.db_path)
    try:
        sites = [dict(row) for row in db.list_sites(0)]
        demand = [dict(row) for row in db.list_demand()]
        from badscan.db import utc_now

        html = render_report(sites, demand, utc_now())
    finally:
        db.close()
    out = Path(args.out)
    if not out.is_absolute():
        out = Path.cwd() / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(out)
    if args.open:
        import os

        os.startfile(out)  # type: ignore[attr-defined]
    return 0


def cmd_stats(settings) -> int:
    db = Database(settings.db_path)
    try:
        stats = db.stats()
    finally:
        db.close()
    print(
        f"сайтов {stats['sites']}, score≥50 {stats['hot']}, с телефоном {stats['with_phone']}, "
        f"в очереди discover {stats['discovered']}, заявок {stats['demand']}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    _stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "init":
        return cmd_init()
    if args.cmd == "niches":
        return cmd_niches()
    if args.cmd == "hunt":
        settings = load_settings(args.config)
        return cmd_hunt(args, settings)
    settings = load_settings(args.config)
    if args.cmd == "scan":
        return cmd_scan(args, settings)
    if args.cmd == "discover":
        return cmd_discover(args, settings)
    if args.cmd == "demand":
        return cmd_demand(args, settings)
    if args.cmd == "export":
        return cmd_export(args, settings)
    if args.cmd == "report":
        return cmd_report(args, settings)
    if args.cmd == "stats":
        return cmd_stats(settings)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
