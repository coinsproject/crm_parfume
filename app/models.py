from sqlalchemy import Column, Integer, String, Text, Boolean, Numeric, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from app.db import Base
from datetime import datetime
from sqlalchemy import Date


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False) # "ADMIN", "MANAGER", "PARTNER", "VIEWER"
    description = Column(String, nullable=True)
    is_system = Column(Boolean, default=True)  # для базовых ролей

    # Связь с пользователями
    users = relationship("User", back_populates="role")
    permissions = relationship("Permission", secondary="role_permissions", back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    label = Column(String, nullable=False)

    roles = relationship("Role", secondary="role_permissions", back_populates="permissions")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False)

    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    full_name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    role_name = Column(String, nullable=True)  # admin / partner (дублирует связь на Role для простых проверок)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    pending_activation = Column(Boolean, default=False)  # Новое поле для отслеживания ожидания активации
    
    # Поля для 2FA
    is_2fa_enabled = Column(Boolean, default=True)  # 2FA теперь включена по умолчанию для всех
    totp_secret = Column(String, nullable=True)
    totp_secret_temp = Column(String, nullable=True)  # для временного хранения при настройке
    failed_2fa_attempts = Column(Integer, default=0)  # количество неудачных попыток 2FA
    last_2fa_attempt_at = Column(DateTime, nullable=True)  # время последней попытки 2FA
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    # Связи
    role = relationship("Role", back_populates="users")
    partner = relationship(
        "Partner",
        back_populates="users",
        foreign_keys=[partner_id],
        primaryjoin="User.partner_id==Partner.id",
    )
    created_orders = relationship("Order", back_populates="created_by_user")
    owned_clients = relationship(
        "Client",
        back_populates="owner_user",
        foreign_keys="Client.owner_user_id",
    )


class Partner(Base):
    __tablename__ = "partners"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    name = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    type = Column(String, nullable=True)  # "WHOLESALE", "DROPSHIP", "REP"
    contact_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    telegram = Column(String, nullable=True)
    telegram_nick = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    can_access_catalog = Column(Boolean, default=False)
    can_edit_prices = Column(Boolean, default=False)
    admin_markup_percent = Column(Numeric(5, 2), nullable=True)
    max_partner_markup_percent = Column(Numeric(5, 2), nullable=True)
    partner_default_markup_percent = Column(Numeric(5, 2), nullable=True)
    status = Column(String, nullable=False, default="active")  # active / paused / blocked
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    user = relationship("User", foreign_keys=[user_id])
    users = relationship(
        "User",
        back_populates="partner",
        foreign_keys="User.partner_id",
        primaryjoin="Partner.id==User.partner_id",
    )
    orders = relationship("Order", back_populates="partner")
    clients = relationship(
        "Client",
        back_populates="owner_partner",
        foreign_keys="Client.owner_partner_id",
        primaryjoin="Partner.id==Client.owner_partner_id",
    )
    partner_prices = relationship("PartnerPrice", back_populates="partner")
    client_markups = relationship("PartnerClientMarkup", back_populates="partner", cascade="all, delete-orphan")


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    telegram = Column(String, nullable=True)
    instagram = Column(String, nullable=True)
    email = Column(String, nullable=True)
    source = Column(String, nullable=True)  # "telegram_channel", "instagram", "partner"
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner_partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    tags = Column(String, nullable=True)  # через запятую, на будущее можно вынести в отдельную таблицу
    can_access_catalog = Column(Boolean, default=False)
    city = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    owner_user = relationship("User", back_populates="owned_clients", foreign_keys=[owner_user_id])
    owner_partner = relationship(
        "Partner",
        back_populates="clients",
        foreign_keys=[owner_partner_id],
        primaryjoin="Client.owner_partner_id==Partner.id",
    )
    partner = relationship("Partner", foreign_keys=[partner_id])
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    orders = relationship("Order", back_populates="client")


class PartnerClientMarkup(Base):
    __tablename__ = "partner_client_markups"

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    partner_markup_percent = Column(Numeric(5, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    partner = relationship("Partner", back_populates="client_markups")
    client = relationship("Client")

    __table_args__ = (
        UniqueConstraint("partner_id", "client_id", name="uq_partner_client_markup"),
    )


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)
    
    # Статусы: "NEW", "WAITING_PAYMENT", "PAID", "PACKING", "SHIPPED", "DELIVERED", "CANCELLED", "RETURNED"
    status = Column(String, nullable=False, default="NEW")
    total_amount = Column(Numeric(10, 2), nullable=False)
    total_client_amount = Column(Numeric(10, 2), nullable=True)
    total_cost_for_owner = Column(Numeric(10, 2), nullable=True)
    total_margin_for_owner = Column(Numeric(10, 2), nullable=True)
    total_margin_percent = Column(Numeric(5, 2), nullable=True)
    currency = Column(String, default="RUB")
    payment_method = Column(String, nullable=True)  # SBP, карта, нал и т.д.
    
    # Флажки
    is_paid = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)

    # Поля для доставки (упрощённая версия)
    delivery_type = Column(String, nullable=True)  # CDEK, Почта, Курьер, Самовывоз
    delivery_status = Column(String, nullable=True, default="NEW")  # NEW, CREATED, IN_TRANSIT, DELIVERED, RETURNED
    delivery_tracking = Column(String, nullable=True)  # трекинг-номер

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    client = relationship("Client", back_populates="orders")
    created_by_user = relationship("User", back_populates="created_orders")
    partner = relationship("Partner", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    delivery = relationship("Delivery", uselist=False, back_populates="order")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    price_product_id = Column(Integer, ForeignKey("price_products.id"), nullable=True)
    catalog_item_id = Column(Integer, ForeignKey("catalog_items.id"), nullable=True)
    sku_id = Column(Integer, nullable=True)  # используем для хранения fragrance_id
    original_name = Column(Text, nullable=False, default="")
    name = Column(String, nullable=False)  # текст позиции (аромат)
    qty = Column(Integer, default=1, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)  # цена за единицу
    client_price = Column(Numeric(10, 2), nullable=True)
    cost_for_owner = Column(Numeric(10, 2), nullable=True)
    line_client_amount = Column(Numeric(10, 2), nullable=True)
    line_cost_amount = Column(Numeric(10, 2), nullable=True)
    line_margin = Column(Numeric(10, 2), nullable=True)
    line_margin_percent = Column(Numeric(5, 2), nullable=True)
    discount = Column(Numeric(10, 2), nullable=True)

    # Связи
    order = relationship("Order", back_populates="items")
    price_product = relationship("PriceProduct", back_populates="order_items")
    catalog_item = relationship("CatalogItem", back_populates="order_items")

class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    
    # Типы доставки: CDEK, Почта, Курьер, Самовывоз
    delivery_type = Column(String, nullable=False)
    address = Column(String, nullable=True)
    pickup_point = Column(String, nullable=True)
    tracking_number = Column(String, nullable=True)
    
    # Статусы: "CREATED", "IN_TRANSIT", "AT_PICKUP_POINT", "DELIVERED", "RETURNED"
    status = Column(String, nullable=False, default="CREATED")
    cost = Column(Numeric(10, 2), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    order = relationship("Order", back_populates="delivery")

# Модель для резервных кодов
class BackupCode(Base):
    __tablename__ = "backup_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code_hash = Column(String, nullable=False)  # хэш кода, а не сам код
    is_used = Column(Boolean, default=False)  # использован ли код
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связь с пользователем
    user = relationship("User", backref="backup_codes")

# Модель для приглашений
class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)

    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=func.now())

    # Связи
    role = relationship("Role")
    partner = relationship("Partner")

# Модель для ароматов
class Fragrance(Base):
    __tablename__ = "fragrances"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)  # Name
    brand = Column(String, index=True, nullable=False)  # Brand
    year = Column(Integer, nullable=True)  # Year
    gender = Column(String, nullable=True)  # Gender ("Male", "Female", "Unisex"...)
    country = Column(String, nullable=True)  # Country
    oil_type = Column(String, nullable=True)  # OilType (EDP/EDT/Extrait...)
    
    rating = Column(Numeric(3, 2), nullable=True)  # rating (0.00-5.00)
    price = Column(Numeric(10, 2), nullable=True)  # ориентир, можно хранить как float
    base_cost = Column(Numeric(10, 2), nullable=True)
    base_retail_price = Column(Numeric(10, 2), nullable=True)
    
    image_url = Column(String, nullable=True)  # основной Image URL (можно сразу webp)
    
    main_accords = Column(JSON, nullable=True)  # [{ "name": "sweet", "percentage": 90 }, ...]
    notes = Column(JSON, nullable=True)  # { "top": [...], "middle": [...], "base": [...] }
    
    longevity = Column(String, nullable=True)  # "Moderate", "Long Lasting"...
    sillage = Column(String, nullable=True)  # "Soft", "Moderate", "Strong"...
    
    seasons = Column(JSON, nullable=True)  # SeasonRanking: [{ "season": "Winter", "score": 0.85 }, ...]
    occasions = Column(JSON, nullable=True)  # OccasionRanking
    
    external_source = Column(String, default="fragella")  # пока всегда "fragella"
    external_key = Column(String, nullable=True)  # например, Name+Brand или их internal ID, если есть

    partner_prices = relationship("PartnerPrice", back_populates="fragrance")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)


class PartnerPrice(Base):
    __tablename__ = "partner_prices"

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    fragrance_id = Column(Integer, ForeignKey("fragrances.id"), nullable=False)
    purchase_price_for_partner = Column(Numeric(10, 2), nullable=True)
    recommended_client_price = Column(Numeric(10, 2), nullable=True)

    partner = relationship("Partner", back_populates="partner_prices")
    fragrance = relationship("Fragrance", back_populates="partner_prices")

    __table_args__ = (UniqueConstraint("partner_id", "fragrance_id", name="uq_partner_fragrance_price"),)


# Модель для логирования использования Fragella API
class FragellaUsageLog(Base):
    __tablename__ = "fragella_usage_log"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    endpoint = Column(String, nullable=False)
    success = Column(Boolean, default=True)
    error_message = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Связь с пользователем
    user = relationship("User")


class PriceProduct(Base):
    __tablename__ = "price_products"

    id = Column(Integer, primary_key=True, index=True)
    external_article = Column(String, unique=True, nullable=False)
    raw_name = Column(Text, nullable=True)
    brand = Column(String, nullable=True)
    product_name = Column(String, nullable=True)
    category = Column(String, nullable=True)
    volume_value = Column(Numeric(10, 2), nullable=True)
    volume_unit = Column(String, nullable=True)
    gender = Column(String, nullable=True)  # F/M/U/null
    is_active = Column(Boolean, default=True)
    price_1 = Column(Numeric(10, 2), nullable=True)  # закупочная цена
    price_2 = Column(Numeric(10, 2), nullable=True)  # округленная цена для партнера
    round_delta = Column(Numeric(10, 2), nullable=True)  # разница округления
    is_in_stock = Column(Boolean, default=True)  # есть ли товар в наличии
    is_in_current_pricelist = Column(Boolean, default=True)  # участвует ли в последней загрузке
    last_price_change_at = Column(DateTime, nullable=True)
    ai_brand = Column(String, nullable=True)  # бренд по версии ИИ
    ai_base_name = Column(String, nullable=True)  # нормализованное имя модели без объёма
    ai_line = Column(String, nullable=True)  # линейка/серия
    ai_kind = Column(String, nullable=True)  # тип продукта
    ai_group_key = Column(String, nullable=True, index=True)  # ключ объединения в одну карточку
    ai_status = Column(String, nullable=False, default="pending")  # pending|ok|failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    price_history = relationship("PriceHistory", back_populates="price_product", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="price_product")
    catalog_item = relationship("CatalogItem", back_populates="price_product", uselist=False)
    variants = relationship("CatalogVariant", back_populates="price_product")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    price_product_id = Column(Integer, ForeignKey("price_products.id"), nullable=False)
    price_upload_id = Column(Integer, ForeignKey("price_uploads.id"), nullable=True)
    price = Column(Numeric(10, 2), nullable=True)  # совместимость: хранит price_2
    old_price_1 = Column(Numeric(10, 2), nullable=True)
    new_price_1 = Column(Numeric(10, 2), nullable=True)
    old_price_2 = Column(Numeric(10, 2), nullable=True)
    new_price_2 = Column(Numeric(10, 2), nullable=True)
    old_round_delta = Column(Numeric(10, 2), nullable=True)
    new_round_delta = Column(Numeric(10, 2), nullable=True)
    currency = Column(String, default="RUB")
    source_date = Column(Date, nullable=True)
    source_filename = Column(String, nullable=True)
    change_type = Column(String, nullable=True)  # NEW, UP, DOWN, UNCHANGED, REMOVED
    created_at = Column(DateTime, default=datetime.utcnow)
    changed_at = Column(DateTime, default=datetime.utcnow)

    price_product = relationship("PriceProduct", back_populates="price_history")
    price_upload = relationship("PriceUpload", back_populates="items")


class PriceUpload(Base):
    __tablename__ = "price_uploads"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=True)
    source_date = Column(Date, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, nullable=False, default="in_progress")  # in_progress, done, failed
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    total_count = Column(Integer, default=0)  # legacy
    total_rows = Column(Integer, default=0)
    new_count = Column(Integer, default=0)  # legacy
    added_count = Column(Integer, default=0)
    up_count = Column(Integer, default=0)  # legacy: повышения
    down_count = Column(Integer, default=0)  # legacy: понижения
    updated_price_count = Column(Integer, default=0)
    removed_count = Column(Integer, default=0)  # legacy
    marked_out_of_stock_count = Column(Integer, default=0)
    unchanged_count = Column(Integer, default=0)

    items = relationship("PriceHistory", back_populates="price_upload")
    created_by = relationship("User")


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id = Column(Integer, primary_key=True, index=True)
    price_product_id = Column(Integer, ForeignKey("price_products.id"), nullable=True)  # legacy
    article = Column(String, nullable=True)
    brand = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    type = Column(String, nullable=True)
    volume = Column(String, nullable=True)  # legacy
    gender = Column(String, nullable=True)
    description_short = Column(Text, nullable=True)
    description_full = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    tags = Column(JSON, nullable=True)
    visible = Column(Boolean, default=False, nullable=False)
    in_stock = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    price_product = relationship("PriceProduct", back_populates="catalog_item")  # legacy
    variants = relationship("CatalogVariant", back_populates="catalog_item", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="catalog_item")

    __table_args__ = (
        UniqueConstraint("brand", "name", name="uq_catalog_item_brand_name"),
    )


class CatalogVariant(Base):
    __tablename__ = "catalog_variants"

    id = Column(Integer, primary_key=True, index=True)
    catalog_item_id = Column(Integer, ForeignKey("catalog_items.id"), nullable=False)
    price_product_id = Column(Integer, ForeignKey("price_products.id"), nullable=False)
    volume_value = Column(Numeric(10, 2), nullable=True)
    volume_unit = Column(String, nullable=True)
    is_tester = Column(Boolean, default=False, nullable=False)
    gender = Column(String, nullable=True)
    kind = Column(String, nullable=True)
    in_stock = Column(Boolean, default=False, nullable=False)
    request_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    catalog_item = relationship("CatalogItem", back_populates="variants")
    price_product = relationship("PriceProduct", back_populates="variants")

    __table_args__ = (
        UniqueConstraint("price_product_id", name="uq_catalog_variant_price_product"),
    )
