from sqlalchemy.orm import Session

from app.models import PriceProduct
from app.services.ai_normalization_service import apply_ai_normalization


def normalize_pending_price_products(db: Session, limit: int = 100):
    pending = (
        db.query(PriceProduct)
        .filter(PriceProduct.ai_status == "pending")
        .order_by(PriceProduct.id.asc())
        .limit(limit)
        .all()
    )
    for pp in pending:
        apply_ai_normalization(db, pp)
    db.commit()
