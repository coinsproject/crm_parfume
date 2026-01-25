"""
Сервис для извлечения кандидатов брендов из прайса
"""
import re
from typing import List, Dict, Tuple, Optional
from collections import Counter
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import PriceProduct, Brand, BrandAlias
from app.services.key_normalization import normalize_key


# Стоп-слова для определения конца названия бренда
STOP_WORDS = {
    'унисекс', 'женск', 'женский', 'мужск', 'мужской',
    'парф', 'парфюмерная', 'туалет', 'туалетная', 'вода',
    'мл', 'ml', 'г', 'гр', 'g', 'gr',
    'тестер', '(тестер)', 'отливант', 'пробник', 'sample',
    'духи', 'edp', 'edt', 'eau', 'de', 'parfum', 'toilette',
    'миниатюра', 'mini', 'decant'
}


def extract_brand_candidate(raw_name: str) -> Optional[str]:
    """
    Извлекает кандидата бренда из raw_name
    
    Алгоритм:
    1. Если есть > → всё до первого > (и трим)
    2. Иначе взять первые 1–4 слова до стоп-слов
    """
    try:
        if not raw_name or not isinstance(raw_name, str):
            return None
        
        raw_name = raw_name.strip()
        if not raw_name:
            return None
        
        # 1. Если есть > → всё до первого >
        if '>' in raw_name:
            parts = raw_name.split('>', 1)
            candidate = parts[0].strip()
            if candidate:
                # Очищаем от лишних символов
                candidate = re.sub(r'^[^\w&\-\.]+|[^\w&\-\.]+$', '', candidate)
                if candidate and len(candidate) >= 2:
                    return candidate
        
        # 2. Иначе взять первые 1–4 слова до стоп-слов
        words = raw_name.split()
        if not words:
            return None
        
        # Ищем позицию первого стоп-слова
        stop_pos = None
        for i, word in enumerate(words):
            word_lower = word.lower().strip('.,;:()[]{}')
            if word_lower in STOP_WORDS:
                stop_pos = i
                break
        
        # Берем от 1 до 4 слов до стоп-слова (или все слова, если стоп-слов нет)
        if stop_pos is not None:
            max_words = min(4, stop_pos)
        else:
            max_words = min(4, len(words))
        
        if max_words == 0:
            return None
        
        candidate_words = words[:max_words]
        candidate = ' '.join(candidate_words).strip()
        
        # Очищаем от лишних символов в начале/конце (но сохраняем & и другие допустимые символы)
        candidate = re.sub(r'^[^\w&\-\.]+|[^\w&\-\.]+$', '', candidate)
        
        if not candidate or len(candidate) < 2:
            return None
        
        return candidate
    except Exception:
        # В случае любой ошибки возвращаем None
        return None


def get_brand_candidates(db: Session, limit: int = 500) -> List[Dict]:
    """
    Извлекает кандидатов брендов из PriceProduct.raw_name,
    группирует по кандидату, считает частоты
    
    Возвращает список словарей:
    {
        'candidate': str,
        'count': int,
        'example_raw_name': str,
        'exists_as_brand': bool,
        'exists_as_alias': bool
    }
    """
    # Получаем все активные продукты (или все, если активных мало)
    # Используем более широкий фильтр для получения большего количества кандидатов
    products = db.query(PriceProduct).filter(
        PriceProduct.raw_name.isnot(None),
        PriceProduct.raw_name != ''
    ).limit(100000).all()  # Ограничиваем для производительности
    
    # Извлекаем кандидатов
    candidates = []
    candidate_to_examples = {}
    
    for product in products:
        if not product.raw_name:
            continue
        try:
            candidate = extract_brand_candidate(product.raw_name)
            if candidate:
                candidates.append(candidate)
                # Сохраняем пример raw_name для каждого кандидата
                if candidate not in candidate_to_examples:
                    candidate_to_examples[candidate] = product.raw_name or ''
        except Exception as e:
            # Пропускаем товары с ошибками извлечения
            continue
    
    # Считаем частоты
    candidate_counts = Counter(candidates)
    
    # Загружаем существующие бренды и алиасы для проверки
    existing_brands = {b.name_canonical.upper(): b for b in db.query(Brand).all()}
    existing_aliases = {a.alias_upper: a for a in db.query(BrandAlias).all()}
    
    # Формируем результат
    result = []
    for candidate, count in candidate_counts.most_common(limit):
        candidate_upper = candidate.upper()
        exists_as_brand = candidate_upper in existing_brands
        exists_as_alias = candidate_upper in existing_aliases
        
        result.append({
            'candidate': candidate or '',
            'count': count,
            'example_raw_name': candidate_to_examples.get(candidate, '') or '',
            'exists_as_brand': exists_as_brand,
            'exists_as_alias': exists_as_alias,
        })
    
    return result


def create_brand_from_candidate(db: Session, candidate: str) -> Tuple[Brand, BrandAlias]:
    """
    Создает бренд и алиас из кандидата
    """
    candidate_clean = candidate.strip()
    candidate_upper = candidate_clean.upper()
    
    # Проверяем, не существует ли уже
    existing_brand = db.query(Brand).filter(Brand.name_canonical.ilike(candidate_clean)).first()
    if existing_brand:
        raise ValueError(f"Бренд '{candidate_clean}' уже существует")
    
    existing_alias = db.query(BrandAlias).filter(BrandAlias.alias_upper == candidate_upper).first()
    if existing_alias:
        raise ValueError(f"Алиас '{candidate_upper}' уже существует")
    
    # Создаем бренд
    brand_key = normalize_key(candidate_clean) or ""
    brand = Brand(name_canonical=candidate_clean, key=brand_key)
    db.add(brand)
    db.flush()
    
    # Создаем алиас
    alias_key = normalize_key(candidate) or ""
    alias = BrandAlias(brand_id=brand.id, alias_upper=candidate_upper, alias_key=alias_key)
    db.add(alias)
    db.commit()
    db.refresh(brand)
    
    return brand, alias


def map_candidate_to_brand(db: Session, candidate: str, brand_id: int) -> BrandAlias:
    """
    Привязывает кандидата к существующему бренду (создает алиас)
    """
    candidate_upper = candidate.strip().upper()
    
    # Проверяем, что бренд существует
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise ValueError(f"Бренд с ID {brand_id} не найден")
    
    # Проверяем, не существует ли уже такой алиас
    existing_alias = db.query(BrandAlias).filter(BrandAlias.alias_upper == candidate_upper).first()
    if existing_alias:
        if existing_alias.brand_id == brand_id:
            return existing_alias  # Уже привязан к этому бренду
        else:
            raise ValueError(f"Алиас '{candidate_upper}' уже привязан к другому бренду")
    
    # Создаем алиас
    alias_key = normalize_key(candidate) or ""
    alias = BrandAlias(brand_id=brand_id, alias_upper=candidate_upper, alias_key=alias_key)
    db.add(alias)
    db.commit()
    db.refresh(alias)
    
    return alias

