from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import User

_ADMIN_USER_ID = "admin"
_ADMIN_INITIAL_PASSWORD = "integration-test-admin-password"
_FORBIDDEN_ADMIN_REQUIRED_DETAIL = "この操作には管理者権限が必要です。"
_FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL = "初回パスワード変更が完了していません。パスワードを変更してください。"
_NOT_FOUND_USER_DETAIL = "指定されたユーザーが見つかりません。"


def _login_and_get_token(client: TestClient, user_id: str, password: str) -> str:
    """指定ユーザーでログインし、アクセストークンを取得する（各テストケースの前提条件整備用）"""
    response = client.post("/token", data={"username": user_id, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _get_password_changed_admin_token(client: TestClient) -> str:
    """初期管理者のパスワードを変更済みの状態にし、新しいアクセストークンを取得する

    admin系エンドポイントはrequire_password_changedがrequire_adminより先に評価されるため、
    管理者権限系のテストでは事前にパスワード変更を済ませておく必要がある。
    """
    token = _login_and_get_token(client, _ADMIN_USER_ID, _ADMIN_INITIAL_PASSWORD)
    response = client.patch(
        "/users/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": _ADMIN_INITIAL_PASSWORD, "new_password": "admin-password-changed"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _register_user(
    client: TestClient,
    admin_token: str,
    user_id: str,
    role: str = "一般",
    initial_password: str = "initial-password-01",
    name: str = "テストユーザー",
    department: str = "",
) -> dict:
    """管理者トークンで新規ユーザーを登録する（テストケースの前提条件整備用）"""
    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_id": user_id,
            "name": name,
            "department": department,
            "role": role,
            "initial_password": initial_password,
        },
    )
    assert response.status_code == 201
    return response.json()


def _get_password_changed_user_token(client: TestClient, user_id: str, initial_password: str) -> str:
    """登録済みユーザーのパスワードを変更済みの状態にし、新しいアクセストークンを取得する"""
    token = _login_and_get_token(client, user_id, initial_password)
    response = client.patch(
        "/users/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": initial_password, "new_password": "user-password-changed"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _get_user_from_db(user_id: str) -> User:
    """DB上のユーザー情報を直接取得する（テスト結果のDB永続化確認用）"""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.user_id == user_id).one()
    finally:
        db.close()


# ==================================================
# ユーザー一覧取得
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：get_users_endpoint
# テスト仕様書：test_specification/integration_test_specification/認証・ユーザー管理/ユーザー一覧取得_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - パスワード変更済みの管理者がユーザー一覧を取得（無効化済みユーザーも含まれること）
def test_get_users_endpoint_001_admin_can_get_user_list_including_deactivated(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "list-target-user-01")
    _register_user(client, admin_token, "list-target-user-02")
    deactivate_response = client.patch(
        "/users/list-target-user-02/deactivate", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert deactivate_response.status_code == 200

    response = client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})

    assert response.status_code == 200
    returned_user_ids = {user["user_id"] for user in response.json()}
    assert returned_user_ids == {_ADMIN_USER_ID, "list-target-user-01", "list-target-user-02"}


# ========== 結合テストNo.2 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_get_users_endpoint_002_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "general-user-01")
    general_token = _get_password_changed_user_token(client, "general-user-01", "initial-password-01")

    response = client.get("/users", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.3 ==========
# 異常系 - 初回パスワード変更未了の管理者が呼び出した場合
def test_get_users_endpoint_003_password_change_not_completed_returns_403(client: TestClient) -> None:
    token = _login_and_get_token(client, _ADMIN_USER_ID, _ADMIN_INITIAL_PASSWORD)

    response = client.get("/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_get_users_endpoint_004_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.get("/users")

    assert response.status_code == 401


# ==================================================
# ユーザー登録
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：register_user_endpoint
# テスト仕様書：test_specification/integration_test_specification/認証・ユーザー管理/ユーザー登録_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - パスワード変更済みの管理者が新規ユーザーを登録
def test_register_user_endpoint_001_admin_can_register_new_user(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_id": "new-user-01",
            "name": "新規ユーザー",
            "department": "総務部",
            "role": "一般",
            "initial_password": "initial-pw-01",
        },
    )

    assert response.status_code == 201
    response_body = response.json()
    assert response_body["user_id"] == "new-user-01"
    assert response_body["role"] == "一般"
    assert response_body["active_flag"] is True
    assert response_body["password_change_required_flag"] is True

    created_user = _get_user_from_db("new-user-01")
    assert created_user.name == "新規ユーザー"
    assert created_user.department == "総務部"
    assert created_user.role == "一般"


# ========== 結合テストNo.2 ==========
# 異常系 - 既に使用されているユーザーIDで登録しようとした場合
def test_register_user_endpoint_002_duplicate_user_id_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_id": _ADMIN_USER_ID,
            "name": "重複ユーザー",
            "department": "",
            "role": "一般",
            "initial_password": "initial-pw-01",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "このユーザーIDは既に使用されています。"}


# ========== 結合テストNo.3 ==========
# 異常系 - 無効化済みユーザーのユーザーIDで再登録しようとした場合（無効化済みでもID再利用不可であること）
def test_register_user_endpoint_003_deactivated_user_id_cannot_be_reused(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "deactivated-user-01")
    deactivate_response = client.patch(
        "/users/deactivated-user-01/deactivate", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert deactivate_response.status_code == 200

    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_id": "deactivated-user-01",
            "name": "再登録ユーザー",
            "department": "",
            "role": "一般",
            "initial_password": "initial-pw-01",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "このユーザーIDは既に使用されています。"}


# ========== 結合テストNo.4 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_register_user_endpoint_004_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "general-user-02")
    general_token = _get_password_changed_user_token(client, "general-user-02", "initial-password-01")

    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "user_id": "new-user-02",
            "name": "新規ユーザー",
            "department": "",
            "role": "一般",
            "initial_password": "initial-pw-01",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - 初回パスワード変更未了の管理者が呼び出した場合
def test_register_user_endpoint_005_password_change_not_completed_returns_403(client: TestClient) -> None:
    token = _login_and_get_token(client, _ADMIN_USER_ID, _ADMIN_INITIAL_PASSWORD)

    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": "new-user-03",
            "name": "新規ユーザー",
            "department": "",
            "role": "一般",
            "initial_password": "initial-pw-01",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ========== 結合テストNo.6 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_register_user_endpoint_006_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.post(
        "/users",
        json={
            "user_id": "new-user-04",
            "name": "新規ユーザー",
            "department": "",
            "role": "一般",
            "initial_password": "initial-pw-01",
        },
    )

    assert response.status_code == 401


# ========== 結合テストNo.7 ==========
# 異常系 - バリデーションエラー（user_idに使用可能文字（半角英数字・ハイフン・アンダースコア）以外を含む場合）
def test_register_user_endpoint_007_invalid_user_id_characters_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_id": "新規ユーザー！",
            "name": "新規ユーザー",
            "department": "",
            "role": "一般",
            "initial_password": "initial-pw-01",
        },
    )

    assert response.status_code == 422


# ========== 結合テストNo.8 ==========
# 異常系 - 必須パラメータ（role）が欠落している場合
def test_register_user_endpoint_008_missing_role_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_id": "new-user-05",
            "name": "新規ユーザー",
            "department": "",
            "initial_password": "initial-pw-01",
        },
    )

    assert response.status_code == 422


# ==================================================
# ユーザー詳細取得
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：get_user_endpoint
# テスト仕様書：test_specification/integration_test_specification/認証・ユーザー管理/ユーザー詳細取得_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - パスワード変更済みの管理者が既存ユーザーの詳細を取得
def test_get_user_endpoint_001_admin_can_get_existing_user_detail(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "target-user-01")

    response = client.get("/users/target-user-01", headers={"Authorization": f"Bearer {admin_token}"})

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["user_id"] == "target-user-01"

    user_in_db = _get_user_from_db("target-user-01")
    assert response_body["name"] == user_in_db.name
    assert response_body["role"] == user_in_db.role


# ========== 結合テストNo.2 ==========
# 異常系 - 存在しないユーザーIDを指定した場合
def test_get_user_endpoint_002_nonexistent_user_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.get("/users/not-exist-user", headers={"Authorization": f"Bearer {admin_token}"})

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_USER_DETAIL}


# ========== 結合テストNo.3 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_get_user_endpoint_003_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "general-user-03")
    general_token = _get_password_changed_user_token(client, "general-user-03", "initial-password-01")

    response = client.get("/users/admin", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_get_user_endpoint_004_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.get("/users/admin")

    assert response.status_code == 401


# ==================================================
# ユーザー編集
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：update_user_endpoint
# テスト仕様書：test_specification/integration_test_specification/認証・ユーザー管理/ユーザー編集_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 氏名・所属のみ変更（ロール変更なし）の場合、トークン世代が変更されないこと
def test_update_user_endpoint_001_name_and_department_change_keeps_token_generation(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "target-user-01")
    token_generation_before = _get_user_from_db("target-user-01").token_generation

    response = client.put(
        "/users/target-user-01",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "変更後氏名", "department": "変更後所属", "role": "一般"},
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["user_id"] == "target-user-01"
    assert response_body["name"] == "変更後氏名"
    assert response_body["department"] == "変更後所属"
    assert response_body["role"] == "一般"

    updated_user = _get_user_from_db("target-user-01")
    assert updated_user.token_generation == token_generation_before


# ========== 結合テストNo.2 ==========
# 正常系 - ロールを変更した場合、トークン世代が+1され、対象ユーザーの旧トークンが失効すること
def test_update_user_endpoint_002_role_change_invalidates_old_token(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "target-user-02")
    old_token = _get_password_changed_user_token(client, "target-user-02", "initial-password-01")
    token_generation_before = _get_user_from_db("target-user-02").token_generation

    response = client.put(
        "/users/target-user-02",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "変更後氏名", "department": "", "role": "管理者"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "管理者"

    updated_user = _get_user_from_db("target-user-02")
    assert updated_user.token_generation == token_generation_before + 1

    old_token_response = client.get("/users/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old_token_response.status_code == 401


# ========== 結合テストNo.3 ==========
# 異常系 - 存在しないユーザーIDを指定した場合
def test_update_user_endpoint_003_nonexistent_user_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.put(
        "/users/not-exist-user",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "氏名", "department": "", "role": "一般"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_USER_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 最後の有効な管理者のロールを"一般"へ変更しようとした場合
def test_update_user_endpoint_004_last_active_admin_role_change_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.put(
        "/users/admin",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "admin", "department": "", "role": "一般"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "最後の管理者のロールを変更することはできません。"}


# ========== 結合テストNo.5 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_update_user_endpoint_005_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "general-user-04")
    general_token = _get_password_changed_user_token(client, "general-user-04", "initial-password-01")
    _register_user(client, admin_token, "target-user-03")

    response = client.put(
        "/users/target-user-03",
        headers={"Authorization": f"Bearer {general_token}"},
        json={"name": "氏名", "department": "", "role": "一般"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.6 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_update_user_endpoint_006_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.put("/users/admin", json={"name": "氏名", "department": "", "role": "一般"})

    assert response.status_code == 401


# ========== 結合テストNo.7 ==========
# 異常系 - バリデーションエラー（氏名が空文字の場合）
def test_update_user_endpoint_007_empty_name_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "target-user-04")

    response = client.put(
        "/users/target-user-04",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "", "department": "", "role": "一般"},
    )

    assert response.status_code == 422


# ========== 結合テストNo.8 ==========
# 異常系 - 必須パラメータ（role）が欠落している場合
def test_update_user_endpoint_008_missing_role_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "target-user-05")

    response = client.put(
        "/users/target-user-05",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "氏名", "department": ""},
    )

    assert response.status_code == 422


# ==================================================
# ユーザー無効化
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：deactivate_user_endpoint
# テスト仕様書：test_specification/integration_test_specification/認証・ユーザー管理/ユーザー無効化_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 一般ユーザーを無効化し、対象ユーザーの旧トークンが失効すること
def test_deactivate_user_endpoint_001_deactivating_user_invalidates_old_token(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "target-user-01")
    old_token = _get_password_changed_user_token(client, "target-user-01", "initial-password-01")
    token_generation_before = _get_user_from_db("target-user-01").token_generation

    response = client.patch(
        "/users/target-user-01/deactivate", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["user_id"] == "target-user-01"
    assert response_body["active_flag"] is False

    updated_user = _get_user_from_db("target-user-01")
    assert updated_user.active_flag is False
    assert updated_user.token_generation == token_generation_before + 1

    old_token_response = client.get("/users/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old_token_response.status_code == 401


# ========== 結合テストNo.2 ==========
# 異常系 - 存在しないユーザーIDを指定した場合
def test_deactivate_user_endpoint_002_nonexistent_user_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.patch(
        "/users/not-exist-user/deactivate", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_USER_DETAIL}


# ========== 結合テストNo.3 ==========
# 異常系 - 最後の有効な管理者を無効化しようとした場合
def test_deactivate_user_endpoint_003_last_active_admin_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.patch("/users/admin/deactivate", headers={"Authorization": f"Bearer {admin_token}"})

    assert response.status_code == 409
    assert response.json() == {"detail": "最後の管理者を無効化することはできません。"}


# ========== 結合テストNo.4 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_deactivate_user_endpoint_004_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "general-user-05")
    general_token = _get_password_changed_user_token(client, "general-user-05", "initial-password-01")
    _register_user(client, admin_token, "target-user-02")

    response = client.patch(
        "/users/target-user-02/deactivate", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_deactivate_user_endpoint_005_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.patch("/users/admin/deactivate")

    assert response.status_code == 401


# ==================================================
# ユーザー再有効化
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：activate_user_endpoint
# テスト仕様書：test_specification/integration_test_specification/認証・ユーザー管理/ユーザー再有効化_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 無効化済みユーザーを再有効化し、トークン世代が更新前の値から変更されないこと
def test_activate_user_endpoint_001_reactivating_user_keeps_token_generation(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "target-user-01")
    deactivate_response = client.patch(
        "/users/target-user-01/deactivate", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert deactivate_response.status_code == 200
    token_generation_after_deactivation = _get_user_from_db("target-user-01").token_generation

    response = client.patch(
        "/users/target-user-01/activate", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["user_id"] == "target-user-01"
    assert response_body["active_flag"] is True

    updated_user = _get_user_from_db("target-user-01")
    assert updated_user.active_flag is True
    assert updated_user.token_generation == token_generation_after_deactivation


# ========== 結合テストNo.2 ==========
# 異常系 - 存在しないユーザーIDを指定した場合
def test_activate_user_endpoint_002_nonexistent_user_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.patch(
        "/users/not-exist-user/activate", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_USER_DETAIL}


# ========== 結合テストNo.3 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_activate_user_endpoint_003_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "general-user-06")
    general_token = _get_password_changed_user_token(client, "general-user-06", "initial-password-01")
    _register_user(client, admin_token, "target-user-02")
    deactivate_response = client.patch(
        "/users/target-user-02/deactivate", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert deactivate_response.status_code == 200

    response = client.patch(
        "/users/target-user-02/activate", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_activate_user_endpoint_004_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.patch("/users/admin/activate")

    assert response.status_code == 401


# ==================================================
# パスワード初期化
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：reset_password_endpoint
# テスト仕様書：test_specification/integration_test_specification/認証・ユーザー管理/パスワード初期化_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 管理者が既存ユーザーのパスワードを初期化し、対象ユーザーの旧トークンが失効すること
def test_reset_password_endpoint_001_resetting_password_invalidates_old_token(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "target-user-01")
    old_token = _get_password_changed_user_token(client, "target-user-01", "initial-password-01")
    token_generation_before = _get_user_from_db("target-user-01").token_generation

    response = client.patch(
        "/users/target-user-01/reset-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"initial_password": "reset-pw-01"},
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["user_id"] == "target-user-01"
    assert response_body["password_change_required_flag"] is True

    updated_user = _get_user_from_db("target-user-01")
    assert updated_user.token_generation == token_generation_before + 1

    old_token_response = client.get("/users/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old_token_response.status_code == 401

    relogin_response = client.post("/token", data={"username": "target-user-01", "password": "reset-pw-01"})
    assert relogin_response.status_code == 200


# ========== 結合テストNo.2 ==========
# 異常系 - 存在しないユーザーIDを指定した場合
def test_reset_password_endpoint_002_nonexistent_user_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.patch(
        "/users/not-exist-user/reset-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"initial_password": "reset-pw-01"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_USER_DETAIL}


# ========== 結合テストNo.3 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_reset_password_endpoint_003_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "general-user-07")
    general_token = _get_password_changed_user_token(client, "general-user-07", "initial-password-01")
    _register_user(client, admin_token, "target-user-02")

    response = client.patch(
        "/users/target-user-02/reset-password",
        headers={"Authorization": f"Bearer {general_token}"},
        json={"initial_password": "reset-pw-01"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_reset_password_endpoint_004_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.patch("/users/admin/reset-password", json={"initial_password": "reset-pw-01"})

    assert response.status_code == 401


# ========== 結合テストNo.5 ==========
# 異常系 - 初期パスワードが8文字未満の場合
def test_reset_password_endpoint_005_initial_password_too_short_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "target-user-03")

    response = client.patch(
        "/users/target-user-03/reset-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"initial_password": "short1"},
    )

    assert response.status_code == 422


# ========== 結合テストNo.6 ==========
# 異常系 - 必須パラメータ（initial_password）が欠落している場合
def test_reset_password_endpoint_006_missing_initial_password_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "target-user-04")

    response = client.patch(
        "/users/target-user-04/reset-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={},
    )

    assert response.status_code == 422
