"""
Конфигурация фильтров для прайса
"""
from typing import List, Dict, Any

# Маппинг ключей фильтров на тексты для поиска в raw_name (нечувствительно к регистру)
FILTER_TEXT_MAP: Dict[str, str] = {
    "hit": "Хит продаж",
    "analog": "Аналог",
    "sets": "Набор",
    "atomizers": "Атомайзер",
    "home": "Для дома",
    "accessories": "Аксессуар",
    "auto": "Автопарфюм",
    "cosmetics": "Косметика",  # Добавляем для всех фильтров
}

# Ключевые слова для определения раздела "Парфюм"
# Позиция считается парфюмом, если содержит хотя бы одно из этих слов
PARFUM_KEYWORDS = [
    "парфюмерн",  # Сокращенная форма для поиска "парфюмерная вода"
    "туалетн",    # Сокращенная форма для поиска "туалетная вода"
    "духи",
    "одеколон",
    "eau de parfum",
    "eau de toilette",
    "parfum",
    "perfume",
    "cologne",
    "extrait",
    "edp",
    "edt",
]

# Исключающие слова (косметика) - имеют приоритет над парфюмом
# Если найдено и парфюм-слово, и косметическое слово → приоритет у Косметики
COSMETICS_EXCLUSION_KEYWORDS = [
    "крем",
    "гель",
    "шампунь",
    "бальзам",
    "маска",
    "сыворотка",
    "скраб",
    "лосьон",
    "мыло",
    "дезодорант",
    "дымка",
    "спрей для тела",
    "масло",
]

# Внутренние фильтры для раздела "Парфюм"
PARFUM_FILTERS: Dict[str, List[str]] = {
    "tester": ["тестер"],
    "sets": ["набор", "set", "gift set"],
    "analog": ["аналог"],
    "decant": ["отливант", "распив"],
    "mini": ["миниатюр"],  # Также проверяется объем <= 10 мл (логика в _apply_parfum_filters)
}

# Разделы прайса
SECTIONS = [
    {"key": "parfum", "label": "Парфюм"},
    {"key": "cosmetics", "label": "Косметика"},
    {"key": "home", "label": "Для дома"},
    {"key": "auto", "label": "Автопарфюм"},
    {"key": "atomizers", "label": "Атомайзеры"},
    {"key": "accessories", "label": "Аксессуары"},
]

PRICE_FILTERS: List[Dict[str, Any]] = [
    {"key": "hit", "label": "Хит продаж"},
    {"key": "analog", "label": "Аналог"},
    {"key": "sets", "label": "Наборы"},
    {"key": "atomizers", "label": "Атомайзеры"},
    {
        "key": "cosmetics",
        "label": "Косметика",
        "children": [
            {"key": "decor", "label": "Декоративная"},
            {"key": "face", "label": "Для лица"},
            {"key": "body", "label": "Для тела"},
            {"key": "hands_feet", "label": "Для рук/ног"},
            {"key": "hair", "label": "Для волос"},
        ]
    },
    {"key": "home", "label": "Для дома"},
    {"key": "accessories", "label": "Аксессуары"},
    {"key": "auto", "label": "Автопарфюм"},
]


