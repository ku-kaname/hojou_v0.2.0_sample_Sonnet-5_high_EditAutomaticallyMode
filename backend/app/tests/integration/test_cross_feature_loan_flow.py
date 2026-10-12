import datetime as dt

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import User

_ADMIN_USER_ID = "admin"
_ADMIN_INITIAL_PASSWORD = "integration-test-admin-password"

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
    """初期管理者のパスワードを変更済みの状態にし、新しいアクセストークンを取得する"""
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


def _register_equipment(client: TestClient, admin_token: str, asset_number: str, name: str = "テスト備品") -> dict:
    """管理者トークンで新規備品を登録する（テストケースの前提条件整備用）"""
    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "asset_number": asset_number,
            "name": name,
            "category": "PC",
            "description": "",
            "location": "",
        },
    )
    assert response.status_code == 200
    return response.json()


def _get_user_internal_id_from_db(user_id: str) -> int:
    """DB上のユーザー情報から内部ID（数値）を直接取得する（申請者・担当者IDの比較確認用）"""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.user_id == user_id).one().id
    finally:
        db.close()


def _date_iso(offset_days: int) -> str:
    """サーバー側の「今日」（UTC基準）から指定日数だけずらした日付をISO8601形式の文字列で取得する"""
    return (dt.datetime.now(dt.UTC).date() + dt.timedelta(days=offset_days)).isoformat()


def _parse_csv_rows(response) -> list[list[str]]:
    """CSVレスポンス（UTF-8 BOM付き）をデコードし、行ごとのセル値リストとして取得する（テスト結果検証用）"""
    import csv
    import io

    decoded_text = response.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(decoded_text)))


# ==================================================
# 貸出申請〜履歴出力一連フロー
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：
#   - create_loan_request_endpoint（貸出申請登録）
#   - approve_loan_request_endpoint（承認）
#   - get_notifications_endpoint・read_notification_endpoint（通知確認・既読化）
#   - lend_loan_request_endpoint（貸出処理）
#   - return_loan_request_endpoint（返却処理）
#   - export_loan_requests_csv_endpoint（貸出履歴CSV出力）
# テスト仕様書：test_specification/integration_test_specification/機能横断/貸出申請〜履歴出力一連フロー_結合テスト仕様書_v0.3.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 貸出申請登録から承認・通知確認・貸出処理・返却処理・貸出履歴CSV出力までの一連の流れが、
# 一貫した担当者・日時・状態で完走すること
def test_cross_feature_loan_flow_001_full_flow_consistency(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "crossflow-user-01")
    equipment = _register_equipment(client, admin_token, "CRFL-01")
    admin_internal_id = _get_user_internal_id_from_db(_ADMIN_USER_ID)
    applicant_internal_id = _get_user_internal_id_from_db("crossflow-user-01")

    # ① 一般ユーザーが貸出申請を登録（開始日=今日）
    create_response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {general_token}"},
        json={
            "equipment_id": equipment["equipment_id"],
            "start_date": _date_iso(0),
            "due_date": _date_iso(7),
            "purpose": "資料作成のため",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["status"] == "申請中"
    loan_request_id = created["loan_request_id"]

    # ② 管理者が承認
    approve_response = client.patch(
        f"/loan-requests/{loan_request_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approve_response.status_code == 200
    approved = approve_response.json()
    assert approved["status"] == "承認済み"
    assert approved["approved_rejected_by_user_id"] == admin_internal_id

    # ③ 一般ユーザーが通知一覧を取得し、「承認」種別の未読通知を既読化
    notification_list_response = client.get(
        "/notifications", headers={"Authorization": f"Bearer {general_token}"}
    )
    assert notification_list_response.status_code == 200
    notification_list = notification_list_response.json()
    approval_notification_list = [
        notification for notification in notification_list if notification["notification_type"] == "承認"
    ]
    assert len(approval_notification_list) == 1
    approval_notification = approval_notification_list[0]
    assert approval_notification["read_flag"] is False

    read_response = client.patch(
        f"/notifications/{approval_notification['notification_id']}/read",
        headers={"Authorization": f"Bearer {general_token}"},
    )
    assert read_response.status_code == 200
    assert read_response.json()["read_flag"] is True

    # ④ 管理者が貸出処理
    lend_response = client.patch(
        f"/loan-requests/{loan_request_id}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert lend_response.status_code == 200
    lent = lend_response.json()
    assert lent["status"] == "貸出中"
    assert lent["lent_by_user_id"] == admin_internal_id

    # ⑤ 管理者が返却処理（return_note="破損なし"）
    return_response = client.patch(
        f"/loan-requests/{loan_request_id}/return",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"return_note": "破損なし"},
    )
    assert return_response.status_code == 200
    returned = return_response.json()
    assert returned["status"] == "返却済み"
    assert returned["returned_by_user_id"] == admin_internal_id
    assert returned["return_note"] == "破損なし"

    # ⑥ 管理者が貸出履歴CSVを出力し、②〜⑤で確定した情報と完全に一致することを確認
    export_response = client.get(
        "/loan-requests/export", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert export_response.status_code == 200
    rows = _parse_csv_rows(export_response)
    assert rows[0] == _CSV_HEADER
    data_row = next(row for row in rows[1:] if row[0] == str(loan_request_id))
    row_as_dict = dict(zip(_CSV_HEADER, data_row))
    assert row_as_dict["equipment_id"] == str(equipment["equipment_id"])
    assert row_as_dict["applicant_user_id"] == str(applicant_internal_id)
    assert row_as_dict["status"] == "返却済み"
    assert row_as_dict["approved_rejected_by_user_id"] == str(admin_internal_id)
    assert row_as_dict["lent_by_user_id"] == str(admin_internal_id)
    assert row_as_dict["returned_by_user_id"] == str(admin_internal_id)
    # CSV側は`str(datetime)`形式（空白区切り・タイムゾーン情報なし）、レスポンス側はISO8601形式
    # （T区切り・UTCのタイムゾーン情報付き）のため、文字列同士では比較できない。
    # どちらもUTCの同一時刻を表すため、レスポンス側のタイムゾーン情報を除去した上で比較する。
    response_returned_at = dt.datetime.fromisoformat(returned["returned_at"]).replace(tzinfo=None)
    assert dt.datetime.fromisoformat(row_as_dict["returned_at"]) == response_returned_at
    assert row_as_dict["return_note"] == "破損なし"
