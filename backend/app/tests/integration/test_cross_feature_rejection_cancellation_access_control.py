import datetime as dt

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import User

_ADMIN_USER_ID = "admin"
_ADMIN_INITIAL_PASSWORD = "integration-test-admin-password"
_CONFLICT_CANNOT_LEND_DETAIL = "この申請は現在の状態では貸出処理できません。"
_CONFLICT_CANNOT_APPROVE_DETAIL = "この申請は現在の状態では承認できません。"


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


def _date_iso(offset_days: int) -> str:
    """サーバー側の「今日」（UTC基準）から指定日数だけずらした日付をISO8601形式の文字列で取得する"""
    return (dt.datetime.now(dt.UTC).date() + dt.timedelta(days=offset_days)).isoformat()


def _create_loan_request(client: TestClient, token: str, equipment_id: int) -> dict:
    """貸出申請を登録する（テストケースの前提条件整備用。開始日=今日、返却予定日=翌日）"""
    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "equipment_id": equipment_id,
            "start_date": _date_iso(0),
            "due_date": _date_iso(1),
            "purpose": "資料作成のため",
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


def _get_user_internal_id_from_db(user_id: str) -> int:
    """DB上のユーザー情報から内部ID（数値）を直接取得する（担当者IDの比較確認用）"""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.user_id == user_id).one().id
    finally:
        db.close()


# ==================================================
# 却下・取消後アクセス制御フロー
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：
#   - reject_loan_request_endpoint（却下）・cancel_loan_request_endpoint（本人取消）
#   - admin_cancel_loan_request_endpoint（管理者取消）
#   - approve_loan_request_endpoint（承認）・lend_loan_request_endpoint（貸出処理）
#   - get_notifications_endpoint（通知確認）
# テスト仕様書：test_specification/integration_test_specification/機能横断/却下・取消後アクセス制御フロー_結合テスト仕様書_v0.3.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 却下後、申請者へ却下通知が届き、当該申請への貸出処理が拒否されること
def test_cross_feature_rejection_cancellation_access_control_001_rejected_request_blocks_lend(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "crossreject-user-01")
    equipment = _register_equipment(client, admin_token, "CRRJ-01")

    # ① 一般ユーザーが貸出申請を登録
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    # ② 管理者が却下
    reject_response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "在庫不足のため"},
    )
    assert reject_response.status_code == 200
    rejected = reject_response.json()
    assert rejected["status"] == "却下"
    assert rejected["reject_cancel_reason"] == "在庫不足のため"

    # ③ 一般ユーザーが通知一覧を取得し、「却下」種別の通知が1件存在することを確認
    notification_list_response = client.get(
        "/notifications", headers={"Authorization": f"Bearer {general_token}"}
    )
    assert notification_list_response.status_code == 200
    reject_notification_list = [
        notification
        for notification in notification_list_response.json()
        if notification["notification_type"] == "却下"
    ]
    assert len(reject_notification_list) == 1

    # ④ 管理者が貸出処理を試み、拒否されることを確認
    lend_response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert lend_response.status_code == 409
    assert lend_response.json() == {"detail": _CONFLICT_CANNOT_LEND_DETAIL}


# ========== 結合テストNo.2 ==========
# 正常系 - 申請者本人による取消後、当該申請への承認が拒否されること
def test_cross_feature_rejection_cancellation_access_control_002_self_cancelled_request_blocks_approve(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "crossreject-user-02")
    equipment = _register_equipment(client, admin_token, "CRRJ-02")

    # ① 一般ユーザーが貸出申請を登録
    created = _create_loan_request(client, general_token, equipment["equipment_id"])

    # ② 一般ユーザーが取消
    cancel_response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/cancel",
        headers={"Authorization": f"Bearer {general_token}"},
        json={},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "取消"

    # ③ 管理者が承認を試み、拒否されることを確認
    approve_response = client.patch(
        f"/loan-requests/{created['loan_request_id']}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approve_response.status_code == 409
    assert approve_response.json() == {"detail": _CONFLICT_CANNOT_APPROVE_DETAIL}


# ========== 結合テストNo.3 ==========
# 正常系 - 管理者取消後、申請者へ取消通知が届き、当該申請への貸出処理が拒否されること
def test_cross_feature_rejection_cancellation_access_control_003_admin_cancelled_request_blocks_lend(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "crossreject-user-03")
    equipment = _register_equipment(client, admin_token, "CRRJ-03")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    approved = _approve_loan_request(client, admin_token, created["loan_request_id"])
    admin_internal_id = _get_user_internal_id_from_db(_ADMIN_USER_ID)

    # ① 管理者が取消
    admin_cancel_response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/admin-cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"reason": "備品の点検が必要なため"},
    )
    assert admin_cancel_response.status_code == 200
    cancelled = admin_cancel_response.json()
    assert cancelled["status"] == "取消"
    assert cancelled["reject_cancel_reason"] == "備品の点検が必要なため"
    assert cancelled["cancelled_by_user_id"] == admin_internal_id

    # ② 一般ユーザーが通知一覧を取得し、「取消」種別の通知が1件存在することを確認
    notification_list_response = client.get(
        "/notifications", headers={"Authorization": f"Bearer {general_token}"}
    )
    assert notification_list_response.status_code == 200
    cancel_notification_list = [
        notification
        for notification in notification_list_response.json()
        if notification["notification_type"] == "取消"
    ]
    assert len(cancel_notification_list) == 1

    # ③ 管理者が貸出処理を試み、拒否されることを確認
    lend_response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert lend_response.status_code == 409
    assert lend_response.json() == {"detail": _CONFLICT_CANNOT_LEND_DETAIL}
