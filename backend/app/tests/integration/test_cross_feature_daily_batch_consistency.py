import datetime as dt

from fastapi.testclient import TestClient

from app import scheduler
from app.database import SessionLocal
from app.models import LoanRequest, User

_ADMIN_USER_ID = "admin"
_ADMIN_INITIAL_PASSWORD = "integration-test-admin-password"
_CONFLICT_CANNOT_LEND_DETAIL = "この申請は現在の状態では貸出処理できません。"


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


def _create_loan_request(
    client: TestClient,
    token: str,
    equipment_id: int,
    start_date: str | None = None,
    due_date: str | None = None,
) -> dict:
    """貸出申請を登録する（テストケースの前提条件整備用。開始日・返却予定日省略時は今日〜翌日とする）"""
    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "equipment_id": equipment_id,
            "start_date": start_date if start_date is not None else _date_iso(0),
            "due_date": due_date if due_date is not None else _date_iso(1),
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

    貸出処理は開始日が今日より後の場合エラーとなるため、開始日は必ず今日とする。
    """
    created = _create_loan_request(client, general_token, equipment_id, start_date=_date_iso(0), due_date=_date_iso(7))
    _approve_loan_request(client, admin_token, created["loan_request_id"])
    return _lend_loan_request(client, admin_token, created["loan_request_id"])


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
    """DB上の貸出申請の返却予定日を直接更新する（返却予定日の前日・翌日の「貸出中」状態の前提条件整備用。
    API経由では返却予定日に過去日を指定できないため、DBを直接更新してテスト条件を作る）"""
    db = SessionLocal()
    try:
        target_loan_request = db.query(LoanRequest).filter(LoanRequest.id == loan_request_id).one()
        target_loan_request.due_date = due_date
        db.commit()
    finally:
        db.close()


def _get_user_internal_id_from_db(user_id: str) -> int:
    """DB上のユーザー情報から内部ID（数値）を直接取得する（申請者IDの比較確認用）"""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.user_id == user_id).one().id
    finally:
        db.close()


# ==================================================
# 日次バッチ処理整合性フロー
# テスト対象ファイル：scheduler.py・main.py
# テスト対象クラス：-
# テスト対象メソッド：
#   - scheduler.run_no_show_cancellation_batch（ノーショー自動取消バッチ）
#   - scheduler.run_due_date_notification_batch（返却期限通知バッチ）
#   - lend_loan_request_endpoint・get_notifications_endpoint・read_notification_endpoint
#   - get_loan_requests_endpoint（scope=overdue）・return_loan_request_endpoint
# テスト仕様書：test_specification/integration_test_specification/機能横断/日次バッチ処理整合性フロー_結合テスト仕様書_v0.4.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - ノーショー自動取消（開始日超過）バッチ実行後、申請中のまま開始日を過ぎた申請が取消済みとなり、
# 申請者へ取消通知が届き、貸出処理が拒否されること
def test_cross_feature_daily_batch_consistency_001_no_show_cancellation_by_start_date(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "crossbatch-user-01")
    equipment = _register_equipment(client, admin_token, "CRBT-01")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    _set_loan_request_start_date_in_db(created["loan_request_id"], dt.date.fromisoformat(_date_iso(-1)))

    # ① ノーショー自動取消（開始日超過）バッチを実行
    scheduler.run_no_show_cancellation_batch()

    db = SessionLocal()
    try:
        target_loan_request = db.query(LoanRequest).filter(LoanRequest.id == created["loan_request_id"]).one()
        assert target_loan_request.status == "取消"
        assert target_loan_request.reject_cancel_reason == "申請中のまま開始日を過ぎたため、自動的に取消しました。"
    finally:
        db.close()

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
        f"/loan-requests/{created['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert lend_response.status_code == 409
    assert lend_response.json() == {"detail": _CONFLICT_CANNOT_LEND_DETAIL}


# ========== 結合テストNo.2 ==========
# 正常系 - ノーショー自動取消（返却予定日超過）バッチ実行後、承認済みのまま返却予定日を過ぎた申請が
# 取消済みとなり、貸出処理が拒否されること
def test_cross_feature_daily_batch_consistency_002_no_show_cancellation_by_due_date(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "crossbatch-user-02")
    equipment = _register_equipment(client, admin_token, "CRBT-02")
    created = _create_loan_request(client, general_token, equipment["equipment_id"])
    approved = _approve_loan_request(client, admin_token, created["loan_request_id"])
    _set_loan_request_due_date_in_db(approved["loan_request_id"], dt.date.fromisoformat(_date_iso(-1)))

    # ① ノーショー自動取消（返却予定日超過）バッチを実行
    scheduler.run_no_show_cancellation_batch()

    db = SessionLocal()
    try:
        target_loan_request = db.query(LoanRequest).filter(LoanRequest.id == approved["loan_request_id"]).one()
        assert target_loan_request.status == "取消"
        assert target_loan_request.reject_cancel_reason == "承認済みのまま返却予定日を過ぎたため、自動的に取消しました。"
    finally:
        db.close()

    # ② 管理者が貸出処理を試み、拒否されることを確認
    lend_response = client.patch(
        f"/loan-requests/{approved['loan_request_id']}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert lend_response.status_code == 409
    assert lend_response.json() == {"detail": _CONFLICT_CANNOT_LEND_DETAIL}


# ========== 結合テストNo.3 ==========
# 正常系 - 返却期限通知（前日）バッチ実行後、返却予定日が翌日の貸出中申請の申請者へ通知が届き、
# 既読化できること
def test_cross_feature_daily_batch_consistency_003_due_date_tomorrow_notification(client: TestClient) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "crossbatch-user-03")
    equipment = _register_equipment(client, admin_token, "CRBT-03")
    on_loan = _create_loan_request_on_loan(client, admin_token, general_token, equipment["equipment_id"])
    _set_loan_request_due_date_in_db(on_loan["loan_request_id"], dt.date.fromisoformat(_date_iso(1)))

    # ① 返却期限通知バッチを実行（対象の貸出申請の申請者宛に返却期限通知が1件生成されることは、
    # ②の通知一覧取得結果（1件のみ・未読）で確認する）
    scheduler.run_due_date_notification_batch()

    # ② 一般ユーザーが通知一覧を取得し、未読の「返却期限」通知が1件存在することを確認
    notification_list_response = client.get(
        "/notifications", headers={"Authorization": f"Bearer {general_token}"}
    )
    assert notification_list_response.status_code == 200
    due_date_notification_list = [
        notification
        for notification in notification_list_response.json()
        if notification["notification_type"] == "返却期限"
    ]
    assert len(due_date_notification_list) == 1
    assert due_date_notification_list[0]["read_flag"] is False

    # ③ ②で取得した通知を既読化
    read_response = client.patch(
        f"/notifications/{due_date_notification_list[0]['notification_id']}/read",
        headers={"Authorization": f"Bearer {general_token}"},
    )
    assert read_response.status_code == 200
    assert read_response.json()["read_flag"] is True


# ========== 結合テストNo.4 ==========
# 正常系 - 返却期限通知（期限超過中）バッチ実行後、通知生成の結果と貸出申請一覧取得（scope=overdue）の
# 結果が整合し、返却処理後は一覧から除外されること
def test_cross_feature_daily_batch_consistency_004_overdue_notification_and_list_consistency(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    general_token = _get_general_user_token(client, admin_token, "crossbatch-user-04")
    equipment = _register_equipment(client, admin_token, "CRBT-04")
    on_loan = _create_loan_request_on_loan(client, admin_token, general_token, equipment["equipment_id"])
    _set_loan_request_due_date_in_db(on_loan["loan_request_id"], dt.date.fromisoformat(_date_iso(-1)))

    # ① 返却期限通知バッチを実行
    scheduler.run_due_date_notification_batch()

    # ② 一般ユーザーが通知一覧を取得し、未読の「返却期限」通知（項番3と同一の通知種別）が1件存在することを確認
    notification_list_response = client.get(
        "/notifications", headers={"Authorization": f"Bearer {general_token}"}
    )
    assert notification_list_response.status_code == 200
    due_date_notification_list = [
        notification
        for notification in notification_list_response.json()
        if notification["notification_type"] == "返却期限"
    ]
    assert len(due_date_notification_list) == 1
    assert due_date_notification_list[0]["read_flag"] is False

    # ③ 管理者が期限超過一覧を取得し、対象の貸出申請が含まれることを確認
    overdue_list_response_before = client.get(
        "/loan-requests?scope=overdue", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert overdue_list_response_before.status_code == 200
    overdue_id_list_before = [
        loan_request["loan_request_id"] for loan_request in overdue_list_response_before.json()
    ]
    assert on_loan["loan_request_id"] in overdue_id_list_before

    # ④ 管理者が返却処理
    return_response = client.patch(
        f"/loan-requests/{on_loan['loan_request_id']}/return",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={},
    )
    assert return_response.status_code == 200
    assert return_response.json()["status"] == "返却済み"

    # ⑤ 管理者が期限超過一覧を再取得し、対象の貸出申請が除外されていることを確認
    overdue_list_response_after = client.get(
        "/loan-requests?scope=overdue", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert overdue_list_response_after.status_code == 200
    overdue_id_list_after = [
        loan_request["loan_request_id"] for loan_request in overdue_list_response_after.json()
    ]
    assert on_loan["loan_request_id"] not in overdue_id_list_after
