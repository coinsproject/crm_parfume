from sqlalchemy import Column, Integer, String, Text, Boolean, Numeric, DateTime, ForeignKey, func, UniqueConstraint, Table, Date
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
import sqlalchemy as sa
from app.db import Base
from datetime import datetime, date


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
    partner_price_markup_percent = Column(Numeric(5, 2), nullable=True)
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
    
    # Статусы: "NEW", "PENDING_CLIENT_APPROVAL", "WAITING_PAYMENT", "PAID", "PACKING", "SHIPPED", "DELIVERED", "CANCELLED", "RETURNED"
    status = Column(String, nullable=False, default="NEW")
    total_amount = Column(Numeric(10, 2), nullable=False)
    total_client_amount = Column(Numeric(10, 2), nullable=True)
    total_cost_for_owner = Column(Numeric(10, 2), nullable=True)
    total_margin_for_owner = Column(Numeric(10, 2), nullable=True)
    total_margin_percent = Column(Numeric(5, 2), nullable=True)
    total_admin_margin = Column(Numeric(10, 2), nullable=True)  # Общая маржа админа
    total_partner_margin = Column(Numeric(10, 2), nullable=True)  # Общая маржа партнера
    total_admin_margin_percent = Column(Numeric(5, 2), nullable=True)  # Процент маржи админа (от себестоимости price_1)
    total_partner_margin_percent = Column(Numeric(5, 2), nullable=True)  # Процент маржи партнера (от себестоимости price_2)
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
    purchase_requests = relationship("PurchaseRequest", secondary="purchase_request_orders", back_populates="orders")

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
    line_admin_margin = Column(Numeric(10, 2), nullable=True)  # Маржа админа по строке
    line_partner_margin = Column(Numeric(10, 2), nullable=True)  # Маржа партнера по строке
    line_admin_margin_percent = Column(Numeric(5, 2), nullable=True)  # Процент маржи админа по строке (от price_1)
    line_partner_margin_percent = Column(Numeric(5, 2), nullable=True)  # Процент маржи партнера по строке (от price_2)
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
    
    # Поля для данных партнера (заполняются при создании приглашения)
    partner_full_name = Column(String, nullable=True)
    partner_phone = Column(String, nullable=True)
    partner_telegram = Column(String, nullable=True)

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
    brand = Column(String, nullable=True)  # legacy, используем norm_brand
    product_name = Column(String, nullable=True)  # legacy
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
    
    # Поля нормализации (новые)
    norm_brand = Column(String, nullable=True, index=True)  # нормализованный бренд
    brand_confidence = Column(Numeric(3, 2), nullable=True)  # уверенность в бренде 0..1
    model_name = Column(String, nullable=True)  # название модели/товара
    series = Column(String, nullable=True)  # серия/линейка
    category_path_json = Column(Text, nullable=True)  # JSON: список категорий из пути "A > B > C"
    attrs_json = Column(Text, nullable=True)  # JSON: атрибуты варианта (format, volume, color, size, pack, features)
    variant_key = Column(String, nullable=True, index=True)  # ключ варианта
    search_text = Column(Text, nullable=True)  # текст для поиска
    normalization_notes = Column(Text, nullable=True)  # заметки о нормализации
    
    # Legacy AI поля (сохраняем для совместимости)
    ai_brand = Column(String, nullable=True)  # бренд по версии ИИ
    ai_base_name = Column(String, nullable=True)  # нормализованное имя модели без объёма
    ai_line = Column(String, nullable=True)  # линейка/серия
    ai_kind = Column(String, nullable=True)  # тип продукта
    ai_group_key = Column(String, nullable=True, index=True)  # ключ объединения в одну карточку
    ai_status = Column(String, nullable=False, default="pending")  # pending|ok|review|error
    
    # Поля для фильтрации по типу товара
    product_type = Column(String(32), nullable=True, index=True)  # perfume, sets, atomizers, cosmetics, home, accessories, auto, analog, hit
    product_subtype = Column(String(32), nullable=True, index=True)  # для cosmetics: decor, face, body, hands_feet, hair
    
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
    status = Column(String, nullable=False, default="in_progress")  # in_progress, done, failed, cancelled
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    total_count = Column(Integer, default=0)  # legacy
    total_rows = Column(Integer, default=0)
    processed_rows = Column(Integer, default=0)  # Количество обработанных строк
    progress_percent = Column(Numeric(5, 2), default=0.0)  # Процент выполнения (0-100)
    cancelled = Column(Boolean, default=False)  # Флаг отмены загрузки
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


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, index=True)
    name_canonical = Column(String, unique=True, nullable=False, index=True)
    key = Column(String, unique=True, nullable=True, index=True)  # Нормализованный ключ для поиска
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    aliases = relationship("BrandAlias", back_populates="brand", cascade="all, delete-orphan")


class BrandAlias(Base):
    __tablename__ = "brand_aliases"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    alias_upper = Column(String, unique=True, nullable=False, index=True)
    alias_key = Column(String, unique=True, nullable=True, index=True)  # Нормализованный ключ для поиска
    created_at = Column(DateTime, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="aliases")


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
    group_key = Column(String, unique=True, nullable=True, index=True)  # ключ карточки (brand|model_name|series)
    
    # Поля для API-обогащения
    external_source = Column(String, nullable=True)  # fragella, etc
    external_key = Column(String, nullable=True, index=True)  # ID во внешней системе
    enrich_status = Column(String, nullable=True, default="pending")  # pending, enriched, needs_review, error
    enrich_confidence = Column(Numeric(3, 2), nullable=True)  # 0..1
    enriched_json = Column(Text, nullable=True)  # JSON с данными обогащения
    
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
    variant_key = Column(String, unique=True, nullable=True, index=True)  # ключ варианта
    
    # Legacy поля
    volume_value = Column(Numeric(10, 2), nullable=True)
    volume_unit = Column(String, nullable=True)
    is_tester = Column(Boolean, default=False, nullable=False)
    gender = Column(String, nullable=True)
    kind = Column(String, nullable=True)
    
    # Новые поля для нормализации
    format = Column(String, nullable=True)  # full/tester/decant/sample/mini
    color = Column(String, nullable=True)
    size_cm = Column(Text, nullable=True)  # JSON: {w:int, h:int}
    pack = Column(Text, nullable=True)  # JSON: {qty:int, unit:string}
    density_raw = Column(String, nullable=True)  # например "40 гр"
    features = Column(Text, nullable=True)  # JSON: list<string>
    volumes_ml = Column(Text, nullable=True)  # JSON: list<int> для наборов
    total_ml = Column(Integer, nullable=True)  # общий объём для наборов
    
    in_stock = Column(Boolean, default=False, nullable=False)
    request_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    catalog_item = relationship("CatalogItem", back_populates="variants")
    price_product = relationship("PriceProduct", back_populates="variants")

    __table_args__ = (
        UniqueConstraint("price_product_id", name="uq_catalog_variant_price_product"),
    )


class PurchaseRequest(Base):
    """Запрос на закупку от партнёра"""
    __tablename__ = "purchase_requests"

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Статусы: "NEW" (новый), "draft" (черновик), "submitted" (отправлен), "PENDING_APPROVAL" (отправлен на подтверждение),
    # "partially_received" (частично получен), "fully_received" (получен полностью), "cancelled" (отменён)
    status = Column(String, nullable=False, default="NEW")
    
    # Даты получения
    expected_delivery_date = Column(Date, nullable=True)  # Ожидаемая дата получения
    actual_delivery_date = Column(Date, nullable=True)  # Фактическая дата получения
    
    # Заметки
    notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)  # Заметки админа
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)  # Когда отправлен на закупку
    
    # Связи
    partner = relationship("Partner", backref="purchase_requests")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    orders = relationship("Order", secondary="purchase_request_orders", back_populates="purchase_requests")


# Промежуточная таблица для связи заказов с запросами на закупку (many-to-many)
purchase_request_orders = sa.Table(
    "purchase_request_orders",
    Base.metadata,
    Column("purchase_request_id", Integer, ForeignKey("purchase_requests.id"), primary_key=True),
    Column("order_id", Integer, ForeignKey("orders.id"), primary_key=True),
    Column("added_at", DateTime, default=datetime.utcnow),
)


class PurchaseRequestItem(Base):
    """Позиция в запросе на закупку с возможностью изменения цены"""
    __tablename__ = "purchase_request_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_request_id = Column(Integer, ForeignKey("purchase_requests.id"), nullable=False)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=False)
    
    # Статусы: "normal" (обычный), "new" (новый товар), "price_changed" (цена изменена), 
    # "pending_approval" (ожидает подтверждения), "confirmation" (подтверждение), "approved" (подтверждён), "rejected" (отклонён)
    status = Column(String, nullable=False, default="normal")
    
    # Цены
    original_price = Column(Numeric(10, 2), nullable=True)  # Исходная цена из заказа
    proposed_price = Column(Numeric(10, 2), nullable=True)  # Предложенная цена от поставщика
    approved_price = Column(Numeric(10, 2), nullable=True)  # Подтверждённая цена
    
    # Комментарии
    price_change_comment = Column(Text, nullable=True)  # Комментарий к изменению цены
    admin_comment = Column(Text, nullable=True)  # Комментарий админа
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    purchase_request = relationship("PurchaseRequest", backref="request_items")
    order_item = relationship("OrderItem")


class Notification(Base):
    """Уведомления для пользователей"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Типы: "purchase_request_new_item" (новый товар в запросе), "purchase_request_price_change" (изменение цены),
    # "purchase_request_approval" (требуется подтверждение), "system_update" (обновление системы),
    # "order_created" (создан новый заказ), "order_items_added" (добавлены товары в заказ)
    type = Column(String, nullable=False)
    
    title = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    
    # Ссылка на связанный объект
    related_type = Column(String, nullable=True)  # "purchase_request", "order", etc.
    related_id = Column(Integer, nullable=True)
    
    # Статус
    is_read = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    read_at = Column(DateTime, nullable=True)
    
    # Связи
    user = relationship("User", backref="notifications")


class ReleaseNote(Base):
    """Релиз-ноутсы (описание изменений в версиях)"""
    __tablename__ = "release_notes"

    id = Column(Integer, primary_key=True, index=True)
    
    # Версия
    version = Column(String, nullable=False, unique=True)  # Например: "1.0.0"
    
    # Заголовок и описание
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)  # Полное описание изменений
    
    # Тип релиза: "major" (крупное обновление), "minor" (новые функции), "patch" (исправления)
    release_type = Column(String, nullable=False, default="minor")
    
    # Дата релиза
    release_date = Column(Date, nullable=False, default=datetime.utcnow)
    
    # Список изменений (JSON или Text)
    changes = Column(Text, nullable=True)  # Можно хранить JSON с категориями: добавлено, изменено, исправлено
    
    # Флаги
    is_published = Column(Boolean, default=False, nullable=False)  # Опубликован ли релиз (для всех)
    is_published_to_partners = Column(Boolean, default=False, nullable=False)  # Опубликован ли для партнеров
    is_important = Column(Boolean, default=False, nullable=False)  # Важное обновление (показывать уведомление)
    max_partner_views = Column(Integer, nullable=True)  # Максимальное количество показов партнерам (None = без ограничений)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    # Можно добавить связь с пользователем, который создал релиз-ноутс
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
