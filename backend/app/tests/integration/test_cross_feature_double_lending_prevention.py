import datetime as dt

from fastapi.testclient import TestClient

_ADMIN_USER_ID = "admin"
_ADMIN_INITIAL_PASSWORD = "integration-test-admin-password"
_CONFLICT_PERIOD_OVERLAP_DETAIL = "指定した期間は、既に承認済みまたは貸出中の申請と重複しています。"


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
    """貸出申請を登録する（テストケースの前提条件整備用。開始日=今日、返却予定日=7日後）"""
    response = client.post(
        "/loan-requests",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "equipment_id": equipment_id,
            "start_date": _date_iso(0),
            "due_date": _date_iso(7),
            "purpose": "資料作成のため",
        },
    )
    return response


def _approve_loan_request(client: TestClient, admin_token: str, loan_request_id: int) -> dict:
    """貸出申請を承認する（テストケースの前提条件整備用）"""
    response = client.patch(
        f"/loan-requests/{loan_request_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    return response.json()


def _lend_loan_request(client: TestClient, admin_token: str, loan_request_id: int) -> dict:
    """貸出処理を行う（テストケースの前提条件整備用）"""
    response = client.patch(
        f"/loan-requests/{loan_request_id}/lend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    return response.json()


# ==================================================
# 二重貸出防止・備品占有解放フロー
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：
#   - create_loan_request_endpoint（貸出申請登録。期間重複確認を含む）
#   - approve_loan_request_endpoint（承認）・lend_loan_request_endpoint（貸出処理）
#   - return_loan_request_endpoint（返却処理。備品占有解放）
# テスト仕様書：test_specification/integration_test_specification/機能横断/二重貸出防止・備品占有解放フロー_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - 同一備品が貸出中の間、別ユーザーによる同一期間の新規申請が拒否されること
def test_cross_feature_double_lending_prevention_001_overlapping_request_rejected_while_on_loan(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    user1_token = _get_general_user_token(client, admin_token, "crossdouble-user-01")
    user2_token = _get_general_user_token(client, admin_token, "crossdouble-user-02")
    equipment = _register_equipment(client, admin_token, "CRDB-01")

    # ① ユーザー1が貸出申請を登録し、管理者が承認→貸出処理まで完了させる
    created_response = _create_loan_request(client, user1_token, equipment["equipment_id"])
    assert created_response.status_code == 200
    created = created_response.json()
    approved = _approve_loan_request(client, admin_token, created["loan_request_id"])
    lent = _lend_loan_request(client, admin_token, approved["loan_request_id"])
    assert lent["status"] == "貸出中"

    # ② ユーザー2が同一備品・同一期間で貸出申請を試み、拒否されることを確認
    conflict_response = _create_loan_request(client, user2_token, equipment["equipment_id"])
    assert conflict_response.status_code == 409
    assert conflict_response.json() == {"detail": _CONFLICT_PERIOD_OVERLAP_DETAIL}


# ========== 結合テストNo.2 ==========
# 正常系 - ①の返却処理により備品占有が解放された後、②で拒否された申請内容を再度登録すると、
# 正常に登録・承認・貸出処理まで完走できること
def test_cross_feature_double_lending_prevention_002_resubmission_succeeds_after_return(
    client: TestClient,
) -> None:
    admin_token = _get_password_changed_admin_token(client)
    user1_token = _get_general_user_token(client, admin_token, "crossdouble-user-03")
    user2_token = _get_general_user_token(client, admin_token, "crossdouble-user-04")
    equipment = _register_equipment(client, admin_token, "CRDB-02")

    # 項番1と同じ前提状態を再現：ユーザー1が貸出中、ユーザー2の同一期間申請は拒否される
    created_response = _create_loan_request(client, user1_token, equipment["equipment_id"])
    assert created_response.status_code == 200
    created = created_response.json()
    approved = _approve_loan_request(client, admin_token, created["loan_request_id"])
    lent = _lend_loan_request(client, admin_token, approved["loan_request_id"])
    assert lent["status"] == "貸出中"
    conflict_response = _create_loan_request(client, user2_token, equipment["equipment_id"])
    assert conflict_response.status_code == 409

    # ① 管理者が、ユーザー1の貸出申請に対して返却処理
    return_response = client.patch(
        f"/loan-requests/{lent['loan_request_id']}/return",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"return_note": "破損なし"},
    )
    assert return_response.status_code == 200
    assert return_response.json()["status"] == "返却済み"

    # ② ユーザー2が、同一の備品・同一期間で貸出申請を再度登録（備品占有解放済みのため成功すること）
    resubmit_response = _create_loan_request(client, user2_token, equipment["equipment_id"])
    assert resubmit_response.status_code == 200
    resubmitted = resubmit_response.json()
    assert resubmitted["status"] == "申請中"

    # ③ 管理者が②の申請を承認し、貸出処理
    reapproved = _approve_loan_request(client, admin_token, resubmitted["loan_request_id"])
    assert reapproved["status"] == "承認済み"
    relent = _lend_loan_request(client, admin_token, reapproved["loan_request_id"])
    assert relent["status"] == "貸出中"
