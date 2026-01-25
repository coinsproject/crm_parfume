"""
Сервис нормализации прайса
Нормализует raw_name в структурированные данные для построения каталога
"""
import re
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
from decimal import Decimal
from sqlalchemy.orm import Session

from app.models import PriceProduct, Brand, BrandAlias
from app.services.key_normalization import normalize_key


def classify_product_type(raw_name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Классифицирует товар по типу и подтипу на основе raw_name
    
    Returns:
        Tuple[product_type, product_subtype] или (None, None) если не удалось определить
    """
    if not raw_name:
        return None, None
    
    name_lower = raw_name.lower()
    
    # Наборы
    if any(word in name_lower for word in ['набор', 'gift set', 'set', 'комплект', 'комплектация']):
        return 'sets', None
    
    # Атомайзеры
    if any(word in name_lower for word in ['атомайзер', 'atomizer', 'sprayer', 'распылитель', 'спрей']):
        return 'atomizers', None
    
    # Автопарфюм
    if any(word in name_lower for word in ['автопарфюм', 'car perfume', 'car', 'авто', 'для авто', 'автомобиль']):
        return 'auto', None
    
    # Косметика - проверяем подтипы
    cosmetics_keywords = {
        'decor': ['помада', 'тушь', 'пудра', 'тон', 'румяна', 'тени', 'консилер', 'бронзер', 'хайлайтер', 'lipstick', 'mascara', 'powder', 'foundation', 'blush', 'eyeshadow'],
        'face': ['для лица', 'face', 'сыворотка', 'крем для лица', 'тонер', 'эссенция', 'сыворотка для лица', 'face cream', 'serum', 'toner'],
        'body': ['для тела', 'body', 'скраб', 'гель для душа', 'лосьон для тела', 'body lotion', 'body cream', 'scrub', 'shower gel'],
        'hands_feet': ['крем для рук', 'hand', 'foot', 'для ног', 'для рук', 'hand cream', 'foot cream'],
        'hair': ['шампунь', 'маска для волос', 'кондиционер', 'hair', 'shampoo', 'hair mask', 'conditioner', 'для волос']
    }
    
    # Проверяем косметику
    cosmetics_general = ['крем', 'лосьон', 'маска', 'сыворотка', 'тон', 'помада', 'пудра', 'шампунь', 
                        'скраб', 'гель', 'бальзам', 'cream', 'lotion', 'mask', 'serum', 'shampoo', 'scrub', 'gel']
    
    if any(word in name_lower for word in cosmetics_general):
        # Определяем подтип
        for subtype, keywords in cosmetics_keywords.items():
            if any(keyword in name_lower for keyword in keywords):
                return 'cosmetics', subtype
        # Если косметика, но подтип не определен
        return 'cosmetics', None
    
    # Парфюм (edp/edt/духи/вода)
    perfume_keywords = ['edp', 'edt', 'edc', 'духи', 'парфюм', 'туалетная вода', 'парфюмерная вода', 
                        'perfume', 'eau de parfum', 'eau de toilette', 'eau de cologne']
    if any(word in name_lower for word in perfume_keywords):
        return 'perfume', None
    
    # Для дома
    home_keywords = ['свеча', 'диффузор', 'ароматизатор', 'candle', 'diffuser', 'для дома', 'home', 'ароматическая свеча']
    if any(word in name_lower for word in home_keywords):
        return 'home', None
    
    # Аксессуары (по умолчанию для остального)
    # Можно добавить более специфичные ключевые слова
    accessories_keywords = ['сумка', 'чехол', 'футляр', 'bag', 'case', 'cover']
    if any(word in name_lower for word in accessories_keywords):
        return 'accessories', None
    
    # Если ничего не подошло, возвращаем None
    return None, None


@dataclass
class NormalizedResult:
    """Результат нормализации строки прайса"""
    brand: Optional[str] = None
    brand_confidence: float = 0.0
    model_name: str = ""
    series: Optional[str] = None
    category_path: List[str] = None
    attrs: Dict[str, Any] = None
    group_key: str = ""
    variant_key: str = ""
    search_text: str = ""
    needs_review: bool = False
    notes: str = ""
    
    def __post_init__(self):
        if self.category_path is None:
            self.category_path = []
        if self.attrs is None:
            self.attrs = {}


class PriceNormalizationService:
    """Сервис для нормализации строк прайса"""
    
    # Словари для распознавания
    FORMAT_KEYWORDS = {
        'отливант': 'decant',
        'тестер': 'tester',
        'пробник': 'sample',
        'sample': 'sample',
        'миниатюра': 'mini',
        'mini': 'mini',
    }
    
    GENDER_KEYWORDS = {
        'мужской': 'M',
        'муж': 'M',
        'male': 'M',
        'женский': 'F',
        'жен': 'F',
        'female': 'F',
        'унисекс': 'U',
        'unisex': 'U',
    }
    
    KIND_KEYWORDS = {
        'духи': 'perfume',
        'edp': 'edp',
        'edt': 'edt',
        'одеколон': 'cologne',
        'парфюмерная вода': 'eau_de_parfum',
        'туалетная вода': 'eau_de_toilette',
    }
    
    COLOR_KEYWORDS = [
        'белый', 'белая', 'белое', 'черный', 'черная', 'черное',
        'красный', 'красная', 'красное', 'синий', 'синяя', 'синее',
        'зеленый', 'зеленая', 'зеленое', 'желтый', 'желтая', 'желтое',
        'коричневый', 'коричневая', 'коричневое', 'розовый', 'розовая', 'розовое',
        'серый', 'серая', 'серое', 'оранжевый', 'оранжевая', 'оранжевое',
    ]
    
    def __init__(self, db: Session):
        self.db = db
        self._brand_cache = None
        self._alias_cache = None
        self._brand_key_cache = None
        self._alias_key_cache = None
    
    def _load_brands_cache(self):
        """Загружает кэш брендов и алиасов"""
        if self._brand_cache is None:
            brands = self.db.query(Brand).all()
            self._brand_cache = {b.name_canonical.upper(): b for b in brands}
            
            aliases = self.db.query(BrandAlias).all()
            self._alias_cache = {}
            for alias in aliases:
                self._alias_cache[alias.alias_upper] = alias.brand_id
    
    def _find_brand(self, text: str) -> Tuple[Optional[str], float]:
        """
        Находит бренд в тексте
        Возвращает (brand_name, confidence)
        """
        self._load_brands_cache()
        
        text_upper = text.upper()
        text_key = normalize_key(text)
        
        # 1. Проверяем алиасы по ключу (exact match) - самый точный
        if text_key and text_key in self._alias_key_cache:
            brand_id = self._alias_key_cache[text_key]
            brand = self.db.query(Brand).filter(Brand.id == brand_id).first()
            if brand:
                return brand.name_canonical, 1.0
        
        # 2. Проверяем бренды по ключу (exact match)
        if text_key and text_key in self._brand_key_cache:
            brand = self._brand_key_cache[text_key]
            return brand.name_canonical, 0.95
        
        # 3. Проверяем алиасы по тексту (substring match)
        for alias, brand_id in self._alias_cache.items():
            if alias in text_upper:
                brand = self.db.query(Brand).filter(Brand.id == brand_id).first()
                if brand:
                    return brand.name_canonical, 0.95
        
        # 4. Проверяем канонические имена брендов (substring match)
        for brand_name, brand_obj in self._brand_cache.items():
            if brand_name in text_upper:
                return brand_obj.name_canonical, 0.9
        
        # 3. Ищем в скобках
        bracket_match = re.search(r'\(([^)]+)\)', text)
        if bracket_match:
            bracket_content = bracket_match.group(1).strip()
            bracket_upper = bracket_content.upper()
            for brand_name, brand_obj in self._brand_cache.items():
                if brand_name in bracket_upper or bracket_upper in brand_name:
                    return brand_obj.name_canonical, 0.85
        
        # 4. Ищем в пути категорий (A > B > C)
        if '>' in text:
            parts = [p.strip() for p in text.split('>')]
            for part in parts:
                part_upper = part.upper()
                for brand_name, brand_obj in self._brand_cache.items():
                    if brand_name in part_upper:
                        return brand_obj.name_canonical, 0.8
        
        # 5. Пытаемся найти бренд через Fragella API (если доступен)
        brand_from_fragella = self._find_brand_via_fragella(text)
        if brand_from_fragella:
            return brand_from_fragella
        
        return None, 0.0
    
    def _find_brand_via_fragella(self, text: str) -> Optional[Tuple[str, float]]:
        """
        Пытается найти бренд через Fragella API
        Возвращает (brand_name, confidence) или None
        """
        try:
            from app.services.fragella_client import FragellaClient
            import asyncio
            import concurrent.futures
            
            client = FragellaClient()
            if not client.enabled or not client.api_key:
                return None
            
            # Извлекаем потенциальное название бренда (первое слово или два)
            words = text.split()
            if len(words) < 1:
                return None
            
            # Пробуем первые 1-3 слова как потенциальный бренд
            for word_count in [1, 2, 3]:
                if word_count > len(words):
                    break
                potential_brand = " ".join(words[:word_count])
                
                try:
                    # Используем синхронный вызов через новый event loop в отдельном потоке
                    def run_async_search():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(
                                client.search_fragrances(potential_brand, limit=3, db=self.db)
                            )
                        finally:
                            new_loop.close()
                    
                    # Запускаем в отдельном потоке с таймаутом
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(run_async_search)
                        try:
                            results = future.result(timeout=5)
                        except concurrent.futures.TimeoutError:
                            continue
                        except Exception:
                            continue
                    
                    if results and len(results) > 0:
                        # Берем первый результат
                        first_result = results[0]
                        found_brand = first_result.get('Brand') or first_result.get('brand')
                        if found_brand:
                            # Сохраняем найденный бренд в каталог для будущего использования
                            self._add_brand_to_catalog(found_brand)
                            return found_brand, 0.85
                except Exception:
                    # Игнорируем ошибки API - это не критично
                    continue
            
            return None
        except Exception:
            # Если Fragella недоступен, просто возвращаем None
            return None
    
    def _add_brand_to_catalog(self, brand_name: str):
        """
        Добавляет бренд в каталог, если его там еще нет
        """
        try:
            brand_name_canonical = brand_name.strip()
            if not brand_name_canonical:
                return
            
            # Проверяем, есть ли уже такой бренд
            existing = self.db.query(Brand).filter(
                Brand.name_canonical.ilike(brand_name_canonical)
            ).first()
            
            if not existing:
                # Создаем новый бренд
                new_brand = Brand(name_canonical=brand_name_canonical)
                self.db.add(new_brand)
                try:
                    self.db.commit()
                    # Обновляем кэш
                    self._brand_cache = None
                    self._alias_cache = None
                    self._load_brands_cache()
                except Exception:
                    self.db.rollback()
        except Exception:
            # Игнорируем ошибки - это не критично
            pass
    
    def _improve_model_via_fragella(self, raw_name: str, brand: str, current_model: str) -> Optional[str]:
        """
        Пытается улучшить название модели через Fragella API
        """
        try:
            from app.services.fragella_client import FragellaClient
            import asyncio
            import concurrent.futures
            
            client = FragellaClient()
            if not client.enabled or not client.api_key:
                return None
            
            # Ищем по бренду и текущей модели
            search_query = f"{brand} {current_model}" if current_model else brand
            
            try:
                def run_async_search():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(
                            client.search_fragrances(search_query, limit=5, db=self.db)
                        )
                    finally:
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(run_async_search)
                    try:
                        results = future.result(timeout=5)
                    except (concurrent.futures.TimeoutError, Exception):
                        return None
                
                if results and len(results) > 0:
                    # Ищем наиболее подходящий результат
                    for result_item in results:
                        result_brand = result_item.get('Brand') or result_item.get('brand', '')
                        result_name = result_item.get('Name') or result_item.get('name', '')
                        
                        # Проверяем, что бренд совпадает
                        if result_brand.upper() == brand.upper() and result_name:
                            # Убираем бренд из названия, если он там есть
                            model_name = result_name
                            if model_name.upper().startswith(brand.upper()):
                                model_name = model_name[len(brand):].strip()
                            
                            # Убираем лишние слова (тип, пол и т.д.)
                            model_name = re.sub(r'\b(мужской|женский|унисекс|парфюмерная вода|туалетная вода|духи|edp|edt)\b', '', model_name, flags=re.IGNORECASE)
                            model_name = re.sub(r'\s+', ' ', model_name).strip()
                            
                            if model_name and len(model_name) > 2:
                                return model_name
            except Exception:
                pass
            
            return None
        except Exception:
            return None
    
    def _extract_format(self, text: str) -> str:
        """Извлекает формат (full/tester/decant/sample/mini)"""
        text_lower = text.lower()
        for keyword, format_type in self.FORMAT_KEYWORDS.items():
            if keyword in text_lower:
                return format_type
        return 'full'
    
    def _extract_gender(self, text: str) -> Optional[str]:
        """Извлекает пол"""
        text_lower = text.lower()
        for keyword, gender in self.GENDER_KEYWORDS.items():
            if keyword in text_lower:
                return gender
        return None
    
    def _extract_volumes(self, text: str) -> Dict[str, Any]:
        """
        Извлекает объёмы
        Возвращает: {volume_ml: int, volumes_ml: [int], total_ml: int}
        """
        result = {}
        
        # Мультиобъём: 50+50+50 мл
        multi_match = re.search(r'(\d+)\+(\d+)(?:\+(\d+))?(?:\+(\d+))?\s*мл', text, re.IGNORECASE)
        if multi_match:
            volumes = [int(v) for v in multi_match.groups() if v]
            result['volumes_ml'] = volumes
            result['total_ml'] = sum(volumes)
            return result
        
        # Обычный объём: 60 мл, 100мл
        volume_match = re.search(r'(\d+(?:[.,]\d+)?)\s*мл', text, re.IGNORECASE)
        if volume_match:
            volume_str = volume_match.group(1).replace(',', '.')
            try:
                volume = int(float(volume_str))
                result['volume_ml'] = volume
            except ValueError:
                pass
        
        return result
    
    def _extract_color(self, text: str) -> Optional[str]:
        """Извлекает цвет"""
        text_lower = text.lower()
        for color in self.COLOR_KEYWORDS:
            if color in text_lower:
                # Нормализуем окончания
                if color.endswith('ая') or color.endswith('ое'):
                    return color[:-2] + 'ый' if color.endswith('ая') else color[:-2] + 'ый'
                return color
        return None
    
    def _extract_size(self, text: str) -> Optional[Dict[str, int]]:
        """Извлекает размер: 20х30 см"""
        size_match = re.search(r'(\d+)\s*[хx]\s*(\d+)\s*см', text, re.IGNORECASE)
        if size_match:
            return {'w': int(size_match.group(1)), 'h': int(size_match.group(2))}
        return None
    
    def _extract_pack(self, text: str) -> Optional[Dict[str, Any]]:
        """Извлекает упаковку: 150 шт/упк"""
        pack_match = re.search(r'(\d+)\s*(шт|упк|шт/упк|шт\.|упк\.)', text, re.IGNORECASE)
        if pack_match:
            return {'qty': int(pack_match.group(1)), 'unit': pack_match.group(2)}
        return None
    
    def _extract_category_path(self, text: str) -> List[str]:
        """Извлекает путь категорий: A > B > C"""
        if '>' in text:
            parts = [p.strip() for p in text.split('>')]
            return [p for p in parts if p]
        return []
    
    def _extract_model_name(self, text: str, brand: Optional[str], category_path: List[str]) -> str:
        """
        Извлекает название модели
        Критично: должно быть стабильным для объединения карточек
        """
        # Удаляем бренд
        work_text = text
        if brand:
            work_text = re.sub(re.escape(brand), '', work_text, flags=re.IGNORECASE)
        
        # Удаляем путь категорий
        if category_path:
            for cat in category_path:
                work_text = re.sub(re.escape(cat), '', work_text, flags=re.IGNORECASE)
            work_text = re.sub(r'>', '', work_text)
        
        # Удаляем формат
        for keyword in self.FORMAT_KEYWORDS.keys():
            work_text = re.sub(rf'\b{re.escape(keyword)}\b', '', work_text, flags=re.IGNORECASE)
        
        # Удаляем пол
        for keyword in self.GENDER_KEYWORDS.keys():
            work_text = re.sub(rf'\b{re.escape(keyword)}\b', '', work_text, flags=re.IGNORECASE)
        
        # Удаляем объёмы
        work_text = re.sub(r'\d+\+?\d*(?:\+\d+)*\s*мл', '', work_text, flags=re.IGNORECASE)
        work_text = re.sub(r'\d+[.,]?\d*\s*мл', '', work_text, flags=re.IGNORECASE)
        
        # Удаляем скобки с содержимым (тестер, отливант и т.д.)
        work_text = re.sub(r'\([^)]*\)', '', work_text)
        
        # Очищаем от лишних пробелов и символов
        work_text = re.sub(r'\s+', ' ', work_text).strip()
        work_text = re.sub(r'^[^\w]+|[^\w]+$', '', work_text)
        
        return work_text
    
    def _generate_group_key(self, brand: Optional[str], model_name: str, series: Optional[str] = None) -> str:
        """Генерирует ключ карточки каталога"""
        def slug(text: str) -> str:
            if not text:
                return ""
            text = text.lower()
            text = re.sub(r'[^\w\s-]', '', text)
            text = re.sub(r'[-\s]+', '-', text)
            return text.strip('-')
        
        parts = []
        if brand:
            parts.append(slug(brand))
        if model_name:
            parts.append(slug(model_name))
        if series:
            parts.append(slug(series))
        
        return "|".join(parts) if parts else ""
    
    def _generate_variant_key(self, group_key: str, attrs: Dict[str, Any]) -> str:
        """Генерирует ключ варианта"""
        if not group_key:
            return ""
        
        parts = [group_key]
        
        # Формат
        format_val = attrs.get('format', 'full')
        parts.append(format_val)
        
        # Объём
        if 'volume_ml' in attrs:
            parts.append(f"{attrs['volume_ml']}ml")
        elif 'total_ml' in attrs:
            parts.append(f"{attrs['total_ml']}ml")
        elif 'volumes_ml' in attrs:
            volumes_str = '+'.join(str(v) for v in attrs['volumes_ml'])
            parts.append(f"{volumes_str}ml")
        
        # Цвет
        if 'color' in attrs and attrs['color']:
            parts.append(attrs['color'])
        
        # Размер
        if 'size_cm' in attrs and attrs['size_cm']:
            size = attrs['size_cm']
            if isinstance(size, dict):
                parts.append(f"{size.get('w', '')}x{size.get('h', '')}cm")
        
        # Упаковка
        if 'pack' in attrs and attrs['pack']:
            pack = attrs['pack']
            if isinstance(pack, dict):
                parts.append(f"{pack.get('qty', '')}{pack.get('unit', '')}")
        
        return "|".join(parts)
    
    def _generate_search_text(self, raw_name: str, brand: Optional[str], model_name: str, 
                             series: Optional[str], attrs: Dict[str, Any]) -> str:
        """Генерирует текст для поиска"""
        parts = [raw_name]
        if brand:
            parts.append(brand)
        if model_name:
            parts.append(model_name)
        if series:
            parts.append(series)
        
        # Добавляем атрибуты
        if 'format' in attrs:
            parts.append(attrs['format'])
        if 'volume_ml' in attrs:
            parts.append(f"{attrs['volume_ml']} мл")
        if 'volumes_ml' in attrs:
            parts.append('+'.join(f"{v} мл" for v in attrs['volumes_ml']))
        if 'color' in attrs and attrs['color']:
            parts.append(attrs['color'])
        if 'features' in attrs:
            parts.extend(attrs['features'])
        
        return " ".join(str(p) for p in parts if p)
    
    def normalize_price_row(self, raw_name: str) -> NormalizedResult:
        """
        Нормализует строку прайса
        """
        if not raw_name or not raw_name.strip():
            return NormalizedResult(
                model_name="",
                needs_review=True,
                notes="Пустая строка"
            )
        
        result = NormalizedResult()
        result.attrs = {}
        
        # Извлекаем категорию
        result.category_path = self._extract_category_path(raw_name)
        
        # Находим бренд
        result.brand, result.brand_confidence = self._find_brand(raw_name)
        
        # Извлекаем формат
        result.attrs['format'] = self._extract_format(raw_name)
        
        # Извлекаем пол
        gender = self._extract_gender(raw_name)
        if gender:
            result.attrs['gender'] = gender
        
        # Извлекаем объёмы
        volumes = self._extract_volumes(raw_name)
        result.attrs.update(volumes)
        
        # Извлекаем цвет
        color = self._extract_color(raw_name)
        if color:
            result.attrs['color'] = color
        
        # Извлекаем размер
        size = self._extract_size(raw_name)
        if size:
            result.attrs['size_cm'] = size
        
        # Извлекаем упаковку
        pack = self._extract_pack(raw_name)
        if pack:
            result.attrs['pack'] = pack
        
        # Извлекаем плотность/вес
        density_match = re.search(r'\((\d+\s*гр?)\)', raw_name)
        if density_match:
            result.attrs['density_raw'] = density_match.group(1)
        
        # Извлекаем features (рулон, кератин и т.д.)
        features = []
        if 'рулон' in raw_name.lower():
            features.append('рулон')
        if 'кератин' in raw_name.lower():
            features.append('кератин')
        if features:
            result.attrs['features'] = features
        
        # Извлекаем название модели
        result.model_name = self._extract_model_name(raw_name, result.brand, result.category_path)
        
        # Если бренд найден, но модель не очень хорошая - пытаемся улучшить через Fragella
        if result.brand and result.brand_confidence >= 0.85:
            improved_model = self._improve_model_via_fragella(raw_name, result.brand, result.model_name)
            if improved_model and len(improved_model) > len(result.model_name):
                result.model_name = improved_model
        
        # Генерируем ключи
        result.group_key = self._generate_group_key(result.brand, result.model_name, result.series)
        result.variant_key = self._generate_variant_key(result.group_key, result.attrs)
        
        # Генерируем search_text
        result.search_text = self._generate_search_text(
            raw_name, result.brand, result.model_name, result.series, result.attrs
        )
        
        # Классифицируем тип товара
        product_type, product_subtype = classify_product_type(raw_name)
        if product_type:
            result.attrs['product_type'] = product_type
        if product_subtype:
            result.attrs['product_subtype'] = product_subtype
        
        # Определяем needs_review
        if not result.brand or result.brand_confidence < 0.85:
            result.needs_review = True
            result.notes += "Бренд не найден или низкая уверенность. "
        
        if not result.model_name or len(result.model_name) < 3:
            result.needs_review = True
            result.notes += "Название модели слишком короткое или пустое. "
        
        # Проверка на конфликты
        if 'tester' in raw_name.lower() and 'отливант' in raw_name.lower():
            result.needs_review = True
            result.notes += "Обнаружены конфликтующие форматы (тестер и отливант). "
        
        if not result.notes:
            result.notes = "Нормализация выполнена успешно"
        
        return result


def normalize_price_row(raw_name: str, db: Session) -> NormalizedResult:
    """
    Удобная функция-обёртка для нормализации
    """
    service = PriceNormalizationService(db)
    return service.normalize_price_row(raw_name)



