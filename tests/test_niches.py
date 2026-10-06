# -*- coding: utf-8 -*-
import unittest

from badscan.niches import keyword_scores, resolve_category
from badscan.search import domain_of_result, parse_ddg_html, unwrap_href


DDG_HTML = """
<html><body>
<a class="result__a" href="https://www.altair-an.kharkov.ua/">АН Альтаїр - Агентство нерухомості Харків</a>
<a class="result__a" href="https://www.olx.ua/uk/list/q-realty/">OLX</a>
<a class="result__a" href="https://lun.ua/realty/kharkiv">LUN</a>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fkub.kh.ua%2Fua%2F&amp;rut=1">КУБ</a>
<form>
  <input type="hidden" name="q" value="будівельні матеріали Харків">
  <input type="hidden" name="s" value="10">
  <input type="hidden" name="vqd" value="abc">
  <input value="Next">
</form>
</body></html>
"""


class SearchParseTests(unittest.TestCase):
    def test_unwraps_ddg_redirect(self) -> None:
        self.assertEqual(
            unwrap_href("//duckduckgo.com/l/?uddg=https%3A%2F%2Fkub.kh.ua%2F&rut=1"),
            "https://kub.kh.ua/",
        )

    def test_keeps_company_sites_and_drops_catalogs(self) -> None:
        rows, nxt = parse_ddg_html(DDG_HTML)
        domains = [domain_of_result(url) for url, _title in rows]
        domains = [domain for domain in domains if domain]
        self.assertEqual(domains, ["altair-an.kharkov.ua", "kub.kh.ua"])
        self.assertEqual(nxt["s"], "10")
        self.assertEqual(nxt["vqd"], "abc")


class CategoryTests(unittest.TestCase):
    def test_realty_and_building_stay_apart(self) -> None:
        realty = "АН Альтаїр. Агентство нерухомості. Продаж квартир у Харкові."
        materials = "Інтернет-магазин будматеріалів. Газоблок, гіпсокартон, цемент, арматура."
        self.assertGreater(keyword_scores(realty)["realty"], 0)
        self.assertEqual(resolve_category("realty", realty), "realty")
        self.assertEqual(resolve_category("building", materials), "building")
        self.assertEqual(resolve_category("realty", materials), "building")

    def test_search_niche_survives_a_weak_mention(self) -> None:
        text = "Агентство нерухомості. Є мебльовані квартири."
        self.assertEqual(resolve_category("realty", text), "realty")


if __name__ == "__main__":
    unittest.main()
