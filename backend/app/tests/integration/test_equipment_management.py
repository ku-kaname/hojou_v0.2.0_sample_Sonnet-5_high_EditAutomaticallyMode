import datetime as dt

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Equipment

_ADMIN_USER_ID = "admin"
_ADMIN_INITIAL_PASSWORD = "integration-test-admin-password"
_FORBIDDEN_ADMIN_REQUIRED_DETAIL = "この操作には管理者権限が必要です。"
_FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL = "初回パスワード変更が完了していません。パスワードを変更してください。"
_NOT_FOUND_EQUIPMENT_DETAIL = "指定された備品が見つかりません。"
_DUPLICATE_ASSET_NUMBER_DETAIL = "この資産番号は既に使用されています。"
_INVALID_HEADER_COLUMN_DETAIL = (
    "ヘッダー行の列構成が不正です。列は資産番号・備品名・分類・説明・保管場所の順にしてください。"
)


def _login_and_get_token(client: TestClient, user_id: str, password: str) -> str:
    """指定ユーザーでログインし、アクセストークンを取得する（各テストケースの前提条件整備用）"""
    response = client.post("/token", data={"username": user_id, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _get_password_changed_admin_token(client: TestClient) -> str:
    """初期管理者のパスワードを変更済みの状態にし、新しいアクセストークンを取得する

    管理者権限系のエンドポイントはrequire_password_changedがrequire_adminより先に評価されるため、
    備品テストでは事前にパスワード変更を済ませておく必要がある。
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
) -> dict:
    """管理者トークンで新規ユーザーを登録する（テストケースの前提条件整備用）"""
    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_id": user_id,
            "name": name,
            "department": "",
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


def _get_general_user_token(client: TestClient, admin_token: str, user_id: str, name: str = "一般ユーザー") -> str:
    """一般ユーザーを登録し、パスワード変更済みのアクセストークンを取得する（備品テストの前提条件整備用）"""
    initial_password = "initial-password-01"
    _register_user(client, admin_token, user_id, name=name, initial_password=initial_password)
    return _get_password_changed_user_token(client, user_id, initial_password)


def _register_equipment(
    client: TestClient,
    admin_token: str,
    asset_number: str,
    name: str = "テスト備品",
    category: str = "PC",
    description: str = "",
    location: str = "",
) -> dict:
    """管理者トークンで新規備品を登録する（テストケースの前提条件整備用）"""
    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "asset_number": asset_number,
            "name": name,
            "category": category,
            "description": description,
            "location": location,
        },
    )
    assert response.status_code == 200
    return response.json()


def _get_equipment_from_db(equipment_id: int) -> Equipment:
    """DB上の備品情報を直接取得する（テスト結果のDB永続化確認用）"""
    db = SessionLocal()
    try:
        return db.query(Equipment).filter(Equipment.id == equipment_id).one()
    finally:
        db.close()


def _make_equipment_on_loan(
    client: TestClient,
    admin_token: str,
    general_token: str,
    equipment_id: int,
    purpose: str = "検証用申請",
) -> dict:
    """対象備品に対して申請→承認→貸出処理を行い、「貸出中」の状態を作る（貸出中前提条件の整備用）

    貸出処理（lend_loan_request）は開始日が今日より後の場合エラーとなるため、
    開始日は必ず今日とする。サーバー側の「今日」はUTCで判定されるため（services.py参照）、
    ローカルタイムゾーンの日付（dt.date.today()）ではなくUTCの日付を用いる。
    """
    today = dt.datetime.now(dt.UTC).date()
    due_date = today + dt.timedelta(days=7)

    create_response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment_id,
            "start_date": today.isoformat(),
            "due_date": due_date.isoformat(),
            "purpose": purpose,
        },
    )
    assert create_response.status_code == 200
    loan_request_id = create_response.json()["loan_request_id"]

    approve_response = client.patch(
        f"/loan-requests/{loan_request_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approve_response.status_code == 200

    lend_response = client.patch(
        f"/loan-requests/{loan_request_id}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert lend_response.status_code == 200
    return lend_response.json()


# ==================================================
# 備品検索一覧取得
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：search_equipment_endpoint
# テスト仕様書：test_specification/integration_test_specification/備品管理/備品検索一覧取得_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 検索条件を指定せずに呼び出した場合、有効な備品が資産番号の昇順で返却されること
def test_search_equipment_endpoint_001_returns_equipment_sorted_by_asset_number(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "search-user-01")
    _register_equipment(client, admin_token, "SRCH-20")
    _register_equipment(client, admin_token, "SRCH-10")

    response = client.get("/equipment", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 200
    asset_number_list = [equipment["asset_number"] for equipment in response.json()]
    assert asset_number_list == ["SRCH-10", "SRCH-20"]


# ========== 結合テストNo.2 ==========
# 正常系 - 分類で絞り込んだ場合、該当分類の備品のみ返却されること
def test_search_equipment_endpoint_002_filters_by_category(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "search-user-02")
    _register_equipment(client, admin_token, "SRCH-CAT-01", category="PC")
    _register_equipment(client, admin_token, "SRCH-CAT-02", category="工具")

    response = client.get("/equipment?category=PC", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 200
    asset_number_list = [equipment["asset_number"] for equipment in response.json()]
    assert asset_number_list == ["SRCH-CAT-01"]


# ========== 結合テストNo.3 ==========
# 正常系 - キーワード（備品名の部分一致）で絞り込んだ場合、該当する備品のみ返却されること
def test_search_equipment_endpoint_003_filters_by_keyword(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "search-user-03")
    _register_equipment(client, admin_token, "SRCH-KW-01", name="ノートPC-A")
    _register_equipment(client, admin_token, "SRCH-KW-02", name="デスクトップPC-B")

    response = client.get("/equipment?keyword=ノート", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 200
    asset_number_list = [equipment["asset_number"] for equipment in response.json()]
    assert asset_number_list == ["SRCH-KW-01"]


# ========== 結合テストNo.4 ==========
# 正常系 - 貸出状況="貸出中"で絞り込んだ場合、貸出中の備品のみ返却され、返却予定日が設定されていること
def test_search_equipment_endpoint_004_filters_by_loan_status_on_loan(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "search-user-04")
    on_loan_equipment = _register_equipment(client, admin_token, "SRCH-LS-01")
    _register_equipment(client, admin_token, "SRCH-LS-02")
    _make_equipment_on_loan(client, admin_token, general_token, on_loan_equipment["equipment_id"])

    response = client.get(
        "/equipment?loan_status=貸出中", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 200
    response_body = response.json()
    asset_number_list = [equipment["asset_number"] for equipment in response_body]
    assert asset_number_list == ["SRCH-LS-01"]
    assert response_body[0]["loan_status"] == "貸出中"
    assert response_body[0]["due_date"] is not None


# ========== 結合テストNo.5 ==========
# 正常系 - 貸出状況="貸出可"で絞り込んだ場合、貸出可の備品のみ返却されること
def test_search_equipment_endpoint_005_filters_by_loan_status_available(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "search-user-05")
    on_loan_equipment = _register_equipment(client, admin_token, "SRCH-LS2-01")
    _register_equipment(client, admin_token, "SRCH-LS2-02")
    _make_equipment_on_loan(client, admin_token, general_token, on_loan_equipment["equipment_id"])

    response = client.get(
        "/equipment?loan_status=貸出可", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 200
    response_body = response.json()
    asset_number_list = [equipment["asset_number"] for equipment in response_body]
    assert asset_number_list == ["SRCH-LS2-02"]
    assert response_body[0]["loan_status"] == "貸出可"
    assert response_body[0]["due_date"] is None


# ========== 結合テストNo.6 ==========
# 正常系 - 管理者がinclude_inactive=trueを指定した場合、無効化済み備品も含めて返却されること
def test_search_equipment_endpoint_006_admin_includes_inactive_equipment(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    inactive_equipment = _register_equipment(client, admin_token, "SRCH-INC-01")
    deactivate_response = client.patch(
        f"/equipment/{inactive_equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate_response.status_code == 200

    response = client.get(
        "/equipment?include_inactive=true", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    asset_number_list = [equipment["asset_number"] for equipment in response.json()]
    assert "SRCH-INC-01" in asset_number_list


# ========== 結合テストNo.7 ==========
# 正常系 - 一般ユーザーがinclude_inactive=trueを指定した場合、無効化済み備品は返却されないこと（アクセス制御）
def test_search_equipment_endpoint_007_general_user_include_inactive_is_ignored(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "search-user-07")
    inactive_equipment = _register_equipment(client, admin_token, "SRCH-INC-02")
    deactivate_response = client.patch(
        f"/equipment/{inactive_equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate_response.status_code == 200

    response = client.get(
        "/equipment?include_inactive=true", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 200
    asset_number_list = [equipment["asset_number"] for equipment in response.json()]
    assert "SRCH-INC-02" not in asset_number_list


# ========== 結合テストNo.8 ==========
# 正常系(境界) - 該当する備品が存在しない検索条件の場合、空リストが返却されること
def test_search_equipment_endpoint_008_no_matching_equipment_returns_empty_list(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "search-user-08")

    response = client.get(
        "/equipment?keyword=存在しないキーワード-xyz", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 200
    assert response.json() == []


# ========== 結合テストNo.9 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_search_equipment_endpoint_009_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.get("/equipment")

    assert response.status_code == 401


# ========== 結合テストNo.10 ==========
# 異常系 - 初回パスワード変更が完了していないユーザーが呼び出した場合
def test_search_equipment_endpoint_010_password_change_not_completed_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "search-user-10")
    token = _login_and_get_token(client, "search-user-10", "initial-password-01")

    response = client.get("/equipment", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 備品詳細取得
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：get_equipment_endpoint
# テスト仕様書：test_specification/integration_test_specification/備品管理/備品詳細取得_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 有効な備品（貸出可）の詳細を取得できること
def test_get_equipment_endpoint_001_returns_available_equipment_detail(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "detail-user-01")
    equipment = _register_equipment(client, admin_token, "DETAIL-01")

    response = client.get(
        f"/equipment/{equipment['equipment_id']}", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["loan_status"] == "貸出可"
    assert response_body["due_date"] is None


# ========== 結合テストNo.2 ==========
# 正常系 - 貸出中の備品を取得した場合、貸出状況="貸出中"・返却予定日が設定されていること
def test_get_equipment_endpoint_002_returns_on_loan_equipment_detail(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "detail-user-02")
    equipment = _register_equipment(client, admin_token, "DETAIL-02")
    _make_equipment_on_loan(client, admin_token, general_token, equipment["equipment_id"])

    response = client.get(
        f"/equipment/{equipment['equipment_id']}", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["loan_status"] == "貸出中"
    assert response_body["due_date"] is not None


# ========== 結合テストNo.3 ==========
# 正常系 - 管理者が無効化済み備品の詳細を取得できること
def test_get_equipment_endpoint_003_admin_can_get_inactive_equipment_detail(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "DETAIL-03")
    deactivate_response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate_response.status_code == 200

    response = client.get(
        f"/equipment/{equipment['equipment_id']}", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert response.json()["active_flag"] is False


# ========== 結合テストNo.4 ==========
# 異常系 - 存在しない備品IDを指定した場合
def test_get_equipment_endpoint_004_nonexistent_equipment_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "detail-user-04")

    response = client.get("/equipment/999999", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_EQUIPMENT_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - 一般ユーザーが無効化済み備品を取得しようとした場合、対象が存在しない場合と同じエラーになること
def test_get_equipment_endpoint_005_general_user_inactive_equipment_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "detail-user-05")
    equipment = _register_equipment(client, admin_token, "DETAIL-05")
    deactivate_response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate_response.status_code == 200

    response = client.get(
        f"/equipment/{equipment['equipment_id']}", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_EQUIPMENT_DETAIL}


# ========== 結合テストNo.6 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_get_equipment_endpoint_006_missing_authorization_header_returns_401(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "DETAIL-06")

    response = client.get(f"/equipment/{equipment['equipment_id']}")

    assert response.status_code == 401


# ========== 結合テストNo.7 ==========
# 異常系 - 初回パスワード変更が完了していないユーザーが呼び出した場合
def test_get_equipment_endpoint_007_password_change_not_completed_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "DETAIL-07")
    _register_user(client, admin_token, "detail-user-07")
    token = _login_and_get_token(client, "detail-user-07", "initial-password-01")

    response = client.get(
        f"/equipment/{equipment['equipment_id']}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ========== 結合テストNo.8 ==========
# 異常系 - 備品IDが数値でない場合
def test_get_equipment_endpoint_008_non_numeric_equipment_id_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "detail-user-08")

    response = client.get("/equipment/abc", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 422


# ==================================================
# 備品登録
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：create_equipment_endpoint
# テスト仕様書：test_specification/integration_test_specification/備品管理/備品登録_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 必須項目のみで登録した場合、説明・保管場所が空文字で登録されること
def test_create_equipment_endpoint_001_required_fields_only(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC-001", "name": "ノートPC", "category": "PC"},
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["asset_number"] == "PC-001"
    assert response_body["description"] == ""
    assert response_body["location"] == ""
    assert response_body["active_flag"] is True
    assert response_body["loan_status"] == "貸出可"
    assert response_body["due_date"] is None

    created_equipment = _get_equipment_from_db(response_body["equipment_id"])
    assert created_equipment.asset_number == "PC-001"


# ========== 結合テストNo.2 ==========
# 正常系 - 全項目を指定して登録できること
def test_create_equipment_endpoint_002_all_fields_specified(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "asset_number": "PC-002",
            "name": "ノートPC2",
            "category": "PC",
            "description": "説明文",
            "location": "本社倉庫",
        },
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["asset_number"] == "PC-002"
    assert response_body["description"] == "説明文"
    assert response_body["location"] == "本社倉庫"
    assert response_body["loan_status"] == "貸出可"
    assert response_body["due_date"] is None


# ========== 結合テストNo.3 ==========
# 異常系 - 資産番号が既存の備品と重複する場合
def test_create_equipment_endpoint_003_duplicate_asset_number_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_equipment(client, admin_token, "PC-003")

    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC-003", "name": "別の備品", "category": "PC"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _DUPLICATE_ASSET_NUMBER_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 資産番号に半角英数字と"-"以外の文字を含む場合
def test_create_equipment_endpoint_004_invalid_asset_number_characters_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC_004", "name": "備品", "category": "PC"},
    )

    assert response.status_code == 422


# ========== 結合テストNo.5 ==========
# 異常系 - 資産番号が33桁以上の場合
def test_create_equipment_endpoint_005_asset_number_too_long_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "A" * 33, "name": "備品", "category": "PC"},
    )

    assert response.status_code == 422


# ========== 結合テストNo.6 ==========
# 異常系 - 備品名が空文字の場合
def test_create_equipment_endpoint_006_empty_name_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC-005", "name": "", "category": "PC"},
    )

    assert response.status_code == 422


# ========== 結合テストNo.7 ==========
# 異常系 - 必須パラメータ（category）が欠落している場合
def test_create_equipment_endpoint_007_missing_category_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC-006", "name": "備品"},
    )

    assert response.status_code == 422


# ========== 結合テストNo.8 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_create_equipment_endpoint_008_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "create-equipment-user-08")

    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {general_token}"},
        json={"asset_number": "PC-007", "name": "備品", "category": "PC"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.9 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_create_equipment_endpoint_009_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.post(
        "/equipment",
        json={"asset_number": "PC-008", "name": "備品", "category": "PC"},
    )

    assert response.status_code == 401


# ========== 結合テストNo.10 ==========
# 異常系 - 初回パスワード変更が完了していない管理者が呼び出した場合
def test_create_equipment_endpoint_010_password_change_not_completed_returns_403(client: TestClient) -> None:
    token = _login_and_get_token(client, _ADMIN_USER_ID, _ADMIN_INITIAL_PASSWORD)

    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {token}"},
        json={"asset_number": "PC-009", "name": "備品", "category": "PC"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 備品編集
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：update_equipment_endpoint
# テスト仕様書：test_specification/integration_test_specification/備品管理/備品編集_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 資産番号を変更せず他項目のみ変更できること
def test_update_equipment_endpoint_001_change_fields_other_than_asset_number(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "PC-101")

    response = client.put(
        f"/equipment/{equipment['equipment_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC-101", "name": "変更後名称", "category": "PC", "description": "", "location": ""},
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["asset_number"] == "PC-101"
    assert response_body["name"] == "変更後名称"


# ========== 結合テストNo.2 ==========
# 正常系 - 資産番号を別の未使用の値に変更できること
def test_update_equipment_endpoint_002_change_asset_number_to_unused_value(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "PC-102")

    response = client.put(
        f"/equipment/{equipment['equipment_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC-102-NEW", "name": "名称", "category": "PC"},
    )

    assert response.status_code == 200
    assert response.json()["asset_number"] == "PC-102-NEW"


# ========== 結合テストNo.3 ==========
# 正常系 - 貸出中の備品を編集した場合、レスポンスの貸出状況が貸出中のまま維持されること
def test_update_equipment_endpoint_003_on_loan_equipment_keeps_loan_status(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "update-equipment-user-03")
    equipment = _register_equipment(client, admin_token, "PC-103")
    _make_equipment_on_loan(client, admin_token, general_token, equipment["equipment_id"])

    response = client.put(
        f"/equipment/{equipment['equipment_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC-103", "name": "変更後名称", "category": "PC"},
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["loan_status"] == "貸出中"
    assert response_body["due_date"] is not None


# ========== 結合テストNo.4 ==========
# 異常系 - 存在しない備品IDを指定した場合
def test_update_equipment_endpoint_004_nonexistent_equipment_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.put(
        "/equipment/999999",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC-104", "name": "名称", "category": "PC"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_EQUIPMENT_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - 変更後の資産番号が他の備品と重複する場合
def test_update_equipment_endpoint_005_duplicate_asset_number_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    target_equipment = _register_equipment(client, admin_token, "PC-105")
    _register_equipment(client, admin_token, "PC-106")

    response = client.put(
        f"/equipment/{target_equipment['equipment_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC-106", "name": "名称", "category": "PC"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _DUPLICATE_ASSET_NUMBER_DETAIL}


# ========== 結合テストNo.6 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_update_equipment_endpoint_006_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "update-equipment-user-06")
    equipment = _register_equipment(client, admin_token, "PC-107")

    response = client.put(
        f"/equipment/{equipment['equipment_id']}",
        headers={"Authorization": f"Bearer {general_token}"},
        json={"asset_number": "PC-107", "name": "名称", "category": "PC"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.7 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_update_equipment_endpoint_007_missing_authorization_header_returns_401(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "PC-108")

    response = client.put(
        f"/equipment/{equipment['equipment_id']}",
        json={"asset_number": "PC-108", "name": "名称", "category": "PC"},
    )

    assert response.status_code == 401


# ========== 結合テストNo.8 ==========
# 異常系 - バリデーションエラー（分類が空文字）の場合
def test_update_equipment_endpoint_008_empty_category_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "PC-109")

    response = client.put(
        f"/equipment/{equipment['equipment_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC-109", "name": "名称", "category": ""},
    )

    assert response.status_code == 422


# ========== 結合テストNo.9 ==========
# 異常系 - 必須パラメータ（name）が欠落している場合
def test_update_equipment_endpoint_009_missing_name_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "PC-110")

    response = client.put(
        f"/equipment/{equipment['equipment_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"asset_number": "PC-110", "category": "PC"},
    )

    assert response.status_code == 422


# ==================================================
# 備品無効化
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：deactivate_equipment_endpoint
# テスト仕様書：test_specification/integration_test_specification/備品管理/備品無効化_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 有効な備品を無効化できること
def test_deactivate_equipment_endpoint_001_deactivates_active_equipment(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "DEACT-01")

    response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["active_flag"] is False

    updated_equipment = _get_equipment_from_db(equipment["equipment_id"])
    assert updated_equipment.active_flag is False


# ========== 結合テストNo.2 ==========
# 正常系 - 既に無効化済みの備品を再度無効化した場合でも成功すること
def test_deactivate_equipment_endpoint_002_deactivating_already_inactive_equipment_succeeds(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "DEACT-02")
    first_response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert first_response.status_code == 200

    response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["active_flag"] is False


# ========== 結合テストNo.3 ==========
# 異常系 - 存在しない備品IDを指定した場合
def test_deactivate_equipment_endpoint_003_nonexistent_equipment_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.patch(
        "/equipment/999999/deactivate", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_EQUIPMENT_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_deactivate_equipment_endpoint_004_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "deactivate-equipment-user-04")
    equipment = _register_equipment(client, admin_token, "DEACT-04")

    response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {general_token}"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_deactivate_equipment_endpoint_005_missing_authorization_header_returns_401(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "DEACT-05")

    response = client.patch(f"/equipment/{equipment['equipment_id']}/deactivate")

    assert response.status_code == 401


# ========== 結合テストNo.6 ==========
# 異常系 - 初回パスワード変更が完了していない管理者が呼び出した場合
def test_deactivate_equipment_endpoint_006_password_change_not_completed_returns_403(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "DEACT-06")
    _register_user(client, admin_token, "deactivate-new-admin-06", role="管理者")
    token = _login_and_get_token(client, "deactivate-new-admin-06", "initial-password-01")

    response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 備品再有効化
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：activate_equipment_endpoint
# テスト仕様書：test_specification/integration_test_specification/備品管理/備品再有効化_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 無効化済みの備品を再有効化できること
def test_activate_equipment_endpoint_001_activates_inactive_equipment(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "ACT-01")
    deactivate_response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate_response.status_code == 200

    response = client.patch(
        f"/equipment/{equipment['equipment_id']}/activate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["active_flag"] is True

    updated_equipment = _get_equipment_from_db(equipment["equipment_id"])
    assert updated_equipment.active_flag is True


# ========== 結合テストNo.2 ==========
# 正常系 - 既に有効な備品を再有効化した場合でも成功すること
def test_activate_equipment_endpoint_002_activating_already_active_equipment_succeeds(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "ACT-02")

    response = client.patch(
        f"/equipment/{equipment['equipment_id']}/activate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["active_flag"] is True


# ========== 結合テストNo.3 ==========
# 異常系 - 存在しない備品IDを指定した場合
def test_activate_equipment_endpoint_003_nonexistent_equipment_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.patch(
        "/equipment/999999/activate", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_EQUIPMENT_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_activate_equipment_endpoint_004_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "activate-equipment-user-04")
    equipment = _register_equipment(client, admin_token, "ACT-04")
    deactivate_response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate_response.status_code == 200

    response = client.patch(
        f"/equipment/{equipment['equipment_id']}/activate",
        headers={"Authorization": f"Bearer {general_token}"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_activate_equipment_endpoint_005_missing_authorization_header_returns_401(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "ACT-05")

    response = client.patch(f"/equipment/{equipment['equipment_id']}/activate")

    assert response.status_code == 401


# ==================================================
# 備品予約状況確認
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：get_equipment_reservations_endpoint
# テスト仕様書：test_specification/integration_test_specification/備品管理/備品予約状況確認_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 管理者が予約状況を確認した場合、借用者氏名を含めて返却されること
def test_get_equipment_reservations_endpoint_001_admin_sees_applicant_name(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(
        client, admin_token, "reservation-user-01", name="予約確認太郎"
    )
    equipment = _register_equipment(client, admin_token, "RSV-01")
    _make_equipment_on_loan(client, admin_token, general_token, equipment["equipment_id"])

    response = client.get(
        f"/equipment/{equipment['equipment_id']}/reservations",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    response_body = response.json()
    assert len(response_body) == 1
    assert response_body[0]["status"] == "貸出中"
    assert response_body[0]["applicant_name"] == "予約確認太郎"


# ========== 結合テストNo.2 ==========
# 正常系 - 一般ユーザーが予約状況を確認した場合、借用者氏名の項目自体が含まれないこと
def test_get_equipment_reservations_endpoint_002_general_user_excludes_applicant_name(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "reservation-user-02")
    equipment = _register_equipment(client, admin_token, "RSV-02")
    _make_equipment_on_loan(client, admin_token, general_token, equipment["equipment_id"])

    response = client.get(
        f"/equipment/{equipment['equipment_id']}/reservations",
        headers={"Authorization": f"Bearer {general_token}"},
    )

    assert response.status_code == 200
    response_body = response.json()
    assert len(response_body) == 1
    assert "applicant_name" not in response_body[0]


# ========== 結合テストNo.3 ==========
# 正常系 - 承認済み・貸出中の申請が存在しない備品の場合、空リストが返却されること
def test_get_equipment_reservations_endpoint_003_no_reservations_returns_empty_list(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "reservation-user-03")
    equipment = _register_equipment(client, admin_token, "RSV-03")

    response = client.get(
        f"/equipment/{equipment['equipment_id']}/reservations",
        headers={"Authorization": f"Bearer {general_token}"},
    )

    assert response.status_code == 200
    assert response.json() == []


# ========== 結合テストNo.4 ==========
# 異常系 - 存在しない備品IDを指定した場合
def test_get_equipment_reservations_endpoint_004_nonexistent_equipment_id_returns_404(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "reservation-user-04")

    response = client.get(
        "/equipment/999999/reservations", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_EQUIPMENT_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - 一般ユーザーが無効化済み備品の予約状況を確認しようとした場合、対象が存在しない場合と同じエラーになること
def test_get_equipment_reservations_endpoint_005_general_user_inactive_equipment_returns_404(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "reservation-user-05")
    equipment = _register_equipment(client, admin_token, "RSV-05")
    deactivate_response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate_response.status_code == 200

    response = client.get(
        f"/equipment/{equipment['equipment_id']}/reservations",
        headers={"Authorization": f"Bearer {general_token}"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_EQUIPMENT_DETAIL}


# ========== 結合テストNo.6 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_get_equipment_reservations_endpoint_006_missing_authorization_header_returns_401(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "RSV-06")

    response = client.get(f"/equipment/{equipment['equipment_id']}/reservations")

    assert response.status_code == 401


# ========== 結合テストNo.7 ==========
# 異常系 - 初回パスワード変更が完了していないユーザーが呼び出した場合
def test_get_equipment_reservations_endpoint_007_password_change_not_completed_returns_403(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "RSV-07")
    _register_user(client, admin_token, "reservation-user-07")
    token = _login_and_get_token(client, "reservation-user-07", "initial-password-01")

    response = client.get(
        f"/equipment/{equipment['equipment_id']}/reservations",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 備品CSV一括登録
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：bulk_import_equipment_endpoint
# テスト仕様書：test_specification/integration_test_specification/備品管理/備品CSV一括登録_結合テスト仕様書.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 正しいCSV（複数行）をアップロードした場合、全件登録され登録件数・備品情報リストが返却されること
def test_bulk_import_equipment_endpoint_001_valid_csv_registers_all_rows(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    csv_content = (
        "資産番号,備品名,分類,説明,保管場所\n"
        "CSV-101,備品イチ,分類A,説明イチ,場所イチ\n"
        "CSV-102,備品ニ,分類B,説明ニ,場所ニ"
    ).encode()

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["registered_count"] == 2
    asset_number_list = [equipment["asset_number"] for equipment in response_body["equipment_list"]]
    assert asset_number_list == ["CSV-101", "CSV-102"]
    for equipment in response_body["equipment_list"]:
        assert equipment["loan_status"] == "貸出可"
        assert equipment["due_date"] is None


# ========== 結合テストNo.2 ==========
# 異常系 - ファイルサイズが上限（5MB）を超える場合
def test_bulk_import_equipment_endpoint_002_file_size_exceeds_limit_returns_400(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    csv_content = "資産番号,備品名,分類,説明,保管場所\n".encode() + b"A" * (5 * 1024 * 1024 + 100)

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {"error_list": [{"row_number": None, "message": "ファイルサイズが上限（5MB）を超えています。"}]}
    }


# ========== 結合テストNo.3 ==========
# 異常系 - ファイルの文字コードがUTF-8でない場合
def test_bulk_import_equipment_endpoint_003_non_utf8_encoding_returns_400(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    csv_content = (
        "資産番号,備品名,分類,説明,保管場所\nSJ-001,日本語備品名,分類,,"
    ).encode("shift_jis")

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "error_list": [
                {"row_number": None, "message": "ファイルの文字コードが不正です。UTF-8で保存してください。"}
            ]
        }
    }


# ========== 結合テストNo.4 ==========
# 異常系 - ヘッダー行の列数が5でない場合
def test_bulk_import_equipment_endpoint_004_invalid_header_column_count_returns_400(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    csv_content = ("資産番号,備品名,分類,説明\nCSV-401,備品,分類,説明").encode()

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {"error_list": [{"row_number": None, "message": _INVALID_HEADER_COLUMN_DETAIL}]}
    }


# ========== 結合テストNo.5 ==========
# 異常系 - データ行数が上限（1,000行）を超える場合
def test_bulk_import_equipment_endpoint_005_data_row_count_exceeds_limit_returns_400(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    data_row_list = [f"CSV-{row_index:04d},備品,分類,," for row_index in range(1, 1002)]
    csv_content = ("資産番号,備品名,分類,説明,保管場所\n" + "\n".join(data_row_list)).encode("utf-8")

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {"error_list": [{"row_number": None, "message": "データ行数が上限（1,000行）を超えています。"}]}
    }


# ========== 結合テストNo.6 ==========
# 異常系 - データ行の列数が5でない行がある場合、行番号付きエラーが返却され、以降の重複チェックが行われないこと
def test_bulk_import_equipment_endpoint_006_invalid_column_count_row_returns_400(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    csv_content = (
        "資産番号,備品名,分類,説明,保管場所\n"
        "CSV-601,備品六イチ,分類,,\n"
        "CSV-602,備品六ニ,分類,説明"
    ).encode()

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": {"error_list": [{"row_number": 2, "message": "列数が不正です。"}]}}


# ========== 結合テストNo.7 ==========
# 異常系 - 資産番号が不正（空、32桁超、または半角英数字と"-"以外を含む）な行がある場合
def test_bulk_import_equipment_endpoint_007_invalid_asset_number_row_returns_400(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    csv_content = (
        "資産番号,備品名,分類,説明,保管場所\n"
        "CSV-701,備品七イチ,分類,,\n"
        "PC_002,備品七ニ,分類,,"
    ).encode()

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": {"error_list": [{"row_number": 2, "message": "資産番号が不正です。"}]}}


# ========== 結合テストNo.8 ==========
# 異常系 - 備品名・分類・説明・保管場所の桁数違反が1行に複数ある場合、違反ごとに1件のエラーが追加されること
def test_bulk_import_equipment_endpoint_008_multiple_violations_in_one_row_returns_400(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    csv_content = (
        "資産番号,備品名,分類,説明,保管場所\n"
        "CSV-801,備品八イチ,分類,,\n"
        "CSV-802,,,,"
    ).encode()

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "error_list": [
                {"row_number": 2, "message": "備品名が不正です。"},
                {"row_number": 2, "message": "分類が不正です。"},
            ]
        }
    }


# ========== 結合テストNo.9 ==========
# 異常系 - CSV内で資産番号が重複する場合、最初に出現した行を除く2件目以降の行番号にエラーが付与されること
def test_bulk_import_equipment_endpoint_009_duplicate_asset_number_in_csv_returns_400(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    csv_content = (
        "資産番号,備品名,分類,説明,保管場所\n"
        "CSV-901,備品九イチ,分類,,\n"
        "PC-010,備品九ニ,分類,,\n"
        "PC-010,備品九サン,分類,,"
    ).encode()

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": {"error_list": [{"row_number": 3, "message": "資産番号が重複しています。"}]}}


# ========== 結合テストNo.10 ==========
# 異常系 - CSV内の資産番号がデータベースに既に登録済みの資産番号と重複する場合
def test_bulk_import_equipment_endpoint_010_duplicate_asset_number_in_db_returns_400(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_equipment(client, admin_token, "PC-011")
    csv_content = (
        "資産番号,備品名,分類,説明,保管場所\n"
        "CSV-1001,備品十イチ,分類,,\n"
        "PC-011,備品十ニ,分類,,"
    ).encode()

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {"error_list": [{"row_number": 2, "message": _DUPLICATE_ASSET_NUMBER_DETAIL}]}
    }


# ========== 結合テストNo.11 ==========
# 異常系 - 1行でもエラーがある場合、エラーがない行も含めて全件登録されないこと
def test_bulk_import_equipment_endpoint_011_any_error_prevents_all_registration(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    csv_content = (
        "資産番号,備品名,分類,説明,保管場所\n"
        "CSV-1101,備品十一イチ,分類,,\n"
        "CSV-1102,備品十一ニ,分類,,\n"
        "CSV-1103,,分類,,"
    ).encode()

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400

    search_response = client.get("/equipment", headers={"Authorization": f"Bearer {admin_token}"})
    asset_number_list = [equipment["asset_number"] for equipment in search_response.json()]
    assert "CSV-1102" not in asset_number_list


# ========== 結合テストNo.12 ==========
# 異常系 - 複数のエラーが異なる行番号に存在する場合、エラー一覧が行番号の昇順で返却されること
def test_bulk_import_equipment_endpoint_012_errors_sorted_by_row_number_ascending(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    csv_content = (
        "資産番号,備品名,分類,説明,保管場所\n"
        "CSV-1201,備品十二イチ,分類,,\n"
        "CSV-1202,,分類,,\n"
        "CSV-1203,備品十二サン,,,"
    ).encode()

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "error_list": [
                {"row_number": 2, "message": "備品名が不正です。"},
                {"row_number": 3, "message": "分類が不正です。"},
            ]
        }
    }


# ========== 結合テストNo.13 ==========
# 正常系(境界) - データ行が0件（ヘッダー行のみ）の場合、0件登録で成功すること
def test_bulk_import_equipment_endpoint_013_zero_data_rows_succeeds(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    csv_content = "資産番号,備品名,分類,説明,保管場所".encode()

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json() == {"registered_count": 0, "equipment_list": []}


# ========== 結合テストNo.14 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_bulk_import_equipment_endpoint_014_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "bulk-import-user-14")
    csv_content = ("資産番号,備品名,分類,説明,保管場所\nCSV-1401,備品,分類,,").encode()

    response = client.post(
        "/equipment/bulk-import",
        headers={"Authorization": f"Bearer {general_token}"},
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.15 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_bulk_import_equipment_endpoint_015_missing_authorization_header_returns_401(
    client: TestClient,
) -> None:
    csv_content = ("資産番号,備品名,分類,説明,保管場所\nCSV-1501,備品,分類,,").encode()

    response = client.post(
        "/equipment/bulk-import",
        files={"file": ("equipment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 401
