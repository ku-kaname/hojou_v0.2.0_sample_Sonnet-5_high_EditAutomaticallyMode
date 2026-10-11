from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import User

_ADMIN_USER_ID = "admin"
_ADMIN_INITIAL_PASSWORD = "integration-test-admin-password"
_CREDENTIALS_EXCEPTION_DETAIL = "資格情報を検証できませんでした"


def _login_and_get_token(client: TestClient, user_id: str, password: str) -> str:
    """指定ユーザーでログインし、アクセストークンを取得する（各テストケースの前提条件整備用）"""
    response = client.post("/token", data={"username": user_id, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _set_user_active_flag(user_id: str, active_flag: bool) -> None:
    """DB上の指定ユーザーのactive_flagを直接更新する（無効化済みユーザーの前提条件整備用）"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).one()
        user.active_flag = active_flag
        db.commit()
    finally:
        db.close()


# ==================================================
# 自分の情報取得
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：get_my_info_endpoint
# テスト仕様書：test_specification/integration_test_specification/認証・ユーザー管理/自分の情報取得_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 初回パスワード変更未了の初期管理者が自分の情報を取得（パスワード変更ガートの対象外であることの確認）
def test_get_my_info_endpoint_001_admin_before_password_change_can_get_own_info(client: TestClient) -> None:
    token = _login_and_get_token(client, _ADMIN_USER_ID, _ADMIN_INITIAL_PASSWORD)

    response = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["user_id"] == _ADMIN_USER_ID
    assert response_body["role"] == "管理者"
    assert response_body["active_flag"] is True
    # 初回ログイン直後はパスワード変更が未了であること（ガートの対象外で200が返ること自体がテスト観点）
    assert response_body["password_change_required_flag"] is True


# ========== 結合テストNo.2 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_get_my_info_endpoint_002_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.get("/users/me")

    assert response.status_code == 401


# ========== 結合テストNo.3 ==========
# 異常系 - 無効化済みユーザーのトークンで取得した場合
def test_get_my_info_endpoint_003_deactivated_user_token_returns_401(client: TestClient) -> None:
    token = _login_and_get_token(client, _ADMIN_USER_ID, _ADMIN_INITIAL_PASSWORD)
    _set_user_active_flag(_ADMIN_USER_ID, False)

    response = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json() == {"detail": _CREDENTIALS_EXCEPTION_DETAIL}


# ==================================================
# パスワード変更
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：change_password_endpoint
# テスト仕様書：test_specification/integration_test_specification/認証・ユーザー管理/パスワード変更_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 正しい現在パスワードでパスワードを変更
def test_change_password_endpoint_001_valid_current_password_changes_password(client: TestClient) -> None:
    token = _login_and_get_token(client, _ADMIN_USER_ID, _ADMIN_INITIAL_PASSWORD)

    response = client.patch(
        "/users/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": _ADMIN_INITIAL_PASSWORD, "new_password": "new-admin-password-01"},
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["token_type"] == "bearer"
    assert response_body["password_change_required"] is False
    assert isinstance(response_body["access_token"], str) and response_body["access_token"] != ""

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.user_id == _ADMIN_USER_ID).one()
        assert admin.password_change_required_flag is False
        assert admin.token_generation == 1  # ログイン時点が0のため、変更後は+1されて1になる
    finally:
        db.close()

    # 新しいパスワードで再ログインできること
    relogin_response = client.post(
        "/token", data={"username": _ADMIN_USER_ID, "password": "new-admin-password-01"}
    )
    assert relogin_response.status_code == 200


# ========== 結合テストNo.2 ==========
# 異常系 - 現在のパスワードが誤っている場合
def test_change_password_endpoint_002_wrong_current_password_returns_400(client: TestClient) -> None:
    token = _login_and_get_token(client, _ADMIN_USER_ID, _ADMIN_INITIAL_PASSWORD)

    response = client.patch(
        "/users/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "incorrect-password", "new_password": "new-admin-password-01"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "現在のパスワードが正しくありません。"}


# ========== 結合テストNo.3 ==========
# 異常系 - 新しいパスワードが8文字未満の場合
def test_change_password_endpoint_003_new_password_too_short_returns_422(client: TestClient) -> None:
    token = _login_and_get_token(client, _ADMIN_USER_ID, _ADMIN_INITIAL_PASSWORD)

    response = client.patch(
        "/users/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": _ADMIN_INITIAL_PASSWORD, "new_password": "short1"},
    )

    assert response.status_code == 422


# ========== 結合テストNo.4 ==========
# 異常系 - 必須パラメータ（new_password）が欠落している場合
def test_change_password_endpoint_004_missing_new_password_returns_422(client: TestClient) -> None:
    token = _login_and_get_token(client, _ADMIN_USER_ID, _ADMIN_INITIAL_PASSWORD)

    response = client.patch(
        "/users/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": _ADMIN_INITIAL_PASSWORD},
    )

    assert response.status_code == 422


# ========== 結合テストNo.5 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_change_password_endpoint_005_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.patch(
        "/users/me/password",
        json={"current_password": "x", "new_password": "new-admin-password-01"},
    )

    assert response.status_code == 401


# ========== 結合テストNo.6 ==========
# 正常系 - パスワード変更後、変更前に発行された旧トークンが失効していること
def test_change_password_endpoint_006_old_token_is_invalidated_after_change(client: TestClient) -> None:
    old_token = _login_and_get_token(client, _ADMIN_USER_ID, _ADMIN_INITIAL_PASSWORD)
    change_response = client.patch(
        "/users/me/password",
        headers={"Authorization": f"Bearer {old_token}"},
        json={"current_password": _ADMIN_INITIAL_PASSWORD, "new_password": "new-admin-password-01"},
    )
    assert change_response.status_code == 200

    response = client.get("/users/me", headers={"Authorization": f"Bearer {old_token}"})

    assert response.status_code == 401
    assert response.json() == {"detail": _CREDENTIALS_EXCEPTION_DETAIL}
