"""
Клиент для взаимодействия с Fragella API
"""
import asyncio
import time
from typing import Dict, List, Optional
import httpx
from app.config import settings
from app.models import FragellaUsageLog
from sqlalchemy.orm import Session


class FragellaClient:
    def __init__(self):
        self.base_url = str(settings.FRAGELLA_API_BASE_URL)
        self.api_key = settings.FRAGELLA_API_KEY
        self.enabled = settings.FRAGELLA_ENABLED
        self.max_requests_per_day = settings.FRAGELLA_MAX_REQUESTS_PER_DAY
        self.min_interval_seconds = settings.FRAGELLA_MIN_INTERVAL_SECONDS
        self.timeout_seconds = settings.FRAGELLA_TIMEOUT_SECONDS
        self._last_request_ts = None

    def _check_enabled(self):
        """Проверяет, включен ли клиент"""
        if not self.enabled or not self.api_key:
            raise RuntimeError("Fragella API is disabled or API key not set")

    def _check_rate_limits(self, db: Session) -> bool:
        """Проверяет, не превышен ли лимит запросов за день"""
        from datetime import datetime, timedelta
        
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        request_count = db.query(FragellaUsageLog).filter(
            FragellaUsageLog.created_at >= today_start
        ).count()
        
        return request_count < self.max_requests_per_day

    async def _make_request(self, endpoint: str, params: Optional[Dict] = None, db: Session = None) -> Dict:
        """Выполняет запрос к API с учетом лимитов и безопасности"""
        self._check_enabled()
        
        if db and not self._check_rate_limits(db):
            raise RuntimeError("Daily request limit exceeded")
        
        # Проверяем интервал между запросами
        if self._last_request_ts is not None:
            elapsed = time.time() - self._last_request_ts
            if elapsed < self.min_interval_seconds:
                await asyncio.sleep(self.min_interval_seconds - elapsed)

        headers = {
            "x-api-key": self.api_key,
        }

        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers, params=params)
                self._last_request_ts = time.time()
                
                response.raise_for_status()
                
                # Логируем успешный запрос
                if db:
                    log_entry = FragellaUsageLog(
                        endpoint=endpoint,
                        success=True
                    )
                    db.add(log_entry)
                    db.commit()
                
                json_data = response.json()
                # Проверяем, что это список или словарь с результатами
                if isinstance(json_data, dict) and 'results' in json_data:
                    return json_data['results']
                elif isinstance(json_data, dict) and 'data' in json_data:
                    return json_data['data']
                elif isinstance(json_data, list):
                    return json_data
                else:
                    # Если это словарь, но не список результатов, возвращаем как есть
                    return json_data
        except httpx.HTTPStatusError as e:
            # Логируем ошибку HTTP
            if db:
                log_entry = FragellaUsageLog(
                    endpoint=endpoint,
                    success=False,
                    error_message=f"HTTP {e.response.status_code}: {e.response.text[:500]}"
                )
                db.add(log_entry)
                db.commit()
            raise
        except httpx.RequestError as e:
            # Логируем ошибку запроса
            if db:
                log_entry = FragellaUsageLog(
                    endpoint=endpoint,
                    success=False,
                    error_message=str(e)
                )
                db.add(log_entry)
                db.commit()
            
            raise

    async def search_fragrances(self, query: str, limit: int = 5, db: Session = None) -> List[Dict]:
        """
        Поиск ароматов по названию/бренду
        """
        params = {
            "search": query,
            "limit": limit
        }
        return await self._make_request("fragrances", params=params, db=db)

    async def get_fragrance_by_id(self, fragrance_id: str, db: Session = None) -> Dict:
        """
        Получение информации об аромате по ID
        """
        return await self._make_request(f"fragrances/{fragrance_id}", db=db)

    async def get_similar_fragrances(self, fragrance_name: str, limit: int = 5, db: Session = None) -> List[Dict]:
        """
        Получение похожих ароматов
        """
        params = {
            "name": fragrance_name,
            "limit": limit
        }
        return await self._make_request("fragrances/similar", params=params, db=db)

    async def get_trending_fragrances(self, limit: int = 10, db: Session = None) -> List[Dict]:
        """
        Получение популярных ароматов
        """
        params = {"limit": limit}
        return await self._make_request("fragrances/trending", params=params, db=db)

    async def search_fragrances(self, query: str, limit: int = 5, db: Session = None) -> List[Dict]:
        """
        Поиск ароматов по названию/бренду
        """
        params = {
            "search": query,
            "limit": limit
        }
        return await self._make_request("fragrances", params=params, db=db)

    async def get_fragrance_by_id(self, fragrance_id: str, db: Session = None) -> Dict:
        """
        Получение информации об аромате по ID
        """
        return await self._make_request(f"fragrances/{fragrance_id}", db=db)

    async def get_similar_fragrances(self, fragrance_name: str, limit: int = 5, db: Session = None) -> List[Dict]:
        """
        Получение похожих ароматов
        """
        params = {
            "name": fragrance_name,
            "limit": limit
        }
        return await self._make_request("fragrances/similar", params=params, db=db)

    async def get_trending_fragrances(self, limit: int = 10, db: Session = None) -> List[Dict]:
        """
        Получение популярных ароматов
        """
        params = {"limit": limit}
        return await self._make_request("fragrances/trending", params=params, db=db)