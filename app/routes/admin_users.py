from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from app.db import get_db
from app.models import User, Role, Partner, Invitation, BackupCode
from app.services.auth_service import require_roles, get_current_user
from app.services.invitation_service import (
    create_invitation,
    get_valid_invitation_by_token,
    mark_invitation_used,
    create_user_from_invitation
)
from app.services.two_fa_service import generate_totp_secret, generate_backup_codes, hash_backup_code
from app.logging_config import auth_logger


router = APIRouter(prefix="/admin", tags=["admin"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/users", response_class=HTMLResponse)
async def get_users_list(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Page with list of users"""
    users = db.query(User).filter(User.deleted_at.is_(None)).all()
    
    # Load roles for each user
    for user in users:
        user.role = db.query(Role).filter(Role.id == user.role_id).first()
        if user.partner_id:
            user.partner = db.query(Partner).filter(Partner.id == user.partner_id).first()
        else:
            user.partner = None
    
    roles = db.query(Role).all()
    partners = db.query(Partner).all()
    pending_users = [user for user in users if user.pending_activation]
    
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "users": users,
        "pending_users": pending_users,
        "roles": roles,
        "partners": partners,
        "current_user": current_user,
        "active_menu": "settings_users"
    })


@router.get("/invitations", response_class=HTMLResponse)
async def get_invitations_list(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Page with list of invitations"""
    invitations = db.query(Invitation).all()
    
    # Load roles and creators for each invitation
    for invitation in invitations:
        invitation.role = db.query(Role).filter(Role.id == invitation.role_id).first()
        if invitation.partner_id:
            invitation.partner = db.query(Partner).filter(Partner.id == invitation.partner_id).first()
        else:
            invitation.partner = None
        invitation.created_by = db.query(User).filter(User.id == invitation.created_by_user_id).first()
    
    return templates.TemplateResponse("admin_invitations.html", {
        "request": request,
        "invitations": invitations,
        "current_user": current_user,
        "active_menu": "settings_users"
    })


@router.get("/invitations/new", response_class=HTMLResponse)
async def get_create_invitation_form(
    request: Request,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Form for creating invitation"""
    roles = db.query(Role).all()
    partners = db.query(Partner).all()
    
    return templates.TemplateResponse("admin_create_invitation.html", {
        "request": request,
        "roles": roles,
        "partners": partners,
        "current_user": current_user,
        "active_menu": "settings_users"
    })


@router.post("/invitations")
async def create_invitation_endpoint(
    email: str,
    role_id: int,
    partner_id: Optional[int] = None,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Creating invitation"""
    # Check that role exists
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role not found"
        )
    
    # If partner is specified, check existence
    if partner_id:
        partner = db.query(Partner).filter(Partner.id == partner_id).first()
        if not partner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Partner not found"
            )
    
    # Create invitation
    invitation = create_invitation(
        email=email,
        role=role,
        db=db,
        partner_id=partner_id,
        created_by_user=current_user
    )
    
    return {
        "success": True,
        "invitation_id": invitation.id,
        "invitation_token": invitation.token,
        "invitation_link": f"/invite/{invitation.token}"
    }


@router.get("/invite/{token}", response_class=HTMLResponse)
async def get_invite_page(
    request: Request,
    token: str,
    db: Session = Depends(get_db)
):
    """Page for accepting invitation"""
    invitation = get_valid_invitation_by_token(token, db)
    
    if not invitation:
        return templates.TemplateResponse("invite_invalid.html", {
            "request": request,
            "message": "Invitation invalid or expired"
        })
    
    return templates.TemplateResponse("invite_accept.html", {
        "request": request,
        "email": invitation.email
    })


@router.post("/invite/{token}")
async def accept_invitation(
    token: str,
    username: str,
    password: str,
    password_confirm: str,
    display_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Accepting invitation and creating user"""
    invitation = get_valid_invitation_by_token(token, db)
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation invalid or expired"
        )
    
    # Check that passwords match
    if password != password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match"
        )
    
    # Check that username is not taken
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Check that email from invitation is not used by another user
    existing_user_by_email = db.query(User).filter(User.email == invitation.email).first()
    if existing_user_by_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already used by another user"
        )
    
    # Create user from invitation
    user = create_user_from_invitation(
        invitation=invitation,
        username=username,
        email=invitation.email,
        password=password,
        full_name=display_name,
        db=db
    )
    
    # Mark invitation as used
    mark_invitation_used(invitation, db)
    
    return {
        "success": True,
        "message": "Account successfully created",
        "user_id": user.id
    }


@router.get("/users/{user_id}/2fa", response_class=HTMLResponse)
async def get_user_2fa_settings(
    request: Request,
    user_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """View 2FA settings for specific user"""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return templates.TemplateResponse("admin_user_2fa_settings.html", {
        "request": request,
        "current_user": current_user,
        "target_user": target_user
    })


@router.post("/users/{user_id}/2fa/enable")
async def admin_enable_user_2fa(
    request: Request,
    user_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Enable 2FA for another user (by admin)"""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if target_user.is_2fa_enabled:
        auth_logger.warning(f"Admin {current_user.username} attempted to enable 2FA for user {target_user.username} who already has it enabled")
        raise HTTPException(status_code=400, detail="2FA already enabled for this user")
    
    # Generate temporary secret for 2FA setup
    temp_secret = generate_totp_secret()
    target_user.totp_secret_temp = temp_secret  # Store temporary secret
    target_user.is_2fa_enabled = True  # Enable 2FA
    db.commit()
    
    # Generate backup codes
    backup_codes = generate_backup_codes(count=10)
    for plain_code in backup_codes:
        code_hash = hash_backup_code(plain_code)
        backup_code = BackupCode(
            user_id=target_user.id,
            code_hash=code_hash,
            is_used=False
        )
        db.add(backup_code)
    db.commit()
    
    auth_logger.info(f"Admin {current_user.username} enabled 2FA for user {target_user.username}")
    return {"success": True, "message": f"2FA enabled for user {target_user.username}", "backup_codes": backup_codes}


@router.post("/users/{user_id}/activate", response_class=JSONResponse)
async def activate_user_endpoint(
    user_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Activate user by admin"""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not target_user.pending_activation:
        raise HTTPException(status_code=400, detail="User is not awaiting activation")
    
    # Activate user
    target_user.is_active = True
    target_user.pending_activation = False
    db.commit()
    
    auth_logger.info(f"Admin {current_user.username} activated user {target_user.username}")
    return {"success": True, "message": f"User {target_user.username} activated"}


@router.post("/users/{user_id}/reject", response_class=JSONResponse)
async def reject_user_endpoint(
    user_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Reject user (delete account)"""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not target_user.pending_activation:
        raise HTTPException(status_code=400, detail="User is not awaiting activation")
    
    # Delete user
    db.delete(target_user)
    db.commit()
    
    auth_logger.info(f"Admin {current_user.username} rejected user registration for {target_user.username}")
    return {"success": True, "message": f"User registration {target_user.username} rejected"}


@router.post("/users/{user_id}/2fa/disable")
async def admin_disable_user_2fa(
    request: Request,
    user_id: int,
    current_user: User = Depends(require_roles(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Disable 2FA for another user (by admin)"""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not target_user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA already disabled for this user")
    
    # Disable 2FA and remove secret
    target_user.is_2fa_enabled = False
    target_user.totp_secret = None
    # Remove all backup codes for user
    db.query(BackupCode).filter(BackupCode.user_id == target_user.id).delete()
    db.commit()
    
    auth_logger.info(f"Admin {current_user.username} disabled 2FA for user {target_user.username}")
    return {"success": True, "message": f"2FA disabled for user {target_user.username}"}
