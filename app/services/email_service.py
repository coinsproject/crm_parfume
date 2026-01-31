"""
Сервис для отправки email уведомлений
"""
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings
from typing import Optional
import logging

email_logger = logging.getLogger("email")

class EmailService:
    def __init__(self):
        self.smtp_host = getattr(settings, 'SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = getattr(settings, 'SMTP_PORT', 587)
        self.smtp_user = getattr(settings, 'SMTP_USER', '')
        self.smtp_password = getattr(settings, 'SMTP_PASSWORD', '')
        self.from_email = getattr(settings, 'SMTP_FROM_EMAIL', self.smtp_user)
        self.enabled = getattr(settings, 'SMTP_ENABLED', False) and bool(self.smtp_user and self.smtp_password)
    
    async def send_email(self, to_email: str, subject: str, body: str, html_body: Optional[str] = None) -> bool:
        """
        Отправляет email уведомление
        
        Args:
            to_email: Email получателя
            subject: Тема письма
            body: Текст письма (plain text)
            html_body: HTML версия письма (опционально)
        
        Returns:
            True если отправка успешна, False в противном случае
        """
        if not self.enabled:
            email_logger.info(f"Email disabled, would send to {to_email}: {subject}")
            return False
        
        if not to_email:
            email_logger.warning("No email address provided")
            return False
        
        try:
            message = MIMEMultipart("alternative")
            message["From"] = self.from_email
            message["To"] = to_email
            message["Subject"] = subject
            
            text_part = MIMEText(body, "plain", "utf-8")
            message.attach(text_part)
            
            if html_body:
                html_part = MIMEText(html_body, "html", "utf-8")
                message.attach(html_part)
            
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                use_tls=True,
            )
            email_logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True
        except Exception as e:
            email_logger.error(f"Failed to send email to {to_email}: {e}", exc_info=True)
            return False

# Глобальный экземпляр сервиса
email_service = EmailService()

