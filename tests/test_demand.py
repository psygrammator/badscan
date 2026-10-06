# -*- coding: utf-8 -*-
import unittest

from badscan.demand.freelancehunt import parse_project
from badscan.demand.match import accept_lead
from badscan.demand.rss import parse_feed
from badscan.demand.telegram import parse_telegram_html


class MatchTests(unittest.TestCase):
    def test_client_order_passes_and_resume_does_not(self) -> None:
        order = "Потрібен сайт-візитка для клініки у Харкові, бюджет 15000 грн"
        resume = "Шукаю роботу верстальщика, резюме в лс"
        ads = "Google Ads для інтернет-магазину професійної косметики — запуск та ведення"
        shop = "Потрібен інтернет-магазин одягу, оплата на картку"
        hashtag_noise = "Схема для вишивки бісером\n#дизайн_сайтов #сопровождение_сайтов"
        labels = "Отрисовка в векторе и редизайн серии этикеток"
        self.assertTrue(accept_lead(order, source="telegram"))
        self.assertEqual(accept_lead(resume, source="telegram"), [])
        self.assertEqual(accept_lead(ads, source="telegram"), [])
        self.assertTrue(accept_lead(shop, source="telegram"))
        self.assertEqual(accept_lead(hashtag_noise, source="telegram"), [])
        self.assertEqual(accept_lead(labels, source="telegram"), [])
        self.assertTrue(accept_lead("Створення сайту на Wordpress, адаптив, 3 мови", source="telegram"))
        self.assertTrue(accept_lead("Редизайн сайту освітнього центру", source="telegram"))
        self.assertTrue(accept_lead("Дизайн лэндига для курсу", source="telegram"))
        self.assertTrue(accept_lead("перенесення магазину з MODX", source="telegram"))

    def test_extra_keyword(self) -> None:
        terms = accept_lead("нужен horoshop каталог", source="telegram", extra_keywords=["horoshop"])
        self.assertIn("horoshop", terms)


class FreelancehuntTests(unittest.TestCase):
    def test_jsonapi_project(self) -> None:
        item = {
            "id": "299170",
            "type": "project",
            "attributes": {
                "name": "Сайт клініки під ключ",
                "description": "<p>Потрібен лендінг</p>",
                "budget": {"amount": 25000, "currency": "UAH"},
                "published_at": "2026-10-06T10:00:00+03:00",
                "skills": [{"id": 96, "name": "Створення сайту"}],
            },
            "links": {"html": "https://freelancehunt.com/project/site/299170.html"},
        }
        parsed = parse_project(item)
        assert parsed is not None
        self.assertEqual(parsed["external_id"], "299170")
        self.assertEqual(parsed["budget"], "25000 UAH")
        self.assertNotIn("<p>", parsed["body"])
        self.assertIn("лендінг", parsed["body"])
        terms = accept_lead(parsed["title"] + parsed["body"], source="freelancehunt")
        self.assertTrue(terms)


class TelegramTests(unittest.TestCase):
    def test_public_preview_message(self) -> None:
        html = """
        <div class="tgme_widget_message" data-post="FreelancehuntProjects/10">
          <div class="tgme_widget_message_text">Створення сайту на Wordpress
          10 000 UAH бюджет</div>
          <a class="tgme_widget_message_date" href="https://t.me/FreelancehuntProjects/10">
            <time datetime="2026-10-06T10:00:00+00:00"></time>
          </a>
        </div>
        """
        leads = parse_telegram_html(html, "FreelancehuntProjects")
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["external_id"], "FreelancehuntProjects/10")
        self.assertIn("UAH", leads[0]["budget"])
        self.assertTrue(accept_lead(leads[0]["body"], source="telegram"))


class RssTests(unittest.TestCase):
    def test_rss_item(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel>
          <item>
            <title>Нужен лендинг для школы</title>
            <link>https://example.com/orders/1</link>
            <description>Сделать сайт-визитку</description>
            <guid>order-1</guid>
            <pubDate>Mon, 06 Oct 2026 10:00:00 +0300</pubDate>
          </item>
        </channel></rss>
        """
        leads = parse_feed(xml, "https://example.com/feed")
        self.assertEqual(leads[0]["external_id"], "order-1")
        self.assertTrue(accept_lead(leads[0]["title"] + leads[0]["body"], source="rss"))


if __name__ == "__main__":
    unittest.main()
