"""
Сервис для импорта ароматов из внешних источников (Fragella API)
"""
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models import Fragrance, FragellaUsageLog
from app.services.fragella_client import FragellaClient


class FragranceImportService:
    def __init__(self):
        self.client = FragellaClient()

    def import_fragrance_from_external(self, fragrance_data: Dict, db: Session) -> Fragrance:
        """
        Импорт аромата из внешнего источника во внутреннюю базу
        """
        # Проверяем, не существует ли уже такой аромат в нашей базе
        existing = db.query(Fragrance).filter(
            Fragrance.external_key == fragrance_data.get('id')
        ).first()
        
        if existing:
            # Если существует, обновляем данные
            existing.name = fragrance_data.get('name', existing.name)
            existing.brand = fragrance_data.get('brand', existing.brand)
            existing.year = fragrance_data.get('year', existing.year)
            existing.gender = fragrance_data.get('gender', existing.gender)
            existing.country = fragrance_data.get('country', existing.country)
            existing.oil_type = fragrance_data.get('concentration', existing.oil_type)
            existing.rating = fragrance_data.get('rating', existing.rating)
            existing.price = fragrance_data.get('price', existing.price)
            existing.image_url = fragrance_data.get('image_url', existing.image_url)
            existing.main_accords = fragrance_data.get('accords', existing.main_accords)
            existing.notes = fragrance_data.get('notes', existing.notes)
            existing.longevity = fragrance_data.get('longevity', existing.longevity)
            existing.sillage = fragrance_data.get('sillage', existing.sillage)
            existing.seasons = fragrance_data.get('seasons', existing.seasons)
            existing.occasions = fragrance_data.get('occasions', existing.occasions)
            
            db.commit()
            return existing
        else:
            # Если не существует, создаем новый
            fragrance = Fragrance(
                name=fragrance_data.get('name', ''),
                brand=fragrance_data.get('brand', ''),
                year=fragrance_data.get('year'),
                gender=fragrance_data.get('gender'),
                country=fragrance_data.get('country'),
                oil_type=fragrance_data.get('concentration'),  # тип масла (EDP/EDT/Extrait...)
                rating=fragrance_data.get('rating'),
                price=fragrance_data.get('price'),
                image_url=fragrance_data.get('image_url'),
                main_accords=fragrance_data.get('accords', []),  # основные аккорды
                notes=fragrance_data.get('notes', {}),  # ноты (top/middle/base)
                longevity=fragrance_data.get('longevity'),  # стойкость
                sillage=fragrance_data.get('sillage'),  # шлейф
                seasons=fragrance_data.get('seasons', []),  # рекомендации по сезонам
                occasions=fragrance_data.get('occasions', []),  # рекомендации по случаям
                external_source="fragella",
                external_key=fragrance_data.get('id')  # внешний ID аромата
            )
            
            db.add(fragrance)
            db.commit()
            db.refresh(fragrance)
            
            return fragrance

    async def search_and_import(self, query: str, limit: int = 5, db: Session = None) -> List[Fragrance]:
        """
        Поиск и импорт ароматов по запросу
        """
        # Получаем данные из внешнего API
        external_fragrances = await self.client.search_fragrances(query=query, limit=limit, db=db)
        
        imported_fragrances = []
        for ext_fragrance in external_fragrances:
            imported = self.import_fragrance_from_external(ext_fragrance, db)
            imported_fragrances.append(imported)
        
        return imported_fragrances

    async def get_fragrance_by_id(self, fragrance_id: str, db: Session = None) -> Optional[Fragrance]:
        """
        Получение аромата по ID из внешнего источника
        """
        external_fragrance = await self.client.get_fragrance_by_id(fragrance_id, db=db)
        
        if not external_fragrance:
            return None
        
        return self.import_fragrance_from_external(external_fragrance, db)