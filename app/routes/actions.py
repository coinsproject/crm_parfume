from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
from app.services.auth_service import get_current_user_from_cookie
from app.logging_config import actions_logger
import json

router = APIRouter(prefix="/actions", tags=["actions"])


@router.post("/log")
async def log_user_action(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: Session = Depends(get_db)
):
    """
    Логирование действий пользователя
    """
    try:
        data = await request.json()
        action = data.get("action", "")
        element = data.get("element", "")
        page = data.get("page", "")
        additional_info = data.get("additional_info", "")
        
        client_ip = request.client.host if request.client else "unknown"
        
        actions_logger.info(f"User {current_user.username} (ID: {current_user.id}) "
                           f"performed action '{action}' on element '{element}' "
                           f"at page '{page}', IP: {client_ip}, additional info: {additional_info}")
                           
        return JSONResponse(content={"status": "logged"}, status_code=200)
    except Exception as e:
        actions_logger.error(f"Error logging user action: {str(e)}")
        return JSONResponse(content={"status": "error"}, status_code=500)