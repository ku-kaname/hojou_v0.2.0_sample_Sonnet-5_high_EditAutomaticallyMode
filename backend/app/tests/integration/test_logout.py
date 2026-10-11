import datetime as dt

import jwt
from fastapi.testclient import TestClient

from app import auth
from app.database import SessionLocal
from app.models import User

_ADMIN_USER_ID = "admin"
_ADMIN_PASSWORD = "integration-test-admin-password"
_CREDENTIALS_EXCEPTION_DETAIL = "資格情報を検証できませんでした"

# ==================================================
# ログアウト
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：logout_endpoint
# テスト仕様書：test_specification/integration_test_specification/共通/ログアウト_結合テスト仕様書_v0.2.0.md
# ==================================================


def _login_and_get_token(client: TestClient) -> str:
    """adminでログインし、アクセストークンを取得する（各テストケースの前提条件整備用）"""
    response = client.post("/token", data={"username": _ADMIN_USER_ID, "password": _ADMIN_PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


def _get_admin_token_generation_from_db() -> int:
    """DB上の初期管理者（admin）のtoken_generationを取得する（アサーション用）"""
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.user_id == _ADMIN_USER_ID).one()
        return admin.token_generation
    finally:
        db.close()


def _set_admin_active_flag(active_flag: bool) -> None:
    """DB上の初期管理者（admin）のactive_flagを直接更新する（無効化済みユーザーの前提条件整備用）"""
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.user_id == _ADMIN_USER_ID).one()
        admin.active_flag = active_flag
        db.commit()
    finally:
        db.close()


# ========== 結合テストNo.1 ==========
# 正常系 - ログイン済みユーザーがログアウト
def test_logout_endpoint_001_logged_in_user_logs_out(client: TestClient) -> None:
    token = _login_and_get_token(client)
    token_generation_before = _get_admin_token_generation_from_db()

    response = client.post("/logout", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 204
    assert response.content == b""
    assert _get_admin_token_generation_from_db() == token_generation_before + 1


# ========== 結合テストNo.2 ==========
# 異常系 - ログアウト済みの旧トークンで再度ログアウトを呼び出した場合、トークンが無効化されていること
def test_logout_endpoint_002_reused_old_token_returns_401(client: TestClient) -> None:
    token = _login_and_get_token(client)
    first_response = client.post("/logout", headers={"Authorization": f"Bearer {token}"})
    assert first_response.status_code == 204

    second_response = client.post("/logout", headers={"Authorization": f"Bearer {token}"})

    assert second_response.status_code == 401
    assert second_response.json() == {"detail": _CREDENTIALS_EXCEPTION_DETAIL}


# ========== 結合テストNo.3 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_logout_endpoint_003_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.post("/logout")

    assert response.status_code == 401


# ========== 結合テストNo.4 ==========
# 異常系 - 改ざん（不正な署名）されたトークンでログアウトを呼び出した場合
def test_logout_endpoint_004_tampered_signature_returns_401(client: TestClient) -> None:
    expire = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=30)
    tampered_token = jwt.encode(
        {"sub": _ADMIN_USER_ID, "tgen": 0, "exp": expire},
        "incorrect-secret-key-used-for-tampering",
        algorithm=auth.JWT_ALGORITHM,
    )

    response = client.post("/logout", headers={"Authorization": f"Bearer {tampered_token}"})

    assert response.status_code == 401
    assert response.json() == {"detail": _CREDENTIALS_EXCEPTION_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - 期限切れのトークンでログアウトを呼び出した場合
def test_logout_endpoint_005_expired_token_returns_401(client: TestClient) -> None:
    expired_at = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    expired_token = jwt.encode(
        {"sub": _ADMIN_USER_ID, "tgen": 0, "exp": expired_at},
        auth.JWT_SECRET_KEY,
        algorithm=auth.JWT_ALGORITHM,
    )

    response = client.post("/logout", headers={"Authorization": f"Bearer {expired_token}"})

    assert response.status_code == 401
    assert response.json() == {"detail": _CREDENTIALS_EXCEPTION_DETAIL}


# ========== 結合テストNo.6 ==========
# 異常系 - 無効化済みユーザーのトークンでログアウトを呼び出した場合
def test_logout_endpoint_006_deactivated_user_token_returns_401(client: TestClient) -> None:
    token = _login_and_get_token(client)
    _set_admin_active_flag(False)

    response = client.post("/logout", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json() == {"detail": _CREDENTIALS_EXCEPTION_DETAIL}
