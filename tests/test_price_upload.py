import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from openpyxl import Workbook

from app.main import app
from app.db import Base, get_db
from app.models import PriceProduct, PriceHistory, PriceUpload, User, Role
from app.services.auth_service import get_current_user_from_cookie


def _make_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Позиции"
    ws.append(["Артикул", "Наименование", "Цена"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class DummyRole:
    def __init__(self, name="ADMIN"):
        self.name = name


class DummyUser:
    def __init__(self):
        self.role = DummyRole()
        self.role_id = None
        self.username = "admin"


@pytest.fixture()
def client_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    def override_current_user():
        return DummyUser()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_from_cookie] = override_current_user

    client = TestClient(app)
    try:
        yield client, session
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()


def _upload(client, fileobj, filename="test.xlsx"):
    files = {"file": (filename, fileobj, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    return client.post("/price/upload", files=files, follow_redirects=False)


def test_first_upload_all_new(client_session):
    client, db = client_session
    buf = _make_xlsx([("1", "Item A 10 мл", 10), ("2", "Item B", 20)])
    resp = _upload(client, buf)
    assert resp.status_code == 303

    assert db.query(PriceUpload).count() == 1
    assert db.query(PriceProduct).count() == 2
    hist = db.query(PriceHistory).all()
    assert len(hist) == 2
    assert all(h.change_type == "NEW" for h in hist)
    upload = db.query(PriceUpload).first()
    assert upload.new_count == 2
    assert upload.total_count == 2


def test_second_upload_unchanged(client_session):
    client, db = client_session
    buf = _make_xlsx([("1", "Item A", 10), ("2", "Item B", 20)])
    _upload(client, buf)
    _upload(client, _make_xlsx([("1", "Item A", 10), ("2", "Item B", 20)]))

    uploads = db.query(PriceUpload).order_by(PriceUpload.uploaded_at).all()
    assert len(uploads) == 2
    last_upload = uploads[-1]
    hist = db.query(PriceHistory).filter(PriceHistory.price_upload_id == last_upload.id).all()
    assert len(hist) == 2
    assert all(h.change_type == "UNCHANGED" for h in hist)
    assert last_upload.unchanged_count == 2
    assert last_upload.new_count == 0


def test_price_changes_up_down(client_session):
    client, db = client_session
    _upload(client, _make_xlsx([("1", "Item A", 10), ("2", "Item B", 20)]))
    _upload(client, _make_xlsx([("1", "Item A", 15), ("2", "Item B", 15)]))

    last_upload = db.query(PriceUpload).order_by(PriceUpload.uploaded_at.desc()).first()
    hist = db.query(PriceHistory).filter(PriceHistory.price_upload_id == last_upload.id).all()
    ct = {h.price_product.external_article: h.change_type for h in hist}
    assert ct["1"] == "UP"
    assert ct["2"] == "DOWN"
    assert last_upload.up_count == 1
    assert last_upload.down_count == 1


def test_removed_positions(client_session):
    client, db = client_session
    _upload(client, _make_xlsx([("1", "Item A", 10), ("2", "Item B", 20)]))
    _upload(client, _make_xlsx([("1", "Item A", 10)]))  # remove article 2

    last_upload = db.query(PriceUpload).order_by(PriceUpload.uploaded_at.desc()).first()
    hist = db.query(PriceHistory).filter(PriceHistory.price_upload_id == last_upload.id).all()
    removed = [h for h in hist if h.change_type == "REMOVED"]
    assert len(removed) == 1
    prod = db.query(PriceProduct).filter(PriceProduct.external_article == "2").first()
    assert prod.is_active is False
    assert last_upload.removed_count == 1


def test_delete_upload_recomputes_is_active(client_session):
    client, db = client_session
    _upload(client, _make_xlsx([("1", "Item A", 10), ("2", "Item B", 20)]))
    _upload(client, _make_xlsx([("1", "Item A", 15), ("2", "Item B", 20)]))  # second upload

    uploads = db.query(PriceUpload).order_by(PriceUpload.uploaded_at).all()
    second_id = uploads[-1].id

    resp = client.post(f"/price/upload/{second_id}/delete")
    assert resp.status_code == 303

    # After deletion, latest state should be from first upload
    prod1 = db.query(PriceProduct).filter(PriceProduct.external_article == "1").first()
    prod2 = db.query(PriceProduct).filter(PriceProduct.external_article == "2").first()
    assert prod1.is_active is True
    assert prod2.is_active is True

