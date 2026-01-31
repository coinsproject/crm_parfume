"""
Сервис для отправки уведомлений через Telegram бота
"""
import httpx
from app.config import settings
from typing import List, Optional
import logging

telegram_logger = logging.getLogger("telegram")

class TelegramService:
    def __init__(self):
        self.bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        admin_chat_ids_str = getattr(settings, 'TELEGRAM_ADMIN_CHAT_IDS', '')
        self.admin_chat_ids = [
            chat_id.strip() 
            for chat_id in admin_chat_ids_str.split(',') 
            if chat_id.strip()
        ] if admin_chat_ids_str else []
        self.enabled = bool(self.bot_token and self.admin_chat_ids)
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
    
    async def send_message(
        self, 
        chat_id: str, 
        message: str, 
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = False
    ) -> bool:
        """
        Отправляет сообщение в Telegram
        
        Args:
            chat_id: ID чата или пользователя
            message: Текст сообщения
            parse_mode: Режим парсинга (HTML или Markdown)
            disable_web_page_preview: Отключить превью ссылок
        
        Returns:
            True если отправка успешна, False в противном случае
        """
        if not self.enabled or not self.api_url:
            telegram_logger.info(f"Telegram disabled, would send to {chat_id}: {message[:50]}...")
            return False
        
        if not chat_id:
            telegram_logger.warning("No chat_id provided")
            return False
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": disable_web_page_preview
                    }
                )
                response.raise_for_status()
                telegram_logger.info(f"Telegram message sent successfully to {chat_id}")
                return True
        except httpx.HTTPStatusError as e:
            telegram_logger.error(f"Telegram API error for chat_id {chat_id}: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            telegram_logger.error(f"Failed to send Telegram message to {chat_id}: {e}", exc_info=True)
            return False
    
    async def notify_admins(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Отправляет сообщение всем администраторам
        
        Args:
            message: Текст сообщения
            parse_mode: Режим парсинга (HTML или Markdown)
        
        Returns:
            True если хотя бы одно сообщение отправлено успешно
        """
        if not self.enabled:
            telegram_logger.info("Telegram disabled, would notify admins")
            return False
        
        if not self.admin_chat_ids:
            telegram_logger.warning("No admin chat IDs configured")
            return False
        
        results = []
        for chat_id in self.admin_chat_ids:
            result = await self.send_message(chat_id, message, parse_mode)
            results.append(result)
        
        success = any(results)
        if success:
            telegram_logger.info(f"Notified {sum(results)}/{len(self.admin_chat_ids)} admins via Telegram")
        
        return success

# Глобальный экземпляр сервиса
telegram_service = TelegramService()

