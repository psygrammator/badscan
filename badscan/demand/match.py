# -*- coding: utf-8 -*-
"""Фильтр постов, где человеку нужен сайт, а не работа разработчиком."""

from __future__ import annotations

import re

HASHTAG_RE = re.compile(r"#[^\s#]+")
URL_RE = re.compile(r"https?://\S+")

# Заказ на сборку, редизайн или перенос. Голое слово «сайт» и хештег #дизайн_сайтов не считаются.
INTENT_RE = re.compile(
    r"("
    r"(?:створ\w*|созда\w*|розроб\w*|разработ\w*|зробит\w*|сделат\w*|потріб\w*|нуж\w*|"
    r"замовит\w*|заказат\w*|хочу|ищу|шукаю)\s+(?:\w+\s+){0,5}"
    r"(?:сайт\w*|лендінг\w*|лендинг\w*|л[еэ]нд[иы]г\w*|landing\w*|"
    r"візитк\w*|визитк\w*|інтернет[\s\-]?магазин\w*|интернет[\s\-]?магазин\w*)"
    r"|редизайн\w*\s+(?:сайт\w*|лендінг\w*|лендинг\w*|л[еэ]нд[иы]г\w*|landing\w*)"
    r"|(?:перенес\w*|перенос\w*|міграц\w*|миграц\w*)\s+(?:\w+\s+){0,6}"
    r"(?:сайт\w*|wordpress\w*|вордпрес\w*|modx\w*|bitrix\w*|бітрікс\w*|битрикс\w*|tilda\w*|тильд\w*|opencart\w*)"
    r"|лендінг\w*|лендинг\w*|л[еэ]нд[иы]г\w*|landing\w*"
    r"|сайт\w*\s+(?:під\s+ключ|под\s+ключ|з\s+нуля|с\s+нуля)"
    r"|(?:wordpress|вордпрес\w*|tilda|тильд\w*|horoshop|weblium)\s+(?:сайт\w*|лендінг\w*|лендинг\w*)"
    r")",
    re.IGNORECASE,
)

# Рекламный заказ, где магазин только упомянут. Без «сайт/лендинг/wordpress» это не оффер на разработку.
ADS_RE = re.compile(
    r"(google\s*ads|контекстн\w*\s+реклам|таргет\w*|smm\b|seo[\s\-]?продвиж)",
    re.IGNORECASE,
)
BUILD_RE = re.compile(
    r"(сайт\w*|лендінг\w*|лендинг\w*|landing|wordpress|вордпрес\w*|тильд\w*|tilda|"
    r"редизайн\w*|візитк\w*|визитк\w*|створення|создание|зробити|сделать|"
    r"розробк\w*\s+сайт\w*|разработк\w*\s+сайт\w*|horoshop|weblium|bitrix|бітрікс|битрикс)",
    re.IGNORECASE,
)

SEEKER_RE = re.compile(
    r"(резюме|шукаю роботу|ищу работу|в штат|моя ставка|я\s+разработчик|я\s+розробник|"
    r"готов(ий|ый)\s+взяти\s+проект\s+на\s+себе)",
    re.IGNORECASE,
)

CLIENT_VERB_RE = re.compile(
    r"(потріб\w*|нуж\w*|шукаю\s+виконав|ищу\s+исполн|замовити|заказать|"
    r"бюджет|під ключ|под ключ|зробити|сделать|розробити|разработать)",
    re.IGNORECASE,
)


def cleaned_text(text: str) -> str:
    without_tags = HASHTAG_RE.sub(" ", text or "")
    without_urls = URL_RE.sub(" ", without_tags)
    return re.sub(r"\s+", " ", without_urls).strip()


def matched_terms(text: str, extra_keywords: list[str] | None = None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    plain = cleaned_text(text)
    for match in INTENT_RE.finditer(plain):
        token = re.sub(r"\s+", " ", match.group(0).lower())
        if token not in seen:
            seen.add(token)
            found.append(token)
    for extra in extra_keywords or []:
        needle = extra.strip().lower()
        if not needle:
            continue
        if needle in plain.lower() and needle not in seen:
            seen.add(needle)
            found.append(needle)
    return found


def is_job_seeker(text: str) -> bool:
    if not SEEKER_RE.search(text or ""):
        return False
    return CLIENT_VERB_RE.search(text or "") is None


def accept_lead(text: str, *, source: str, extra_keywords: list[str] | None = None) -> list[str]:
    terms = matched_terms(text, extra_keywords)
    if not terms:
        return []
    if source != "freelancehunt" and is_job_seeker(text):
        return []
    if source != "freelancehunt" and ADS_RE.search(text or "") and not BUILD_RE.search(text or ""):
        return []
    return terms
