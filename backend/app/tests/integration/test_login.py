import datetime as dt

import jwt
from fastapi.testclient import TestClient

from app import auth
from app.database import SessionLocal
from app.models import User

_ADMIN_USER_ID = "admin"
_ADMIN_PASSWORD = "integration-test-admin-password"

# ==================================================
# ログイン
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：login_endpoint
# テスト仕様書：test_specification/integration_test_specification/共通/ログイン_結合テスト仕様書_v0.2.0.md
# ==================================================


def _get_admin_from_db() -> User:
    """DB上の初期管理者（admin）レコードを取得する（アサーション用）"""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.user_id == _ADMIN_USER_ID).one()
    finally:
        db.close()


def _assert_locked_until_is_in_future(locked_until: dt.datetime) -> None:
    """locked_untilが現在日時より後の値であることを確認する（タイムゾーン有無の差異を吸収して比較する）"""
    locked_until_naive = locked_until.replace(tzinfo=None) if locked_until.tzinfo else locked_until
    now_naive = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    assert locked_until_naive > now_naive


# ========== 結合テストNo.1 ==========
# 正常系 - 正しいユーザーID・パスワードでログイン
def test_login_endpoint_001_valid_credentials_returns_token(client: TestClient) -> None:
    response = client.post("/token", data={"username": _ADMIN_USER_ID, "password": _ADMIN_PASSWORD})

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["token_type"] == "bearer"
    assert response_body["password_change_required"] is True

    payload = jwt.decode(response_body["access_token"], auth.JWT_SECRET_KEY, algorithms=[auth.JWT_ALGORITHM])
    assert payload["sub"] == _ADMIN_USER_ID
    assert payload["tgen"] == 0

    admin = _get_admin_from_db()
    assert admin.login_failure_count == 0
    assert admin.locked_until is None


# ========== 結合テストNo.2 ==========
# 異常系 - 存在しないユーザーIDでログイン
def test_login_endpoint_002_unknown_user_id_returns_401(client: TestClient) -> None:
    response = client.post("/token", data={"username": "notexist", "password": "anypassword"})

    assert response.status_code == 401
    assert response.json() == {"detail": "ユーザーIDかパスワードが間違っています。"}


# ========== 結合テストNo.3 ==========
# 異常系 - 誤ったパスワードでログイン
def test_login_endpoint_003_wrong_password_returns_401(client: TestClient) -> None:
    response = client.post("/token", data={"username": _ADMIN_USER_ID, "password": "wrong-password"})

    assert response.status_code == 401
    assert response.json() == {"detail": "ユーザーIDかパスワードが間違っています。"}

    admin = _get_admin_from_db()
    assert admin.login_failure_count == 1


# ========== 結合テストNo.4 ==========
# 異常系 - ログイン失敗を5回連続した場合、5回目でアカウントが一時的にロックされること
def test_login_endpoint_004_five_consecutive_failures_locks_account(client: TestClient) -> None:
    for attempt_count in range(1, 5):
        response = client.post("/token", data={"username": _ADMIN_USER_ID, "password": "wrong-password"})
        assert response.status_code == 401, f"{attempt_count}回目の失敗レスポンスが想定外"
        assert response.json() == {"detail": "ユーザーIDかパスワードが間違っています。"}

    fifth_response = client.post("/token", data={"username": _ADMIN_USER_ID, "password": "wrong-password"})
    assert fifth_response.status_code == 401
    assert fifth_response.json() == {
        "detail": (
            "ログイン試行回数が上限に達したため、アカウントが一時的にロックされています。"
            "しばらくしてから再度お試しください。"
        )
    }

    admin = _get_admin_from_db()
    _assert_locked_until_is_in_future(admin.locked_until)


# ========== 結合テストNo.5 ==========
# 異常系 - アカウントロック中に正しいパスワードでログインしても失敗すること
def test_login_endpoint_005_locked_account_rejects_correct_password(client: TestClient) -> None:
    for _ in range(5):
        client.post("/token", data={"username": _ADMIN_USER_ID, "password": "wrong-password"})

    response = client.post("/token", data={"username": _ADMIN_USER_ID, "password": _ADMIN_PASSWORD})

    assert response.status_code == 401
    assert response.json() == {
        "detail": (
            "ログイン試行回数が上限に達したため、アカウントが一時的にロックされています。"
            "しばらくしてから再度お試しください。"
        )
    }


# ========== 結合テストNo.6 ==========
# 異常系 - 必須パラメータ欠落（passwordを送信しない）
def test_login_endpoint_006_missing_password_returns_422(client: TestClient) -> None:
    response = client.post("/token", data={"username": _ADMIN_USER_ID})

    assert response.status_code == 422


# ========== 結合テストNo.7 ==========
# 異常系 - 必須パラメータ欠落（usernameを送信しない）
def test_login_endpoint_007_missing_username_returns_422(client: TestClient) -> None:
    response = client.post("/token", data={"password": _ADMIN_PASSWORD})

    assert response.status_code == 422
