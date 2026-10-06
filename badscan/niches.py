# -*- coding: utf-8 -*-
"""Ниши, по которым ищем компании, а не случайные домены из сертификатов."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Niche:
    id: str
    title: str
    queries: tuple[str, ...]
    keywords: tuple[str, ...]


NICHES: tuple[Niche, ...] = (
    Niche(
        "realty",
        "Агентства недвижимости",
        ("агентство нерухомості", "агенція нерухомості"),
        (
            "нерухомост",
            "недвижимост",
            "рієлтор",
            "риелтор",
            "ріелтор",
            "агенція нерухомості",
            "агентство нерухомості",
            "агентство недвижимости",
            "продаж квартир",
            "оренда квартир",
            "новобудов",
        ),
    ),
    Niche(
        "building",
        "Стройматериалы",
        ("будівельні матеріали", "будматеріали магазин"),
        (
            "будматеріал",
            "стройматериал",
            "будівельні матеріали",
            "будівельних матеріалів",
            "металобаз",
            "газоблок",
            "піноблок",
            "пеноблок",
            "гіпсокартон",
            "гипсокартон",
            "покрівельн",
            "кровельн",
            "сухі суміш",
            "сухие смеси",
            "лакофарб",
            "утеплювач",
            "утеплител",
            "цемент",
            "арматур",
        ),
    ),
    Niche(
        "construction",
        "Строительные компании",
        ("будівельна компанія", "будівництво будинків"),
        (
            "будівельна компанія",
            "строительная компания",
            "будівельно-монтаж",
            "генпідряд",
            "ремонт квартир",
            "будівництво будин",
            "строительство дом",
        ),
    ),
    Niche(
        "medicine",
        "Медицина и стоматология",
        ("медичний центр", "стоматологія"),
        (
            "стоматолог",
            "медичний центр",
            "медицинский центр",
            "клініка",
            "клиника",
            "діагностич",
            "диагностич",
        ),
    ),
    Niche(
        "auto",
        "Автосалоны и СТО",
        ("автосервіс", "автосалон"),
        (
            "автосервіс",
            "автосервис",
            "автосалон",
            "шиномонтаж",
            "кузовний ремонт",
        ),
    ),
    Niche(
        "law",
        "Юридические компании",
        ("юридична компанія", "адвокатське бюро"),
        (
            "адвокат",
            "юридична компанія",
            "юридические услуги",
            "нотаріус",
            "нотариус",
            "адвокатське",
        ),
    ),
    Niche(
        "hotels",
        "Отели и базы отдыха",
        ("готель", "база відпочинку"),
        (
            "готель",
            "гостиниц",
            "база відпочинку",
            "база отдыха",
            "хостел",
        ),
    ),
    Niche(
        "furniture",
        "Мебель",
        ("магазин меблів", "меблева фабрика"),
        (
            "мебл",
            "мебел",
        ),
    ),
    Niche(
        "beauty",
        "Салоны красоты",
        ("салон краси",),
        (
            "салон краси",
            "салон красоты",
            "барбершоп",
            "косметолог",
            "манікюр",
            "маникюр",
        ),
    ),
    Niche(
        "logistics",
        "Логистика",
        ("транспортна компанія", "вантажні перевезення"),
        (
            "вантажоперевез",
            "грузоперевоз",
            "транспортна компан",
            "транспортная компан",
            "логістичн компан",
            "логистическ компан",
        ),
    ),
    Niche(
        "education",
        "Учебные центры",
        ("навчальний центр",),
        (
            "навчальний центр",
            "учебный центр",
            "курси англ",
            "автошкола",
        ),
    ),
)

DEFAULT_CITIES: tuple[str, ...] = (
    "Харків",
    "Київ",
    "Одеса",
    "Львів",
    "Дніпро",
    "Запоріжжя",
)

_BY_ID = {niche.id: niche for niche in NICHES}


def niche_by_id(niche_id: str) -> Niche | None:
    return _BY_ID.get(niche_id)


def parse_niche_ids(raw: str | None) -> list[Niche]:
    if not raw or raw.strip().lower() == "all":
        return list(NICHES)
    found: list[Niche] = []
    for part in raw.split(","):
        niche = _BY_ID.get(part.strip().lower())
        if niche is None:
            known = ", ".join(item.id for item in NICHES)
            raise SystemExit(f"немає ніші {part.strip()}. є: {known}")
        found.append(niche)
    return found


def keyword_scores(text: str) -> dict[str, int]:
    blob = (text or "").lower()
    scores: dict[str, int] = {}
    for niche in NICHES:
        scores[niche.id] = sum(1 for keyword in niche.keywords if keyword in blob)
    return scores


def resolve_category(search_niche: str, text: str) -> str:
    """Ніша з пошуку лишається, якщо сторінка сама не кричить про іншу."""
    scores = keyword_scores(text)
    if search_niche not in scores:
        return search_niche
    best = max(scores, key=lambda key: scores[key])
    if best != search_niche and scores[best] >= 2 and scores[best] > scores[search_niche]:
        return best
    return search_niche
