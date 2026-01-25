"""
Сервис для нормализации ключей брендов и алиасов
"""
import re
from typing import Optional


def normalize_key(text: str) -> Optional[str]:
    """
    Нормализует текст для создания устойчивого ключа поиска.
    Убирает различия в &/and, дефисах, точках, двойных пробелах и т.д.
    
    Примеры:
    - "Abercrombie & Fitch" → "abercrombieandfitch"
    - "Abercrombie and Fitch" → "abercrombieandfitch"
    - "Tom-Ford" → "tomford"
    - "Tom  Ford" → "tomford"
    """
    if not text or not text.strip():
        return None
    
    # Приводим к нижнему регистру
    key = text.lower().strip()
    
    # Заменяем & на and
    key = re.sub(r'\s*&\s*', 'and', key)
    
    # Заменяем дефисы и подчеркивания на пробелы
    key = re.sub(r'[-_]', ' ', key)
    
    # Убираем точки, запятые и другие знаки препинания
    key = re.sub(r'[.,;:!?()\[\]{}"\']', '', key)
    
    # Нормализуем пробелы (множественные → один)
    key = re.sub(r'\s+', ' ', key)
    
    # Убираем пробелы в начале и конце
    key = key.strip()
    
    # Убираем все пробелы (делаем один токен)
    key = key.replace(' ', '')
    
    if not key:
        return None
    
    return key



