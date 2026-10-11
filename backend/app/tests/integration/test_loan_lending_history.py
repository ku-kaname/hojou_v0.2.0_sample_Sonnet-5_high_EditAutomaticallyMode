import csv
import datetime as dt
import io

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import LoanRequest, User

_ADMIN_USER_ID = "admin"
_ADMIN_INITIAL_PASSWORD = "integration-test-admin-password"
_FORBIDDEN_ADMIN_REQUIRED_DETAIL = "この操作には管理者権限が必要です。"
_FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL = "初回パスワード変更が完了していません。パスワードを変更してください。"
_NOT_FOUND_LOAN_REQUEST_DETAIL = "指定された貸出申請が見つかりません。"
_CONFLICT_CANNOT_LEND_DETAIL = "この申請は現在の状態では貸出処理できません。"
_CONFLICT_LEND_FUTURE_START_DATE_DETAIL = "開始日前のため、この申請は貸出処理できません。"
_CONFLICT_EQUIPMENT_INACTIVE_FOR_LEND_DETAIL = "指定された備品は無効化されているため、貸出処理できません。"
_CONFLICT_LEND_OVERLAP_DETAIL = "同一備品について、貸出中の別申請が存在するため貸出処理できません。"
_CONFLICT_CANNOT_RETURN_DETAIL = "この申請は現在の状態では返却処理できません。"

_CSV_HEADER = [
    "loan_request_id",
    "equipment_id",
    "applicant_user_id",
    "start_date",
    "due_date",
    "purpose",
    "status",
    "reject_cancel_reason",
    "approved_rejected_by_user_id",
    "lent_by_user_id",
    "returned_by_user_id",
    "cancelled_by_user_id",
    "requested_at",
    "approved_rejected_at",
    "lent_at",
    "returned_at",
    "cancelled_at",
    "return_note",
]


def _login_and_get_token(client: TestClient, user_id: str, password: str) -> str:
    """指定ユーザーでログインし、アクセストークンを取得する（各テストケースの前提条件整備用）"""
    response = client.post("/token", data={"username": user_id, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _get_password_changed_admin_token(client: TestClient) -> str:
    """初期管理者のパスワードを変更済みの状態にし、新しいアクセストークンを取得する

    管理者権限系のエンドポイントはrequire_password_changedがrequire_adminより先に評価されるため、
    貸出・返却・履歴のテストでは事前にパスワード変更を済ませておく必要がある。
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
    """DB上の貸出申請の開始日を直接更新する（承認済みのまま開始日を過去日にする前提条件整備用。
    API経由では承認時に開始日が過去日だと拒否されるため、承認後にDBを直接更新してテスト条件を作る）"""
    db = SessionLocal()
    try:
        target_loan_request = db.query(LoanRequest).filter(LoanRequest.id == loan_request_id).one()
        target_loan_request.start_date = start_date
        db.commit()
    finally:
        db.close()


def _set_loan_request_status_in_db(loan_request_id: int, status_value: str) -> None:
    """DB上の貸出申請の状態を直接更新する

    承認処理自体が重複チェックで拒否するため、API経由では作れない「同一備品について
    承認済み・貸出中の申請が重複する」前提条件を、DBを直接更新して作る）"""
    db = SessionLocal()
    try:
        target_loan_request = db.query(LoanRequest).filter(LoanRequest.id == loan_request_id).one()
        target_loan_request.status = status_value
        db.commit()
    finally:
        db.close()


def _date_iso(offset_days: int) -> str:
    """サーバー側の「今日」（UTC基準）から指定日数だけずらした日付をISO8601形式の文字列で取得する

    開始日の判定はUTCの日付で行われるため（services.py参照）、
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


def _lend_loan_request(client: TestClient, admin_token: str, loan_request_id: int) -> dict:
    """承認済みの貸出申請に対して貸出処理を行う（「貸出中」状態の前提条件整備用）"""
    response = client.patch(
        f"/loan-requests/{loan_request_id}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    return response.json()


def _create_loan_request_on_loan(
    client: TestClient, admin_token: str, general_token: str, equipment_id: int
) -> dict:
    """申請中の貸出申請を登録し、承認→貸出処理を行って「貸出中」の状態にする（「貸出中」状態の前提条件整備用）

    貸出処理（lend_loan_request）は開始日が今日より後の場合エラーとなるため、開始日は必ず今日とする。
    """
    created = _create_loan_request(
        client, general_token, equipment_id, start_date=_date_iso(0), due_date=_date_iso(7)
    )
    _approve_loan_request(client, admin_token, created["loan_request_id"])
    return _lend_loan_request(client, admin_token, created["loan_request_id"])


def _parse_csv_rows(response) -> list[list[str]]:
    """CSVレスポンス（UTF-8 BOM付き）をデコードし、行ごとのセル値リストとして取得する（テスト結果検証用）"""
    decoded_text = response.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(decoded_text)))


# ==================================================
# 貸出処理
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：lend_loan_request_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出・返却・履歴/貸出処理_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 開始日が今日の承認済み申請を貸出処理できること（境界値）
def test_lend_loan_request_endpoint_001_lends_approved_request_with_today_start_date(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-lend-user-01")
    equipment = _register_equipment(client, admin_token, "LNLD-01")
    created = _create_loan_request(
        client, general_token, equipment["equipment_id"], start_date=_date_iso(0), due_date=_date_iso(1)
    )
    _approve_loan_request(client, admin_token, created["loan_request_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "貸出中"
    assert body["lent_by_user_id"] == _get_user_internal_id_from_db(_ADMIN_USER_ID)


# ========== 結合テストNo.2 ==========
# 正常系 - 開始日が前日（過去日）の承認済み申請を貸出処理できること
def test_lend_loan_request_endpoint_002_lends_approved_request_with_past_start_date(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-lend-user-02")
    equipment = _register_equipment(client, admin_token, "LNLD-02")
    created = _create_loan_request(
        client, general_token, equipment["equipment_id"], start_date=_date_iso(0), due_date=_date_iso(1)
    )
    _approve_loan_request(client, admin_token, created["loan_request_id"])
    _set_loan_request_start_date_in_db(created["loan_request_id"], dt.date.fromisoformat(_date_iso(-1)))

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "貸出中"


# ========== 結合テストNo.3 ==========
# 異常系 - 存在しない貸出申請IDを指定した場合
def test_lend_loan_request_endpoint_003_nonexistent_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.patch(
        "/loan-requests/999999/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_LOAN_REQUEST_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 状態が「承認済み」でない申請（申請中）を貸出処理しようとした場合
def test_lend_loan_request_endpoint_004_pending_request_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-lend-user-04")
    equipment = _register_equipment(client, admin_token, "LNLD-04")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_CANNOT_LEND_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - 開始日が翌日（未来）の承認済み申請を貸出処理しようとした場合
def test_lend_loan_request_endpoint_005_future_start_date_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-lend-user-05")
    equipment = _register_equipment(client, admin_token, "LNLD-05")
    created = _create_loan_request(
        client, general_token, equipment["equipment_id"], start_date=_date_iso(1), due_date=_date_iso(2)
    )
    _approve_loan_request(client, admin_token, created["loan_request_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_LEND_FUTURE_START_DATE_DETAIL}


# ========== 結合テストNo.6 ==========
# 異常系 - 対象備品が無効化されている場合
def test_lend_loan_request_endpoint_006_inactive_equipment_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-lend-user-06")
    equipment = _register_equipment(client, admin_token, "LNLD-06")
    created = _create_loan_request(
        client, general_token, equipment["equipment_id"], start_date=_date_iso(0), due_date=_date_iso(1)
    )
    _approve_loan_request(client, admin_token, created["loan_request_id"])
    deactivate_response = client.patch(
        f"/equipment/{equipment['equipment_id']}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate_response.status_code == 200

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_EQUIPMENT_INACTIVE_FOR_LEND_DETAIL}


# ========== 結合テストNo.7 ==========
# 異常系 - 同一備品について、貸出中の別申請が存在する場合
def test_lend_loan_request_endpoint_007_overlap_with_on_loan_request_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-lend-user-07")
    equipment = _register_equipment(client, admin_token, "LNLD-07")
    start_date = _date_iso(0)
    due_date = _date_iso(7)
    # 両方とも「申請中」同士の期間重複は許可されているため、先に2件とも登録する
    on_loan_source = _create_loan_request(
        client, general_token, equipment["equipment_id"], start_date=start_date, due_date=due_date
    )
    overlapping_source = _create_loan_request(
        client, general_token, equipment["equipment_id"], start_date=start_date, due_date=due_date
    )
    _approve_loan_request(client, admin_token, on_loan_source["loan_request_id"])
    _lend_loan_request(client, admin_token, on_loan_source["loan_request_id"])
    # もう一方は、承認処理（approve）自体が重複チェックで拒否するため、
    # DBを直接更新して「承認済み」状態を作る（承認済み・貸出中が重複する前提条件整備用）
    _set_loan_request_status_in_db(overlapping_source["loan_request_id"], "承認済み")

    response = client.patch(
        f"/loan-requests/{overlapping_source['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_LEND_OVERLAP_DETAIL}


# ========== 結合テストNo.8 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_lend_loan_request_endpoint_008_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-lend-user-08")
    equipment = _register_equipment(client, admin_token, "LNLD-08")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _approve_loan_request(client, admin_token, created["loan_request_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {general_token}"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.9 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_lend_loan_request_endpoint_009_missing_authorization_header_returns_401(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-lend-user-09")
    equipment = _register_equipment(client, admin_token, "LNLD-09")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _approve_loan_request(client, admin_token, created["loan_request_id"])

    response = client.patch(f"/loan-requests/{created['loan_request_id']}/lend")

    assert response.status_code == 401


# ========== 結合テストNo.10 ==========
# 異常系 - 初回パスワード変更が完了していない管理者が呼び出した場合
def test_lend_loan_request_endpoint_010_password_change_not_completed_admin_returns_403(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-lend-user-10")
    equipment = _register_equipment(client, admin_token, "LNLD-10")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _approve_loan_request(client, admin_token, created["loan_request_id"])
    _register_user(client, admin_token, "loan-lend-new-admin-10", role="管理者")
    token = _login_and_get_token(client, "loan-lend-new-admin-10", "initial-password-01")

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 返却処理
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：return_loan_request_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出・返却・履歴/返却処理_結合テスト仕様書_v0.2.1.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 貸出中の申請に返却時状態メモを指定して返却処理できること
def test_return_loan_request_endpoint_001_returns_on_loan_request_with_return_note(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-return-user-01")
    equipment = _register_equipment(client, admin_token, "LNRT-01")
    on_loan = _create_loan_request_on_loan(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{on_loan['loan_request_id']}/return",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"return_note": "破損なし"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "返却済み"
    assert body["return_note"] == "破損なし"
    assert body["returned_by_user_id"] == _get_user_internal_id_from_db(_ADMIN_USER_ID)


# ========== 結合テストNo.2 ==========
# 正常系 - 返却時状態メモを指定しない場合、空文字列として返却処理できること
def test_return_loan_request_endpoint_002_returns_without_return_note(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-return-user-02")
    equipment = _register_equipment(client, admin_token, "LNRT-02")
    on_loan = _create_loan_request_on_loan(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{on_loan['loan_request_id']}/return",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "返却済み"
    assert body["return_note"] == ""


# ========== 結合テストNo.3 ==========
# 異常系 - 存在しない貸出申請IDを指定した場合
def test_return_loan_request_endpoint_003_nonexistent_id_returns_404(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.patch(
        "/loan-requests/999999/return",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": _NOT_FOUND_LOAN_REQUEST_DETAIL}


# ========== 結合テストNo.4 ==========
# 異常系 - 状態が「貸出中」でない申請（承認済み）を返却処理しようとした場合
def test_return_loan_request_endpoint_004_approved_request_returns_409(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-return-user-04")
    equipment = _register_equipment(client, admin_token, "LNRT-04")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _approve_loan_request(client, admin_token, created["loan_request_id"])

    response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/return",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": _CONFLICT_CANNOT_RETURN_DETAIL}


# ========== 結合テストNo.5 ==========
# 異常系 - 返却時状態メモが201文字の場合
def test_return_loan_request_endpoint_005_return_note_too_long_returns_422(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-return-user-05")
    equipment = _register_equipment(client, admin_token, "LNRT-05")
    on_loan = _create_loan_request_on_loan(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{on_loan['loan_request_id']}/return",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"return_note": "あ" * 201},
    )

    assert response.status_code == 422


# ========== 結合テストNo.6 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_return_loan_request_endpoint_006_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-return-user-06")
    equipment = _register_equipment(client, admin_token, "LNRT-06")
    on_loan = _create_loan_request_on_loan(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(
        f"/loan-requests/{on_loan['loan_request_id']}/return",
        headers={"Authorization": f"Bearer {general_token}"},
        json={},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.7 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_return_loan_request_endpoint_007_missing_authorization_header_returns_401(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-return-user-07")
    equipment = _register_equipment(client, admin_token, "LNRT-07")
    on_loan = _create_loan_request_on_loan(client, admin_token, general_token, equipment["equipment_id"])

    response = client.patch(f"/loan-requests/{on_loan['loan_request_id']}/return", json={})

    assert response.status_code == 401


# ========== 結合テストNo.8 ==========
# 異常系 - 初回パスワード変更が完了していない管理者が呼び出した場合
def test_return_loan_request_endpoint_008_password_change_not_completed_admin_returns_403(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-return-user-08")
    equipment = _register_equipment(client, admin_token, "LNRT-08")
    on_loan = _create_loan_request_on_loan(client, admin_token, general_token, equipment["equipment_id"])
    _register_user(client, admin_token, "loan-return-new-admin-08", role="管理者")
    token = _login_and_get_token(client, "loan-return-new-admin-08", "initial-password-01")

    response = client.patch(
        f"/loan-requests/{on_loan['loan_request_id']}/return",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ==================================================
# 貸出履歴CSV出力
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：export_loan_requests_csv_endpoint
# テスト仕様書：test_specification/integration_test_specification/貸出・返却・履歴/貸出履歴CSV出力_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 条件を指定せず、全履歴をCSV形式（UTF-8、BOM付き）で出力できること
def test_export_loan_requests_csv_endpoint_001_exports_all_history_with_bom_and_header(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-export-user-01")
    equipment = _register_equipment(client, admin_token, "LNEX-01")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.get("/loan-requests/export", headers={"Authorization": f"Bearer {admin_token}"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.content.startswith(b"\xef\xbb\xbf")
    rows = _parse_csv_rows(response)
    assert rows[0] == _CSV_HEADER
    data_row = next(row for row in rows[1:] if row[0] == str(created["loan_request_id"]))
    assert data_row[1] == str(equipment["equipment_id"])
    assert data_row[2] == str(_get_user_internal_id_from_db("loan-export-user-01"))
    assert data_row[6] == "申請中"


# ========== 結合テストNo.2 ==========
# 正常系 - 開始日範囲（start_date_from・start_date_to）を指定して絞り込めること
def test_export_loan_requests_csv_endpoint_002_filters_by_start_date_range(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-export-user-02")
    equipment = _register_equipment(client, admin_token, "LNEX-02")
    in_range = _create_loan_request(
        client, general_token, equipment["equipment_id"], start_date=_date_iso(1), due_date=_date_iso(2)
    )
    out_of_range = _create_loan_request(
        client, general_token, equipment["equipment_id"], start_date=_date_iso(10), due_date=_date_iso(11)
    )

    response = client.get(
        f"/loan-requests/export?start_date_from={_date_iso(0)}&start_date_to={_date_iso(2)}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    loan_request_id_list = [row[0] for row in _parse_csv_rows(response)[1:]]
    assert str(in_range["loan_request_id"]) in loan_request_id_list
    assert str(out_of_range["loan_request_id"]) not in loan_request_id_list


# ========== 結合テストNo.3 ==========
# 正常系 - 備品ID（equipment_id）を指定して絞り込めること
def test_export_loan_requests_csv_endpoint_003_filters_by_equipment_id(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-export-user-03")
    equipment_a = _register_equipment(client, admin_token, "LNEX-03-A")
    equipment_b = _register_equipment(client, admin_token, "LNEX-03-B")
    matching = _create_loan_request(client, general_token, equipment_a["equipment_id"])
    non_matching = _create_loan_request(client, general_token, equipment_b["equipment_id"])

    response = client.get(
        f"/loan-requests/export?equipment_id={equipment_a['equipment_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    loan_request_id_list = [row[0] for row in _parse_csv_rows(response)[1:]]
    assert str(matching["loan_request_id"]) in loan_request_id_list
    assert str(non_matching["loan_request_id"]) not in loan_request_id_list


# ========== 結合テストNo.4 ==========
# 正常系 - 申請者ID（applicant_user_id）を指定して絞り込めること
def test_export_loan_requests_csv_endpoint_004_filters_by_applicant_user_id(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    token_a = _get_general_user_token(client, admin_token, "loan-export-user-04-a")
    token_b = _get_general_user_token(client, admin_token, "loan-export-user-04-b")
    equipment = _register_equipment(client, admin_token, "LNEX-04")
    matching = _create_loan_request(
        client, token_a, equipment["equipment_id"], start_date=_date_iso(0), due_date=_date_iso(1)
    )
    non_matching = _create_loan_request(
        client, token_b, equipment["equipment_id"], start_date=_date_iso(2), due_date=_date_iso(3)
    )
    applicant_internal_id = _get_user_internal_id_from_db("loan-export-user-04-a")

    response = client.get(
        f"/loan-requests/export?applicant_user_id={applicant_internal_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    loan_request_id_list = [row[0] for row in _parse_csv_rows(response)[1:]]
    assert str(matching["loan_request_id"]) in loan_request_id_list
    assert str(non_matching["loan_request_id"]) not in loan_request_id_list


# ========== 結合テストNo.5 ==========
# 正常系 - 条件に該当する履歴が0件の場合、ヘッダー行のみのCSVが返却されること
def test_export_loan_requests_csv_endpoint_005_no_matching_history_returns_header_only(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-export-user-05")
    equipment = _register_equipment(client, admin_token, "LNEX-05")
    _create_loan_request(client, general_token, equipment["equipment_id"])

    response = client.get(
        "/loan-requests/export?equipment_id=999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert _parse_csv_rows(response) == [_CSV_HEADER]


# ========== 結合テストNo.6 ==========
# 正常系 - 数式インジェクション対策：目的（purpose）が「=」で始まる場合、シングルクォートが付与されること
def test_export_loan_requests_csv_endpoint_006_sanitizes_formula_injection_in_purpose(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-export-user-06")
    equipment = _register_equipment(client, admin_token, "LNEX-06")
    created = _create_loan_request(client, general_token, equipment["equipment_id"], purpose="=SUM(A1:A10)")

    response = client.get("/loan-requests/export", headers={"Authorization": f"Bearer {admin_token}"})

    assert response.status_code == 200
    rows = _parse_csv_rows(response)
    data_row = next(row for row in rows[1:] if row[0] == str(created["loan_request_id"]))
    assert data_row[5] == "'=SUM(A1:A10)"


# ========== 結合テストNo.7 ==========
# 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合
def test_export_loan_requests_csv_endpoint_007_non_admin_user_returns_403(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "loan-export-user-07")

    response = client.get("/loan-requests/export", headers={"Authorization": f"Bearer {general_token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_ADMIN_REQUIRED_DETAIL}


# ========== 結合テストNo.8 ==========
# 異常系 - Authorizationヘッダーを指定せずに呼び出した場合
def test_export_loan_requests_csv_endpoint_008_missing_authorization_header_returns_401(
    client: TestClient,
) -> None:
    response = client.get("/loan-requests/export")

    assert response.status_code == 401


# ========== 結合テストNo.9 ==========
# 異常系 - 初回パスワード変更が完了していない管理者が呼び出した場合
def test_export_loan_requests_csv_endpoint_009_password_change_not_completed_admin_returns_403(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    _register_user(client, admin_token, "loan-export-new-admin-09", role="管理者")
    token = _login_and_get_token(client, "loan-export-new-admin-09", "initial-password-01")

    response = client.get("/loan-requests/export", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json() == {"detail": _FORBIDDEN_PASSWORD_CHANGE_REQUIRED_DETAIL}


# ========== 結合テストNo.10 ==========
# 異常系 - start_date_fromの形式が不正な場合
def test_export_loan_requests_csv_endpoint_010_invalid_start_date_from_format_returns_422(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)

    response = client.get(
        "/loan-requests/export?start_date_from=invalid-date",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422
