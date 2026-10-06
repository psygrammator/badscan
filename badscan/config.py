# -*- coding: utf-8 -*-
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def config_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    cwd = Path.cwd() / "config.toml"
    if cwd.exists():
        return cwd
    fallback = project_root() / "config.toml"
    if fallback.exists():
        return fallback
    example = project_root() / "config.example.toml"
    return example if example.exists() else cwd


@dataclass
class Settings:
    user_agent: str = "CoreWebLeadResearch/1.0 (+https://coreweb.art; public-page audit)"
    delay_sec: float = 1.2
    timeout_sec: float = 12.0
    workers: int = 3
    db_path: Path = field(default_factory=lambda: Path("data/leads.sqlite"))
    rescan_days: int = 14
    pagespeed_key: str = ""
    pagespeed_strategy: str = "mobile"
    pagespeed_min_local_score: int = 35
    crawl_id: str = "latest"
    zones: list[str] = field(default_factory=list)
    limit_per_zone: int = 25
    fh_token: str = ""
    fh_skill_ids: list[int] = field(default_factory=list)
    fh_pages: int = 3
    tg_channels: list[str] = field(default_factory=list)
    tg_pages: int = 2
    rss_urls: list[str] = field(default_factory=list)
    extra_keywords: list[str] = field(default_factory=list)
    bot_token: str = ""
    bot_chat_id: str = ""
    config_file: Path = field(default_factory=Path)


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def load_settings(path: str | None = None) -> Settings:
    cfg = config_path(path)
    raw: dict = {}
    if cfg.exists():
        raw = tomllib.loads(cfg.read_text(encoding="utf-8"))
    pagespeed = raw.get("pagespeed") or {}
    discover = raw.get("discover") or {}
    demand = raw.get("demand") or {}
    fh = demand.get("freelancehunt") or {}
    tg = demand.get("telegram") or {}
    rss = demand.get("rss") or {}
    notify = raw.get("notify") or {}
    db_raw = str(raw.get("db_path") or "data/leads.sqlite")
    db_path = Path(db_raw)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    return Settings(
        user_agent=str(raw.get("user_agent") or Settings.user_agent),
        delay_sec=float(raw.get("delay_sec") or 1.2),
        timeout_sec=float(raw.get("timeout_sec") or 12),
        workers=max(1, int(raw.get("workers") or 3)),
        db_path=db_path,
        rescan_days=max(0, int(raw.get("rescan_days") or 14)),
        pagespeed_key=str(pagespeed.get("api_key") or "").strip(),
        pagespeed_strategy=str(pagespeed.get("strategy") or "mobile"),
        pagespeed_min_local_score=int(pagespeed.get("min_local_score") or 35),
        crawl_id=str(discover.get("crawl_id") or "latest"),
        zones=_as_str_list(discover.get("zones")),
        limit_per_zone=max(1, int(discover.get("limit_per_zone") or 25)),
        fh_token=str(fh.get("token") or "").strip(),
        fh_skill_ids=_as_int_list(fh.get("skill_ids")),
        fh_pages=max(1, int(fh.get("pages") or 3)),
        tg_channels=[c.lstrip("@") for c in _as_str_list(tg.get("channels"))],
        tg_pages=max(1, int(tg.get("pages") or 1)),
        rss_urls=_as_str_list(rss.get("urls")),
        extra_keywords=_as_str_list(raw.get("extra_keywords")),
        bot_token=str(notify.get("bot_token") or "").strip(),
        bot_chat_id=str(notify.get("chat_id") or "").strip(),
        config_file=cfg,
    )
