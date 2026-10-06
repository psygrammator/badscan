# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path

from badscan.db import Database
from badscan.discover import domains_from_crt, parse_cdx_line
from badscan.domains import domain_from_input, load_seed_lines, registrable_domain
from badscan.export import SITE_EXPORT, rows_to_csv, write_csv
from badscan.extract import analyze_html, decode_html
from badscan.report import render_report
from badscan.score import Features, apply_pagespeed, score_features


WP_HTML = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="generator" content="WordPress 4.9.8">
<title>Стоматологія Харків</title>
</head>
<body>
<a href="tel:+380671112233">подзвонити</a>
<a href="mailto:info@clinic.kh.ua">mail</a>
<a href="/kontakty">Контакти</a>
<script src="/wp-includes/js/jquery/jquery-1.12.4.min.js"></script>
<link rel="stylesheet" href="/wp-content/themes/old/style.css">
<p>Запис 400 грн</p>
</body>
</html>
"""


class DomainTests(unittest.TestCase):
    def test_registrable_strips_www_and_city_suffix(self) -> None:
        self.assertEqual(registrable_domain("www.firma.kh.ua"), "firma.kh.ua")
        self.assertEqual(registrable_domain("blog.example.com.ua"), "example.com.ua")
        self.assertEqual(domain_from_input("https://www.firma.kh.ua/catalog?x=1"), "firma.kh.ua")

    def test_seeds_skip_comments(self) -> None:
        domains = load_seed_lines("# comment\n\nhttps://coreweb.art\nwww.firma.od.ua\nwww.firma.od.ua\n")
        self.assertEqual(domains, ["coreweb.art", "firma.od.ua"])


class ScoreTests(unittest.TestCase):
    def test_fast_https_site_is_not_a_lead(self) -> None:
        features = Features(
            domain="coreweb.art",
            requested_url="https://coreweb.art/",
            final_url="https://coreweb.art/",
            status_code=200,
            ttfb_ms=180,
            https=True,
            viewport=True,
            compressed=True,
            html_bytes=40_000,
            title="CoreWeb",
            visible_chars=2000,
            ukraine=40,
        )
        scored = score_features(features)
        self.assertLess(scored.bad_score, 25)
        self.assertEqual(scored.pitch, "")

    def test_old_wordpress_scores_as_lead(self) -> None:
        facts = analyze_html(WP_HTML, "https://clinic.kh.ua/", {"server": "Apache/2.2.22"}, "clinic.kh.ua")
        features = Features(
            domain="clinic.kh.ua",
            requested_url="http://clinic.kh.ua/",
            final_url="http://clinic.kh.ua/",
            status_code=200,
            ttfb_ms=4200,
            https=False,
            compressed=False,
            html_bytes=900_000,
            visible_chars=800,
            viewport=facts["viewport"],
            title=facts["title"],
            lang=facts["lang"],
            cms=facts["cms"],
            cms_version=facts["cms_version"],
            jquery=facts["jquery"],
            server=facts["server"],
            phones=facts["phones"],
            emails=facts["emails"],
            contact_url=facts["contact_url"],
            ukraine=facts["ukraine"],
            parked=facts["parked"],
        )
        scored = score_features(features)
        self.assertEqual(features.cms, "wordpress")
        self.assertEqual(features.cms_version, "4.9.8")
        self.assertEqual(features.phones, ["+380671112233"])
        self.assertEqual(features.emails, ["info@clinic.kh.ua"])
        self.assertTrue(features.contact_url.endswith("/kontakty"))
        self.assertGreaterEqual(features.ukraine, 40)
        self.assertGreaterEqual(scored.bad_score, 70)
        self.assertIn("WordPress", scored.pitch)
        self.assertIn("TTFB", scored.pitch)

    def test_parked_domain_is_not_pitched(self) -> None:
        html = "<html><title>Domain for sale</title><body>buy this domain</body></html>"
        facts = analyze_html(html, "http://park.example/", {}, "park.example")
        features = Features(
            domain="park.example",
            requested_url="http://park.example/",
            final_url="http://park.example/",
            status_code=200,
            https=False,
            ttfb_ms=5000,
            parked=facts["parked"],
            visible_chars=facts["visible_chars"],
        )
        scored = score_features(features)
        self.assertTrue(facts["parked"])
        self.assertEqual(scored.bad_score, 0)
        self.assertEqual(scored.pitch, "")

    def test_broken_server_is_a_lead(self) -> None:
        scored = score_features(
            Features(
                domain="broken.kh.ua",
                requested_url="https://broken.kh.ua/",
                final_url="https://broken.kh.ua/",
                status_code=501,
                https=True,
                viewport=True,
                ttfb_ms=200,
                compressed=True,
                html_bytes=2000,
                visible_chars=20,
                ukraine=45,
            )
        )
        self.assertGreaterEqual(scored.bad_score, 25)
        self.assertIn("HTTP 501", scored.pitch)

    def test_pagespeed_adds_points(self) -> None:
        base = score_features(
            Features(
                domain="slow.ua",
                requested_url="https://slow.ua/",
                final_url="https://slow.ua/",
                status_code=200,
                https=True,
                viewport=False,
                ttfb_ms=200,
                visible_chars=1000,
                html_bytes=10_000,
                compressed=True,
                ukraine=45,
            )
        )
        bumped = apply_pagespeed(base, performance=22, lcp_ms=5100)
        self.assertGreater(bumped.bad_score, base.bad_score)
        self.assertTrue(any("Lighthouse" in item for item in bumped.issues))

    def test_cp1251_title(self) -> None:
        raw = "<html><head><meta charset='windows-1251'><title>Кафе</title></head><body>ок</body></html>".encode(
            "cp1251"
        )
        text = decode_html(raw, "text/html")
        self.assertIn("Кафе", text)


class DiscoverParseTests(unittest.TestCase):
    def test_cdx_keeps_city_business_and_drops_platforms(self) -> None:
        line = json.dumps({"url": "http://www.firma.kh.ua/catalog", "status": "200", "mime": "text/html"})
        self.assertEqual(parse_cdx_line(line), "firma.kh.ua")
        blocked = json.dumps({"url": "https://blog.wordpress.com/hello", "status": "200"})
        self.assertIsNone(parse_cdx_line(blocked))
        school = json.dumps({"url": "https://school.edu.ua/", "status": "200"})
        self.assertIsNone(parse_cdx_line(school))

    def test_crt_records_keep_zone_and_drop_wildcards(self) -> None:
        records = [
            {"name_value": "*.autocentr.kh.ua\nautocentr.kh.ua"},
            {"name_value": "www.firma.kh.ua"},
            {"name_value": "school.edu.ua"},
            {"common_name": "other.com"},
        ]
        self.assertEqual(
            domains_from_crt(records, "kh.ua", 10),
            ["autocentr.kh.ua", "firma.kh.ua"],
        )


class StorageTests(unittest.TestCase):
    def test_site_upsert_and_csv_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "leads.sqlite")
            db.upsert_site(
                {
                    "domain": "firma.kh.ua",
                    "url": "https://firma.kh.ua/",
                    "final_url": "https://firma.kh.ua/",
                    "status_code": 200,
                    "ttfb_ms": 1800,
                    "https": 1,
                    "tls_error": 0,
                    "cms": "wordpress",
                    "cms_version": "4.9",
                    "title": "Фірма",
                    "lang": "uk",
                    "html_bytes": 1000,
                    "compressed": 0,
                    "viewport": 0,
                    "jquery": "1.12",
                    "php_version": "5.6",
                    "server": "Apache/2.2",
                    "generator": "WordPress 4.9",
                    "redirect_count": 0,
                    "ukraine": 80,
                    "bad_score": 77,
                    "issues": "WordPress",
                    "phones": "+380671112233",
                    "emails": "info@firma.kh.ua",
                    "contact_url": "https://firma.kh.ua/kontakty",
                    "pitch": "старый WordPress",
                    "psi_performance": None,
                    "psi_seo": None,
                    "psi_lcp_ms": None,
                    "crux_lcp_ms": None,
                    "crux_inp_ms": None,
                    "crux_cls": None,
                    "scanned_at": "2026-10-06T12:00:00+00:00",
                    "error": None,
                }
            )
            db.upsert_demand(
                {
                    "source": "telegram",
                    "external_id": "fh/1",
                    "title": "Потрібен сайт",
                    "body": "лендинг",
                    "url": "https://t.me/fh/1",
                    "budget": "10000 UAH",
                    "author": "fh",
                    "published_at": "2026-10-06T12:00:00+00:00",
                    "matched": "сайт",
                    "fetched_at": "2026-10-06T12:00:00+00:00",
                }
            )
            again = db.upsert_demand(
                {
                    "source": "telegram",
                    "external_id": "fh/1",
                    "title": "Потрібен сайт",
                    "body": "лендинг оновлено",
                    "url": "https://t.me/fh/1",
                    "budget": "10000 UAH",
                    "author": "fh",
                    "published_at": "2026-10-06T12:00:00+00:00",
                    "matched": "сайт",
                    "fetched_at": "2026-10-06T12:01:00+00:00",
                }
            )
            self.assertFalse(again)
            self.assertEqual(db.stats()["sites"], 1)
            self.assertEqual(db.stats()["demand"], 1)
            sites = [dict(row) for row in db.list_sites(40)]
            self.assertEqual(sites[0]["domain"], "firma.kh.ua")
            html = render_report(sites, [dict(row) for row in db.list_demand()], "2026-10-06")
            self.assertIn("firma.kh.ua", html)
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn("${esc(row.bad_score)}", html)
            self.assertNotIn("${{", html)
            path = Path(tmp) / "sites.csv"
            write_csv(path, rows_to_csv(sites, SITE_EXPORT))
            blob = path.read_bytes()
            self.assertTrue(blob.startswith(b"\xef\xbb\xbf"))
            self.assertIn("Фірма".encode("utf-8"), blob)
            db.close()


if __name__ == "__main__":
    unittest.main()
