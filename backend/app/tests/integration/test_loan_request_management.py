import datetime as dt

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import LoanRequest, User

_ADMIN_USER_ID = "admin"
_ADMIN_INITIAL_PASSWORD = "integration-test-admin-password"
_FORBIDDEN_ADMIN_REQUIRED_DETAIL = "この操作には管理者権限が必要です。"
_FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL = "初回パスワード変更が完了していません。パスワードを変更してください。"
_FORBIDDEN_SCOPE_DETAIL = "この操作を行う権限がありません。"
_NOT_FOUND_EQUIPMENT_DETAIL = "指定された備品が見つかりません。"
_NOT_FOUND_LOAN_REQUEST_DETAIL = "指定された貸出申請が見つかりません。"
_NOT_FOUND_NOTIFICATION_DETAIL = "指定された通知が見つかりません。"
_CONFLICT_EQUIPMENT_INACTIVE_DETAIL = "指定された備品は無効化されているため、貸出を申請できません。"
_CONFLICT_PERIOD_OVERLAP_DETAIL = "指定した期間は、既に承認済みまたは貸出中の申請と重複しています。"
_BAD_REQUEST_START_DATE_DETAIL = "開始日には今日以降の日付を指定してください。"
_BAD_REQUEST_DUE_DATE_DETAIL = "返却予定日には開始日以降の日付を指定してください。"
_CONFLICT_CANNOT_APPROVE_DETAIL = "この申請は現在の状態では承認できません。"
_CONFLICT_APPROVE_PAST_START_DATE_DETAIL = "開始日を過ぎているため、この申請は承認できません。"
_CONFLICT_CANNOT_REJECT_DETAIL = "この申請は現在の状態では却下できません。"
_CONFLICT_CANNOT_CANCEL_DETAIL = "この申請は現在の状態では取消できません。"


def _login_and_get_token(client: TestClient, user_id: str, password: str) -> str:
    """指定ユーザーでログインし、アクセストークンを取得する（各テストケースの前提条件整備用）"""
    response = client.post("/token", data={"username": user_id, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _get_password_changed_admin_token(client: TestClient) -> str:
    """初期管理者のパスワードを変更済みの状態にし、新しいアクセストークンを取得する

    管理者権限系のエンドポイントはrequire_password_changedがrequire_adminより先に評価されるため、
    貸出申請・承認のテストでは事前にパスワード変更を済ませておく必要がある。
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
    """一般ユーザーを登録し、パスワード変更済みのアクセストークンを取得する（テストの前提条件整備用）"""
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


def _get_user_internal_id_from_db(user_id: str) -> int:
    """DB上のユーザー情報から内部ID（数値）を直接取得する（申請者ID等の比較確認用）"""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.user_id == user_id).one().id
    finally:
        db.close()


def _set_loan_request_start_date_in_db(loan_request_id: int, start_date: dt.date) -> None:
    """DB上の貸出申請の開始日を直接更新する（開始日が過去日の「申請中」状態の前提条件整備用。
    API経由では開始日に過去日を指定した時点で登録自体が失敗するため、DBを直接更新してテスト条件を作る）"""
    db = SessionLocal()
    try:
        target_loan_request = db.query(LoanRequest).filter(LoanRequest.id == loan_request_id).one()
        target_loan_request.start_date = start_date
        db.commit()
    finally:
        db.close()


def _set_loan_request_due_date_in_db(loan_request_id: int, due_date: dt.date) -> None:
    """DB上の貸出申請の返却予定日を直接更新する（返却予定日を過ぎた「貸出中」状態の前提条件整備用。
    API経由では返却予定日に過去日を指定できないため、DBを直接更新してテスト条件を作る）"""
    db = SessionLocal()
    try:
        target_loan_request = db.query(LoanRequest).filter(LoanRequest.id == loan_request_id).one()
        target_loan_request.due_date = due_date
        db.commit()
    finally:
        db.close()


def _date_iso(offset_days: int) -> str:
    """サーバー側の「今日」（UTC基準）から指定日数だけずらした日付をISO8601形式の文字列で取得する

    開始日・返却予定日の判定はUTCの日付で行われるため（services.py参照）、
    ローカルタイムゾーンの日付（dt.date.today()）ではなくUTCの日付を用いる。
    """
    return (dt.datetime.now(dt.UTC).date() + dt.timedelta(days=offset_days)).isoformat()


def _create_loan_request(
    client: TestClient,
    token: str,
    equipment_id: int,
    start_date: str | None = None,
    due_date: str | None = None,
    purpose: str = "資料作成のため",
) -> dict:
    """貸出申請を登録する（テストケースの前提条件整備用。開始日・返却予定日省略時は今日〜翌日とする）"""
    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "equipment_id": equipment_id,
            "start_date": start_date if start_date is not None else _date_iso(0),
            "due_date": due_date if due_date is not None else _date_iso(1),
            "purpose": purpose,
        },
    )
    assert response.status_code == 200
    return response.json()


def _approve_loan_request(client: TestClient, admin_token: str, loan_request_id: int) -> dict:
    """貸出申請を承認する（テストケースの前提条件整備用）"""
    response = client.patch(
        f"/loan-requests/{loan_request_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    return response.json()


def _reject_loan_request(
    client: TestClient, admin_token: str, loan_request_id: int, reason: str = "点検予定と重複するため"
) -> dict:
    """貸出申請を却下する（テストケースの前提条件整備用）"""
    response = client.patch(
        f"/loan-requests/{loan_request_id}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": reason},
    )
    assert response.status_code == 200
    return response.json()


def _lend_loan_request(client: TestClient, admin_token: str, loan_request_id: int) -> dict:
    """承認済みの貸出申請に対して貸出処理を行う（「貸出中」状態の前提条件整備用）"""
    response = client.patch(
        f"/loan-requests/{loan_request_id}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    return response.json()


def _create_approved_loan_request(
    client: TestClient,
    admin_token: str,
    general_token: str,
    equipment_id: int,
    start_date: str | None = None,
    due_date: str | None = None,
) -> dict:
    """申請中の貸出申請を登録し、承認済みの状態にする（「承認済み」状態の前提条件整備用）"""
    created = _create_loan_request(client, general_token, equipment_id, start_date, due_date)
    return _approve_loan_request(client, admin_token, created["loan_request_id"])


def _create_loan_request_on_loan(
    client: TestClient, admin_token: str, general_token: str, equipment_id: int
) -> dict:
    """申請中の貸出申請を登録し、承認→貸出処理を行って「貸出中」の状態にする（「貸出中」状態の前提条件整備用）

    貸出処理（lend_loan_request）は開始日が今日より後の場合エラーとなるため、開始日は必ず今日とする。
    """
    approved = _create_approved_loan_request(
        client, admin_token, general_token, equipment_id, start_date=_date_iso(0), due_date=_date_iso(7)
    )
    return _lend_loan_request(client, admin_token, approved["loan_request_id"])


# ==================================================
# 貸出申請登録
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：create_loan_request_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出申請・承認/貸出申請登録_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 開始日が今日、返却予定日がそれより先の日付で登録できること
def test_create_loan_request_endpoint_001_registers_with_today_start_and_later_due_date(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-01")
    equipment = _register_equipment(client, admin_token, "LNCR-01")
    start_date = _date_iso(0)
    due_date = _date_iso(1)

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": start_date,
            "due_date": due_date,
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["equipment_id"] == equipment["equipment_id"]
    assert body["start_date"] == start_date
    assert body["due_date"] == due_date
    assert body["purpose"] == "資料作成のため"
    assert body["status"] == "申請中"
    assert body["applicant_user_id"] == _get_user_internal_id_from_db("loan-create-user-01")
    assert body["reject_cancel_reason"] == ""
    assert body["approved_rejected_by_user_id"] is None
    assert body["lent_by_user_id"] is None
    assert body["cancelled_by_user_id"] is None


# ========== 結合テストNo.2 ==========
# 正常系 - 開始日と返却予定日が同日の場合に登録できること（境界値）
def test_create_loan_request_endpoint_002_registers_with_same_start_and_due_date(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-02")
    equipment = _register_equipment(client, admin_token, "LNCR-02")
    today = _date_iso(0)

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": today,
            "due_date": today,
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["start_date"] == today
    assert body["due_date"] == today
    assert body["status"] == "申請中"


# ========== 結合テストNo.3 ==========
# 異常系 - 指定した備品が存在しない場合
def test_create_loan_request_endpoint_003_nonexistent_equipment_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-03")

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": 999999,
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_EQUIPMENT_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 対象備品が無効化済みの場合
def test_create_loan_request_endpoint_004_inactive_equipment_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-04")
    equipment = _register_equipment(client, admin_token, "LNCR-04")
    deactivate_response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate_response.status_code == 200

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_EQUIPMENT_INACTIVE_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - 開始日が前日（過去日）の場合
def test_create_loan_request_endpoint_005_past_start_date_returns_400(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-05")
    equipment = _register_equipment(client, admin_token, "LNCR-05")

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(-1),
            "due_date": _date_iso(0),
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": _BAD_REQUEST_START_DATE_DETAIL}


# ========== 結合テストNo.6 ==========
# 異常系 - 返却予定日が開始日の前日の場合
def test_create_loan_request_endpoint_006_due_date_before_start_date_returns_400(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-06")
    equipment = _register_equipment(client, admin_token, "LNCR-06")

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(1),
            "due_date": _date_iso(0),
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": _BAD_REQUEST_DUE_DATE_DETAIL}


# ========== 結合テストNo.7 ==========
# 異常系 - 同一備品について承認済みの申請と期間が重複する場合
def test_create_loan_request_endpoint_007_overlap_with_approved_request_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-07")
    equipment = _register_equipment(client, admin_token, "LNCR-07")
    _create_approved_loan_request(client, admin_token, general_token, equipment["equipment_id"])

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_PERIOD_OVERLAP_DETAIL}


# ========== 結合テストNo.8 ==========
# 異常系 - 同一備品について貸出中の申請と期間が重複する場合
def test_create_loan_request_endpoint_008_overlap_with_on_loan_request_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-08")
    equipment = _register_equipment(client, admin_token, "LNCR-08")
    _create_loan_request_on_loan(client, admin_token, general_token, equipment["equipment_id"])

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_PERIOD_OVERLAP_DETAIL}


# ========== 結合テストNo.9 ==========
# 正常系 - 同一備品について申請中の申請と期間が重複する場合でも登録できること（申請中同士の重複は許可）
def test_create_loan_request_endpoint_009_overlap_with_pending_request_is_allowed(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-09")
    equipment = _register_equipment(client, admin_token, "LNCR-09")
    _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "申請中"


# ========== 結合テストNo.10 ==========
# 異常系 - 用途が空文字の場合
def test_create_loan_request_endpoint_010_empty_purpose_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-10")
    equipment = _register_equipment(client, admin_token, "LNCR-10")

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "",
        },
    )

    assert response.status_code == 422


# ========== 結合テストNo.11 ==========
# 異常系 - 用途が201文字の場合
def test_create_loan_request_endpoint_011_purpose_too_long_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-11")
    equipment = _register_equipment(client, admin_token, "LNCR-11")

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "あ" * 201,
        },
    )

    assert response.status_code == 422


# ========== 結合テストNo.12 ==========
# 異常系 - equipment_idに数値以外の文字列を指定した場合
def test_create_loan_request_endpoint_012_non_numeric_equipment_id_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-12")

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": "abc",
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 422


# ========== 結合テストNo.13 ==========
# 異常系 - 必須パラメータ（equipment_id）が欠落している場合
def test_create_loan_request_endpoint_013_missing_equipment_id_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-create-user-13")

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 422


# ========== 結合テストNo.14 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_create_loan_request_endpoint_014_missing_authorization_header_returns_401(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "LNCR-14")

    response = client.post(
        "/loan-requests",
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 401


# ========== 結合テストNo.15 ==========
# 異常系 - 初回パスワード変更が完了していないユーザーが呼び出した場合
def test_create_loan_request_endpoint_015_password_change_not_completed_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "LNCR-15")
    _register_user(client, admin_token, "loan-create-user-15")
    token = _login_and_get_token(client, "loan-create-user-15", "initial-password-01")

    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "資料作成のため",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 貸出申請取消
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：cancel_loan_request_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出申請・承認/貸出申請取消_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 申請中の自分の申請を取消理由付きで取消できること
def test_cancel_loan_request_endpoint_001_cancels_pending_request_with_reason(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-cancel-user-01")
    equipment = _register_equipment(client, admin_token, "LNCX-01")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/cancel",
        headers={"Authorization": f"Bearer {general_token}"},
        json={"reason": "都合により不要になったため"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "取消"
    assert body["reject_cancel_reason"] == "都合により不要になったため"
    assert body["cancelled_by_user_id"] == _get_user_internal_id_from_db("loan-cancel-user-01")


# ========== 結合テストNo.2 ==========
# 正常系 - 承認済みの自分の申請を取消理由なし（未指定）で取消できること
def test_cancel_loan_request_endpoint_002_cancels_approved_request_without_reason(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-cancel-user-02")
    equipment = _register_equipment(client, admin_token, "LNCX-02")
    approved = _create_approved_loan_request(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/cancel",
        headers={"Authorization": f"Bearer {general_token}"},
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "取消"
    assert body["reject_cancel_reason"] == ""
    assert body["cancelled_by_user_id"] == _get_user_internal_id_from_db("loan-cancel-user-02")


# ========== 結合テストNo.3 ==========
# 異常系 - 存在しない貸出申請IDを指定した場合
def test_cancel_loan_request_endpoint_003_nonexistent_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-cancel-user-03")

    response = client.patch(
        "/loan-requests/999999/cancel",
        headers={"Authorization": f"Bearer {general_token}"},
        json={"reason": "不要になったため"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_LOAN_REQUEST_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 他人の申請を指定した場合、対象が存在しない場合と同じエラーになること
def test_cancel_loan_request_endpoint_004_other_users_request_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    applicant_token = _get_general_user_token(client, admin_token, "loan-cancel-user-04-a")
    other_token = _get_general_user_token(client, admin_token, "loan-cancel-user-04-b")
    equipment = _register_equipment(client, admin_token, "LNCX-04")
    created = _create_loan_request(client, applicant_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/cancel",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"reason": "不要になったため"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_LOAN_REQUEST_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - 却下済みの申請を取消しようとした場合
def test_cancel_loan_request_endpoint_005_rejected_request_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-cancel-user-05")
    equipment = _register_equipment(client, admin_token, "LNCX-05")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _reject_loan_request(client, admin_token, created["loan_request_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/cancel",
        headers={"Authorization": f"Bearer {general_token}"},
        json={"reason": "不要になったため"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_CANNOT_CANCEL_DETAIL}


# ========== 結合テストNo.6 ==========
# 異常系 - 貸出中の申請を取消しようとした場合
def test_cancel_loan_request_endpoint_006_on_loan_request_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-cancel-user-06")
    equipment = _register_equipment(client, admin_token, "LNCX-06")
    on_loan = _create_loan_request_on_loan(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{on_loan['loan_request_id']}/cancel",
        headers={"Authorization": f"Bearer {general_token}"},
        json={"reason": "不要になったため"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_CANNOT_CANCEL_DETAIL}


# ========== 結合テストNo.7 ==========
# 異常系 - 取消理由が201文字の場合
def test_cancel_loan_request_endpoint_007_reason_too_long_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-cancel-user-07")
    equipment = _register_equipment(client, admin_token, "LNCX-07")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/cancel",
        headers={"Authorization": f"Bearer {general_token}"},
        json={"reason": "あ" * 201},
    )

    assert response.status_code == 422


# ========== 結合テストNo.8 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_cancel_loan_request_endpoint_008_missing_authorization_header_returns_401(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-cancel-user-08")
    equipment = _register_equipment(client, admin_token, "LNCX-08")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/cancel",
        json={"reason": "不要になったため"},
    )

    assert response.status_code == 401


# ========== 結合テストNo.9 ==========
# 異常系 - 初回パスワード変更が完了していないユーザーが呼び出した場合
def test_cancel_loan_request_endpoint_009_password_change_not_completed_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "LNCX-09")
    general_token = _get_general_user_token(client, admin_token, "loan-cancel-user-09-setup")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _register_user(client, admin_token, "loan-cancel-user-09")
    token = _login_and_get_token(client, "loan-cancel-user-09", "initial-password-01")

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/cancel",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "不要になったため"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 貸出申請一覧取得
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：get_loan_requests_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出申請・承認/貸出申請一覧取得_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - scope未指定（デフォルトmine）の場合、自分の申請のみ返却されること（他ユーザーの申請は含まれないこと）
def test_get_loan_requests_endpoint_001_default_scope_mine_excludes_other_users(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    token_a = _get_general_user_token(client, admin_token, "loan-list-user-01-a")
    token_b = _get_general_user_token(client, admin_token, "loan-list-user-01-b")
    equipment_a = _register_equipment(client, admin_token, "LNLS-01-A")
    equipment_b = _register_equipment(client, admin_token, "LNLS-01-B")
    request_a = _create_loan_request(client, token_a, equipment_a["equipment_id"])
    _create_loan_request(client, token_b, equipment_b["equipment_id"])

    response = client.get("/loan-requests", headers={"Authorization": f"Bearer {token_a}"})

    assert response.status_code == 200
    loan_request_id_list = [loan_request["loan_request_id"] for loan_request in response.json()]
    assert loan_request_id_list == [request_a["loan_request_id"]]


# ========== 結合テストNo.2 ==========
# 正常系 - scope=mine・statusを指定して絞り込めること
def test_get_loan_requests_endpoint_002_scope_mine_with_status_filter(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-list-user-02")
    equipment_pending = _register_equipment(client, admin_token, "LNLS-02-A")
    equipment_rejected = _register_equipment(client, admin_token, "LNLS-02-B")
    pending = _create_loan_request(client, general_token, equipment_pending["equipment_id"])
    rejected_source = _create_loan_request(client, general_token, equipment_rejected["equipment_id"])
    _reject_loan_request(client, admin_token, rejected_source["loan_request_id"])

    response = client.get(
        "/loan-requests?scope=mine&status=申請中", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 200
    loan_request_id_list = [loan_request["loan_request_id"] for loan_request in response.json()]
    assert loan_request_id_list == [pending["loan_request_id"]]


# ========== 結合テストNo.3 ==========
# 正常系 - 管理者がscope=allを指定した場合、全ユーザーの申請が返却されること
def test_get_loan_requests_endpoint_003_admin_scope_all_returns_all_users_requests(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    token_a = _get_general_user_token(client, admin_token, "loan-list-user-03-a")
    token_b = _get_general_user_token(client, admin_token, "loan-list-user-03-b")
    equipment_a = _register_equipment(client, admin_token, "LNLS-03-A")
    equipment_b = _register_equipment(client, admin_token, "LNLS-03-B")
    request_a = _create_loan_request(client, token_a, equipment_a["equipment_id"])
    request_b = _create_loan_request(client, token_b, equipment_b["equipment_id"])

    response = client.get("/loan-requests?scope=all", headers={"Authorization": f"Bearer {admin_token}"})

    assert response.status_code == 200
    loan_request_id_list = {loan_request["loan_request_id"] for loan_request in response.json()}
    assert request_a["loan_request_id"] in loan_request_id_list
    assert request_b["loan_request_id"] in loan_request_id_list


# ========== 結合テストNo.4 ==========
# 正常系 - 管理者がscope=overdueを指定した場合、返却予定日を過ぎた貸出中の申請のみ返却されること（status指定は無視されること）
def test_get_loan_requests_endpoint_004_admin_scope_overdue_ignores_status_param(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-list-user-04")
    overdue_equipment = _register_equipment(client, admin_token, "LNLS-04-A")
    on_time_equipment = _register_equipment(client, admin_token, "LNLS-04-B")
    overdue_request = _create_loan_request_on_loan(
        client, admin_token, general_token, overdue_equipment["equipment_id"]
    )
    on_time_request = _create_loan_request_on_loan(
        client, admin_token, general_token, on_time_equipment["equipment_id"]
    )
    _set_loan_request_due_date_in_db(overdue_request["loan_request_id"], dt.date.fromisoformat(_date_iso(-1)))

    response = client.get(
        "/loan-requests?scope=overdue&status=申請中", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    loan_request_id_list = [loan_request["loan_request_id"] for loan_request in response.json()]
    assert loan_request_id_list == [overdue_request["loan_request_id"]]
    assert on_time_request["loan_request_id"] not in loan_request_id_list


# ========== 結合テストNo.5 ==========
# 異常系 - 一般ユーザーがscope=allを指定した場合
def test_get_loan_requests_endpoint_005_general_user_scope_all_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-list-user-05")

    response = client.get("/loan-requests?scope=all", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_SCOPE_DETAIL}


# ========== 結合テストNo.6 ==========
# 異常系 - 一般ユーザーがscope=overdueを指定した場合
def test_get_loan_requests_endpoint_006_general_user_scope_overdue_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-list-user-06")

    response = client.get("/loan-requests?scope=overdue", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_SCOPE_DETAIL}


# ========== 結合テストNo.7 ==========
# 異常系 - scopeに許可されていない値を指定した場合
def test_get_loan_requests_endpoint_007_invalid_scope_value_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-list-user-07")

    response = client.get(
        "/loan-requests?scope=invalid", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 422


# ========== 結合テストNo.8 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_get_loan_requests_endpoint_008_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.get("/loan-requests")

    assert response.status_code == 401


# ========== 結合テストNo.9 ==========
# 異常系 - 初回パスワード変更が完了していないユーザーが呼び出した場合
def test_get_loan_requests_endpoint_009_password_change_not_completed_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "loan-list-user-09")
    token = _login_and_get_token(client, "loan-list-user-09", "initial-password-01")

    response = client.get("/loan-requests", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 貸出申請詳細取得
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：get_loan_request_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出申請・承認/貸出申請詳細取得_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 自分の申請の詳細を取得できること
def test_get_loan_request_endpoint_001_returns_own_request_detail(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-detail-user-01")
    equipment = _register_equipment(client, admin_token, "LNDT-01")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.get(
        f"/loan-requests/{created['loan_request_id']}", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["loan_request_id"] == created["loan_request_id"]
    assert body["applicant_user_id"] == _get_user_internal_id_from_db("loan-detail-user-01")


# ========== 結合テストNo.2 ==========
# 正常系 - 管理者が他ユーザーの申請の詳細を取得できること
def test_get_loan_request_endpoint_002_admin_can_view_other_users_request_detail(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-detail-user-02")
    equipment = _register_equipment(client, admin_token, "LNDT-02")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.get(
        f"/loan-requests/{created['loan_request_id']}", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["loan_request_id"] == created["loan_request_id"]
    assert body["applicant_user_id"] == _get_user_internal_id_from_db("loan-detail-user-02")


# ========== 結合テストNo.3 ==========
# 異常系 - 存在しない貸出申請IDを指定した場合
def test_get_loan_request_endpoint_003_nonexistent_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-detail-user-03")

    response = client.get("/loan-requests/999999", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_LOAN_REQUEST_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 一般ユーザーが他人の申請を取得しようとした場合、対象が存在しない場合と同じエラーになること
def test_get_loan_request_endpoint_004_general_user_other_users_request_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    applicant_token = _get_general_user_token(client, admin_token, "loan-detail-user-04-a")
    other_token = _get_general_user_token(client, admin_token, "loan-detail-user-04-b")
    equipment = _register_equipment(client, admin_token, "LNDT-04")
    created = _create_loan_request(client, applicant_token, equipment["equipment_id"])

    response = client.get(
        f"/loan-requests/{created['loan_request_id']}", headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_LOAN_REQUEST_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - 貸出申請IDが数値でない場合
def test_get_loan_request_endpoint_005_non_numeric_id_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-detail-user-05")

    response = client.get("/loan-requests/abc", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 422


# ========== 結合テストNo.6 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_get_loan_request_endpoint_006_missing_authorization_header_returns_401(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-detail-user-06")
    equipment = _register_equipment(client, admin_token, "LNDT-06")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.get(f"/loan-requests/{created['loan_request_id']}")

    assert response.status_code == 401


# ========== 結合テストNo.7 ==========
# 異常系 - 初回パスワード変更が完了していないユーザーが呼び出した場合
def test_get_loan_request_endpoint_007_password_change_not_completed_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    equipment = _register_equipment(client, admin_token, "LNDT-07")
    _register_user(client, admin_token, "loan-detail-user-07", initial_password="initial-password-01")
    token = _login_and_get_token(client, "loan-detail-user-07", "initial-password-01")
    created_response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "資料作成のため",
        },
    )
    assert created_response.status_code == 403

    response = client.get(
        f"/loan-requests/{equipment['equipment_id']}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 貸出申請承認
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：approve_loan_request_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出申請・承認/貸出申請承認_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 開始日が翌日の申請中の申請を承認できること
def test_approve_loan_request_endpoint_001_approves_pending_request_with_future_start_date(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-approve-user-01")
    equipment = _register_equipment(client, admin_token, "LNAP-01")
    created = _create_loan_request(
        client, general_token, equipment["equipment_id"], start_date=_date_iso(1), due_date=_date_iso(2)
    )

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "承認済み"
    assert body["reject_cancel_reason"] == ""
    assert body["approved_rejected_by_user_id"] == _get_user_internal_id_from_db(_ADMIN_USER_ID)


# ========== 結合テストNo.2 ==========
# 正常系 - 開始日が今日の申請を承認できること（境界値）
def test_approve_loan_request_endpoint_002_approves_request_with_today_start_date(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-approve-user-02")
    equipment = _register_equipment(client, admin_token, "LNAP-02")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "承認済み"


# ========== 結合テストNo.3 ==========
# 異常系 - 存在しない貸出申請IDを指定した場合
def test_approve_loan_request_endpoint_003_nonexistent_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.patch(
        "/loan-requests/999999/approve", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_LOAN_REQUEST_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - すでに承認済みの申請を承認しようとした場合
def test_approve_loan_request_endpoint_004_already_approved_request_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-approve-user-04")
    equipment = _register_equipment(client, admin_token, "LNAP-04")
    approved = _create_approved_loan_request(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_CANNOT_APPROVE_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - 開始日が前日（過去日）の申請を承認しようとした場合
def test_approve_loan_request_endpoint_005_past_start_date_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-approve-user-05")
    equipment = _register_equipment(client, admin_token, "LNAP-05")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _set_loan_request_start_date_in_db(created["loan_request_id"], dt.date.fromisoformat(_date_iso(-1)))

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_APPROVE_PAST_START_DATE_DETAIL}


# ========== 結合テストNo.6 ==========
# 異常系 - 同一備品について承認済みの他の申請と期間が重複する場合
def test_approve_loan_request_endpoint_006_overlap_with_approved_request_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-approve-user-06")
    equipment = _register_equipment(client, admin_token, "LNAP-06")
    first_request = _create_loan_request(client, general_token, equipment["equipment_id"])
    second_request = _create_loan_request(client, general_token, equipment["equipment_id"])
    _approve_loan_request(client, admin_token, first_request["loan_request_id"])

    response = client.patch(
        f"/loan-requests/{second_request['loan_request_id']}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_PERIOD_OVERLAP_DETAIL}


# ========== 結合テストNo.7 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_approve_loan_request_endpoint_007_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-approve-user-07")
    equipment = _register_equipment(client, admin_token, "LNAP-07")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/approve",
        headers={"Authorization": f"Bearer {general_token}"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.8 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_approve_loan_request_endpoint_008_missing_authorization_header_returns_401(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-approve-user-08")
    equipment = _register_equipment(client, admin_token, "LNAP-08")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(f"/loan-requests/{created['loan_request_id']}/approve")

    assert response.status_code == 401


# ========== 結合テストNo.9 ==========
# 異常系 - 初回パスワード変更が完了していない管理者が呼び出した場合
def test_approve_loan_request_endpoint_009_password_change_not_completed_admin_returns_403(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-approve-user-09")
    equipment = _register_equipment(client, admin_token, "LNAP-09")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _register_user(client, admin_token, "loan-approve-new-admin-09", role="管理者")
    token = _login_and_get_token(client, "loan-approve-new-admin-09", "initial-password-01")

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/approve",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 貸出申請却下
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：reject_loan_request_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出申請・承認/貸出申請却下_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 申請中の申請を却下理由付きで却下できること
def test_reject_loan_request_endpoint_001_rejects_pending_request_with_reason(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-reject-user-01")
    equipment = _register_equipment(client, admin_token, "LNRJ-01")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "備品の点検予定と重複するため"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "却下"
    assert body["reject_cancel_reason"] == "備品の点検予定と重複するため"
    assert body["approved_rejected_by_user_id"] == _get_user_internal_id_from_db(_ADMIN_USER_ID)


# ========== 結合テストNo.2 ==========
# 異常系 - 存在しない貸出申請IDを指定した場合
def test_reject_loan_request_endpoint_002_nonexistent_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.patch(
        "/loan-requests/999999/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "備品の点検予定と重複するため"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_LOAN_REQUEST_DETAIL}


# ========== 結合テストNo.3 ==========
# 異常系 - すでに承認済みの申請を却下しようとした場合
def test_reject_loan_request_endpoint_003_already_approved_request_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-reject-user-03")
    equipment = _register_equipment(client, admin_token, "LNRJ-03")
    approved = _create_approved_loan_request(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "備品の点検予定と重複するため"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_CANNOT_REJECT_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 却下理由が空文字の場合
def test_reject_loan_request_endpoint_004_empty_reason_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-reject-user-04")
    equipment = _register_equipment(client, admin_token, "LNRJ-04")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": ""},
    )

    assert response.status_code == 422


# ========== 結合テストNo.5 ==========
# 異常系 - 却下理由が201文字の場合
def test_reject_loan_request_endpoint_005_reason_too_long_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-reject-user-05")
    equipment = _register_equipment(client, admin_token, "LNRJ-05")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "あ" * 201},
    )

    assert response.status_code == 422


# ========== 結合テストNo.6 ==========
# 異常系 - 必須パラメータ（reason）が欠落している場合
def test_reject_loan_request_endpoint_006_missing_reason_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-reject-user-06")
    equipment = _register_equipment(client, admin_token, "LNRJ-06")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={},
    )

    assert response.status_code == 422


# ========== 結合テストNo.7 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_reject_loan_request_endpoint_007_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-reject-user-07")
    equipment = _register_equipment(client, admin_token, "LNRJ-07")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/reject",
        headers={"Authorization": f"Bearer {general_token}"},
        json={"reason": "備品の点検予定と重複するため"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.8 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_reject_loan_request_endpoint_008_missing_authorization_header_returns_401(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-reject-user-08")
    equipment = _register_equipment(client, admin_token, "LNRJ-08")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/reject",
        json={"reason": "備品の点検予定と重複するため"},
    )

    assert response.status_code == 401


# ========== 結合テストNo.9 ==========
# 異常系 - 初回パスワード変更が完了していない管理者が呼び出した場合
def test_reject_loan_request_endpoint_009_password_change_not_completed_admin_returns_403(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-reject-user-09")
    equipment = _register_equipment(client, admin_token, "LNRJ-09")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _register_user(client, admin_token, "loan-reject-new-admin-09", role="管理者")
    token = _login_and_get_token(client, "loan-reject-new-admin-09", "initial-password-01")

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/reject",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "備品の点検予定と重複するため"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 貸出申請管理者取消
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：admin_cancel_loan_request_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出申請・承認/貸出申請管理者取消_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 承認済みの申請を取消理由付きで取消できること
def test_admin_cancel_loan_request_endpoint_001_cancels_approved_request_with_reason(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-admincancel-user-01")
    equipment = _register_equipment(client, admin_token, "LNAC-01")
    approved = _create_approved_loan_request(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/admin-cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "備品の故障が判明したため"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "取消"
    assert body["reject_cancel_reason"] == "備品の故障が判明したため"
    assert body["cancelled_by_user_id"] == _get_user_internal_id_from_db(_ADMIN_USER_ID)


# ========== 結合テストNo.2 ==========
# 異常系 - 存在しない貸出申請IDを指定した場合
def test_admin_cancel_loan_request_endpoint_002_nonexistent_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.patch(
        "/loan-requests/999999/admin-cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "備品の故障が判明したため"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_LOAN_REQUEST_DETAIL}


# ========== 結合テストNo.3 ==========
# 異常系 - 申請中の申請を取消しようとした場合
def test_admin_cancel_loan_request_endpoint_003_pending_request_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-admincancel-user-03")
    equipment = _register_equipment(client, admin_token, "LNAC-03")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/admin-cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "備品の故障が判明したため"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_CANNOT_CANCEL_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 取消理由が空文字の場合
def test_admin_cancel_loan_request_endpoint_004_empty_reason_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-admincancel-user-04")
    equipment = _register_equipment(client, admin_token, "LNAC-04")
    approved = _create_approved_loan_request(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/admin-cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": ""},
    )

    assert response.status_code == 422


# ========== 結合テストNo.5 ==========
# 異常系 - 必須パラメータ（reason）が欠落している場合
def test_admin_cancel_loan_request_endpoint_005_missing_reason_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-admincancel-user-05")
    equipment = _register_equipment(client, admin_token, "LNAC-05")
    approved = _create_approved_loan_request(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/admin-cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={},
    )

    assert response.status_code == 422


# ========== 結合テストNo.6 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_admin_cancel_loan_request_endpoint_006_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-admincancel-user-06")
    equipment = _register_equipment(client, admin_token, "LNAC-06")
    approved = _create_approved_loan_request(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/admin-cancel",
        headers={"Authorization": f"Bearer {general_token}"},
        json={"reason": "備品の故障が判明したため"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.7 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_admin_cancel_loan_request_endpoint_007_missing_authorization_header_returns_401(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-admincancel-user-07")
    equipment = _register_equipment(client, admin_token, "LNAC-07")
    approved = _create_approved_loan_request(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/admin-cancel",
        json={"reason": "備品の故障が判明したため"},
    )

    assert response.status_code == 401


# ========== 結合テストNo.8 ==========
# 異常系 - 初回パスワード変更が完了していない管理者が呼び出した場合
def test_admin_cancel_loan_request_endpoint_008_password_change_not_completed_admin_returns_403(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-admincancel-user-08")
    equipment = _register_equipment(client, admin_token, "LNAC-08")
    approved = _create_approved_loan_request(client, admin_token, general_token, equipment["equipment_id"])
    _register_user(client, admin_token, "loan-admincancel-new-admin-08", role="管理者")
    token = _login_and_get_token(client, "loan-admincancel-new-admin-08", "initial-password-01")

    response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/admin-cancel",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "備品の故障が判明したため"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 通知一覧取得
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：get_notifications_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出申請・承認/通知一覧取得_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 自分宛の通知が作成日時の降順で返却されること
def test_get_notifications_endpoint_001_returns_own_notifications_in_descending_order(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "notif-list-user-01")
    equipment_rejected = _register_equipment(client, admin_token, "NTLS-01-A")
    equipment_approved = _register_equipment(client, admin_token, "NTLS-01-B")
    rejected_source = _create_loan_request(client, general_token, equipment_rejected["equipment_id"])
    _reject_loan_request(client, admin_token, rejected_source["loan_request_id"])
    approved_source = _create_loan_request(client, general_token, equipment_approved["equipment_id"])
    _approve_loan_request(client, admin_token, approved_source["loan_request_id"])

    response = client.get("/notifications", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["notification_type"] == "承認"
    assert body[0]["loan_request_id"] == approved_source["loan_request_id"]
    assert body[1]["notification_type"] == "却下"
    assert body[1]["loan_request_id"] == rejected_source["loan_request_id"]
    first_created_at = dt.datetime.fromisoformat(body[0]["created_at"])
    second_created_at = dt.datetime.fromisoformat(body[1]["created_at"])
    assert first_created_at >= second_created_at


# ========== 結合テストNo.2 ==========
# 正常系 - 自分宛の通知が存在しない場合、空リストが返却されること
def test_get_notifications_endpoint_002_returns_empty_list_when_no_notifications(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "notif-list-user-02")

    response = client.get("/notifications", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 200
    assert response.json() == []


# ========== 結合テストNo.3 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_get_notifications_endpoint_003_missing_authorization_header_returns_401(client: TestClient) -> None:
    response = client.get("/notifications")

    assert response.status_code == 401


# ========== 結合テストNo.4 ==========
# 異常系 - 初回パスワード変更が完了していないユーザーが呼び出した場合
def test_get_notifications_endpoint_004_password_change_not_completed_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "notif-list-user-04")
    token = _login_and_get_token(client, "notif-list-user-04", "initial-password-01")

    response = client.get("/notifications", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 通知既読化
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：mark_notification_as_read_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出申請・承認/通知既読化_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 自分宛の未読通知を既読化できること
def test_mark_notification_as_read_endpoint_001_marks_unread_notification_as_read(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "notif-read-user-01")
    equipment = _register_equipment(client, admin_token, "NTRD-01")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _approve_loan_request(client, admin_token, created["loan_request_id"])
    notification_list = client.get("/notifications", headers={"Authorization": f"Bearer {general_token}"}).json()
    notification_id = notification_list[0]["notification_id"]

    response = client.patch(
        f"/notifications/{notification_id}/read", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["notification_id"] == notification_id
    assert body["read_flag"] is True


# ========== 結合テストNo.2 ==========
# 正常系 - 既読済みの通知を再度既読化しても成功すること
def test_mark_notification_as_read_endpoint_002_marking_already_read_notification_succeeds(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "notif-read-user-02")
    equipment = _register_equipment(client, admin_token, "NTRD-02")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _approve_loan_request(client, admin_token, created["loan_request_id"])
    notification_list = client.get("/notifications", headers={"Authorization": f"Bearer {general_token}"}).json()
    notification_id = notification_list[0]["notification_id"]
    first_response = client.patch(
        f"/notifications/{notification_id}/read", headers={"Authorization": f"Bearer {general_token}"}
    )
    assert first_response.status_code == 200

    response = client.patch(
        f"/notifications/{notification_id}/read", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["notification_id"] == notification_id
    assert body["read_flag"] is True


# ========== 結合テストNo.3 ==========
# 異常系 - 存在しない通知IDを指定した場合
def test_mark_notification_as_read_endpoint_003_nonexistent_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "notif-read-user-03")

    response = client.patch(
        "/notifications/999999/read", headers={"Authorization": f"Bearer {general_token}"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_NOTIFICATION_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 他人宛の通知を指定した場合、対象が存在しない場合と同じエラーになること
def test_mark_notification_as_read_endpoint_004_other_users_notification_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    recipient_token = _get_general_user_token(client, admin_token, "notif-read-user-04-a")
    other_token = _get_general_user_token(client, admin_token, "notif-read-user-04-b")
    equipment = _register_equipment(client, admin_token, "NTRD-04")
    created = _create_loan_request(client, recipient_token, equipment["equipment_id"])
    _approve_loan_request(client, admin_token, created["loan_request_id"])
    notification_list = client.get(
        "/notifications", headers={"Authorization": f"Bearer {recipient_token}"}
    ).json()
    notification_id = notification_list[0]["notification_id"]

    response = client.patch(
        f"/notifications/{notification_id}/read", headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_NOTIFICATION_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_mark_notification_as_read_endpoint_005_missing_authorization_header_returns_401(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "notif-read-user-05")
    equipment = _register_equipment(client, admin_token, "NTRD-05")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _approve_loan_request(client, admin_token, created["loan_request_id"])
    notification_list = client.get("/notifications", headers={"Authorization": f"Bearer {general_token}"}).json()
    notification_id = notification_list[0]["notification_id"]

    response = client.patch(f"/notifications/{notification_id}/read")

    assert response.status_code == 401


# ========== 結合テストNo.6 ==========
# 異常系 - 初回パスワード変更が完了していないユーザーが呼び出した場合
def test_mark_notification_as_read_endpoint_006_password_change_not_completed_returns_403(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "notif-read-user-06-setup")
    equipment = _register_equipment(client, admin_token, "NTRD-06")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _approve_loan_request(client, admin_token, created["loan_request_id"])
    notification_list = client.get("/notifications", headers={"Authorization": f"Bearer {general_token}"}).json()
    notification_id = notification_list[0]["notification_id"]
    _register_user(client, admin_token, "notif-read-user-06")
    token = _login_and_get_token(client, "notif-read-user-06", "initial-password-01")

    response = client.patch(
        f"/notifications/{notification_id}/read", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}
