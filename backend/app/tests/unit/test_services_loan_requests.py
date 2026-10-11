import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import services


# 貸出申請レスポンスの元になるcrud層レスポンス（LoanRequest相当）のモックを組み立てる。
# 個々のテストで変えたい項目のみoverridesで上書きする。
def build_mock_loan_request(**overrides):
    defaults = {
        "id": 1,
        "equipment_id": 1,
        "start_date": dt.date(2026, 10, 1),
        "due_date": dt.date(2026, 10, 10),
        "purpose": "テスト用途",
        "applicant_user_id": 100,
        "status": "申請中",
        "reject_cancel_reason": None,
        "approved_rejected_by_user_id": None,
        "lent_by_user_id": None,
        "returned_by_user_id": None,
        "cancelled_by_user_id": None,
        "requested_at": dt.datetime(2026, 10, 1, 9, 0, tzinfo=dt.UTC),
        "approved_rejected_at": None,
        "lent_at": None,
        "returned_at": None,
        "cancelled_at": None,
        "return_note": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# 通知レスポンスの元になるcrud層レスポンス（Notification相当）のモックを組み立てる。
def build_mock_notification(**overrides):
    defaults = {
        "id": 1,
        "notification_type": "新規申請",
        "loan_request_id": 1,
        "recipient_user_id": 100,
        "read_flag": False,
        "created_at": dt.datetime(2026, 10, 1, 9, 0, tzinfo=dt.UTC),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ==================================================
# 貸出申請登録
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：create_loan_request
# テスト仕様書：test_specification/unit_test_specification/貸出申請・承認/貸出申請登録_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象備品が存在しない場合に404エラーが発生すること
def test_create_loan_request_001_target_equipment_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=None)
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.create_loan_request(
            current_user=mock_current_user,
            db=mocker.Mock(),
            equipment_id=1,
            start_date=dt.date.today(),
            due_date=dt.date.today() + dt.timedelta(days=5),
            purpose="テスト用途",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された備品が見つかりません。"


# ========== 単体テストNo.2 ==========
# 対象備品が無効化されている場合に409エラーが発生すること
def test_create_loan_request_002_inactive_equipment_raises_409(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=False)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.create_loan_request(
            current_user=mock_current_user,
            db=mocker.Mock(),
            equipment_id=1,
            start_date=dt.date.today(),
            due_date=dt.date.today() + dt.timedelta(days=5),
            purpose="テスト用途",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "指定された備品は無効化されているため、貸出を申請できません。"


# ========== 単体テストNo.3 ==========
# 開始日に今日より前の日付を指定した場合に400エラーが発生すること
def test_create_loan_request_003_start_date_before_today_raises_400(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=True)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.create_loan_request(
            current_user=mock_current_user,
            db=mocker.Mock(),
            equipment_id=1,
            start_date=dt.date.today() - dt.timedelta(days=1),
            due_date=dt.date.today() + dt.timedelta(days=5),
            purpose="テスト用途",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "開始日には今日以降の日付を指定してください。"


# ========== 単体テストNo.4 ==========
# 返却予定日に開始日より前の日付を指定した場合に400エラーが発生すること
def test_create_loan_request_004_due_date_before_start_date_raises_400(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=True)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_current_user = SimpleNamespace(id=100, role="一般")
    start_date = dt.date.today() + dt.timedelta(days=5)

    with pytest.raises(HTTPException) as exc_info:
        services.create_loan_request(
            current_user=mock_current_user,
            db=mocker.Mock(),
            equipment_id=1,
            start_date=start_date,
            due_date=start_date - dt.timedelta(days=1),
            purpose="テスト用途",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "返却予定日には開始日以降の日付を指定してください。"


# ========== 単体テストNo.5 ==========
# 同一備品について承認済み・貸出中の申請と期間が重複する場合に409エラーが発生すること
def test_create_loan_request_005_overlapping_period_raises_409(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=True)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mocker.patch("app.services.crud.count_overlapping_loan_requests", return_value=1)
    mock_create_loan_request = mocker.patch("app.services.crud.create_loan_request")
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.create_loan_request(
            current_user=mock_current_user,
            db=mocker.Mock(),
            equipment_id=1,
            start_date=dt.date.today() + dt.timedelta(days=1),
            due_date=dt.date.today() + dt.timedelta(days=5),
            purpose="テスト用途",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "指定した期間は、既に承認済みまたは貸出中の申請と重複しています。"
    mock_create_loan_request.assert_not_called()


# ========== 単体テストNo.6 ==========
# 重複がない場合に申請者をログインユーザー自身として申請が登録されること
def test_create_loan_request_006_no_overlap_registers_with_login_user_as_applicant(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=True)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mocker.patch("app.services.crud.count_overlapping_loan_requests", return_value=0)
    mock_created_loan_request = build_mock_loan_request(applicant_user_id=100)
    mock_create_loan_request = mocker.patch(
        "app.services.crud.create_loan_request", return_value=mock_created_loan_request
    )
    mocker.patch("app.services.crud.get_active_admin_user_id_list", return_value=[])
    mock_current_user = SimpleNamespace(id=100, role="一般")

    loan_request_response = services.create_loan_request(
        current_user=mock_current_user,
        db=mocker.Mock(),
        equipment_id=1,
        start_date=dt.date.today() + dt.timedelta(days=1),
        due_date=dt.date.today() + dt.timedelta(days=5),
        purpose="テスト用途",
    )

    mock_create_loan_request.assert_called_once()
    assert mock_create_loan_request.call_args.args[2] == 100
    assert loan_request_response.applicant_user_id == 100


# ========== 単体テストNo.7 ==========
# 有効な管理者が複数名いる場合、各管理者宛に「新規申請」通知が生成されること
def test_create_loan_request_007_multiple_admins_create_notification_for_each(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=True)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mocker.patch("app.services.crud.count_overlapping_loan_requests", return_value=0)
    mocker.patch("app.services.crud.create_loan_request", return_value=build_mock_loan_request())
    mocker.patch("app.services.crud.get_active_admin_user_id_list", return_value=[10, 20])
    mock_create_notification = mocker.patch("app.services.crud.create_notification")
    mock_current_user = SimpleNamespace(id=100, role="一般")

    services.create_loan_request(
        current_user=mock_current_user,
        db=mocker.Mock(),
        equipment_id=1,
        start_date=dt.date.today() + dt.timedelta(days=1),
        due_date=dt.date.today() + dt.timedelta(days=5),
        purpose="テスト用途",
    )

    assert mock_create_notification.call_count == 2
    notified_admin_id_list = [call.args[1] for call in mock_create_notification.call_args_list]
    assert notified_admin_id_list == [10, 20]
    assert all(call.args[2] == "新規申請" for call in mock_create_notification.call_args_list)


# ========== 単体テストNo.8 ==========
# 有効な管理者が0名の場合、通知生成が行われず例外も発生しないこと
def test_create_loan_request_008_no_admins_skips_notification(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=True)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mocker.patch("app.services.crud.count_overlapping_loan_requests", return_value=0)
    mocker.patch("app.services.crud.create_loan_request", return_value=build_mock_loan_request())
    mocker.patch("app.services.crud.get_active_admin_user_id_list", return_value=[])
    mock_create_notification = mocker.patch("app.services.crud.create_notification")
    mock_current_user = SimpleNamespace(id=100, role="一般")

    services.create_loan_request(
        current_user=mock_current_user,
        db=mocker.Mock(),
        equipment_id=1,
        start_date=dt.date.today() + dt.timedelta(days=1),
        due_date=dt.date.today() + dt.timedelta(days=5),
        purpose="テスト用途",
    )

    mock_create_notification.assert_not_called()


# ==================================================
# 貸出申請一覧取得
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：get_loan_requests
# テスト仕様書：test_specification/unit_test_specification/貸出申請・承認/貸出申請一覧取得_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象範囲が"all"で、ログインユーザーが管理者でない場合に403エラーが発生すること
def test_get_loan_requests_001_scope_all_general_user_raises_403(mocker):
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.get_loan_requests(
            current_user=mock_current_user, db=mocker.Mock(), scope="all", status_filter=None
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "この操作を行う権限がありません。"


# ========== 単体テストNo.2 ==========
# 対象範囲が"overdue"で、ログインユーザーが管理者でない場合に403エラーが発生すること
def test_get_loan_requests_002_scope_overdue_general_user_raises_403(mocker):
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.get_loan_requests(
            current_user=mock_current_user, db=mocker.Mock(), scope="overdue", status_filter=None
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "この操作を行う権限がありません。"


# ========== 単体テストNo.3 ==========
# 対象範囲が"mine"の場合、申請者をログインユーザー自身に絞り込んで検索すること
def test_get_loan_requests_003_scope_mine_searches_by_login_user(mocker):
    mock_search_loan_requests = mocker.patch(
        "app.services.crud.search_loan_requests", return_value=[]
    )
    mock_current_user = SimpleNamespace(id=100, role="一般")

    services.get_loan_requests(
        current_user=mock_current_user, db=mocker.Mock(), scope="mine", status_filter="申請中"
    )

    called_args = mock_search_loan_requests.call_args.args
    assert called_args[1] == 100
    assert called_args[2] == "申請中"
    assert called_args[4] is None


# ========== 単体テストNo.4 ==========
# 対象範囲が"all"で管理者の場合、403エラーとならず全件を対象に検索すること
def test_get_loan_requests_004_scope_all_admin_searches_all(mocker):
    mock_search_loan_requests = mocker.patch(
        "app.services.crud.search_loan_requests", return_value=[]
    )
    mock_current_user = SimpleNamespace(id=100, role="管理者")

    services.get_loan_requests(
        current_user=mock_current_user, db=mocker.Mock(), scope="all", status_filter="承認済み"
    )

    called_args = mock_search_loan_requests.call_args.args
    assert called_args[1] is None
    assert called_args[2] == "承認済み"
    assert called_args[4] is None


# ========== 単体テストNo.5 ==========
# 対象範囲が"overdue"の場合、状態="貸出中"固定・返却予定日上限=今日で検索し、status_filterは無視されること
def test_get_loan_requests_005_scope_overdue_fixes_status_and_due_date(mocker):
    mock_search_loan_requests = mocker.patch(
        "app.services.crud.search_loan_requests", return_value=[]
    )
    mock_current_user = SimpleNamespace(id=100, role="管理者")

    services.get_loan_requests(
        current_user=mock_current_user, db=mocker.Mock(), scope="overdue", status_filter="申請中"
    )

    called_args = mock_search_loan_requests.call_args.args
    assert called_args[1] is None
    assert called_args[2] == "貸出中"
    assert called_args[4] == dt.date.today()


# ========== 単体テストNo.6 ==========
# 検索結果が0件の場合、空のリストが返却されること
def test_get_loan_requests_006_no_results_returns_empty_list(mocker):
    mocker.patch("app.services.crud.search_loan_requests", return_value=[])
    mock_current_user = SimpleNamespace(id=100, role="一般")

    loan_request_response_list = services.get_loan_requests(
        current_user=mock_current_user, db=mocker.Mock(), scope="mine", status_filter=None
    )

    assert loan_request_response_list == []


# ==================================================
# 貸出申請詳細取得
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：get_loan_request
# テスト仕様書：test_specification/unit_test_specification/貸出申請・承認/貸出申請詳細取得_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象貸出申請が存在しない場合に404エラーが発生すること
def test_get_loan_request_001_target_loan_request_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=None)
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.get_loan_request(current_user=mock_current_user, db=mocker.Mock(), loan_request_id=1)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された貸出申請が見つかりません。"


# ========== 単体テストNo.2 ==========
# 一般ユーザーが他人の申請を取得しようとした場合に404エラーが発生すること
def test_get_loan_request_002_general_user_others_request_raises_404(mocker):
    mock_target_loan_request = build_mock_loan_request(applicant_user_id=999)
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.get_loan_request(current_user=mock_current_user, db=mocker.Mock(), loan_request_id=1)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された貸出申請が見つかりません。"


# ========== 単体テストNo.3 ==========
# 一般ユーザーが自分の申請を取得する場合はアクセス制御をスキップして取得できること
def test_get_loan_request_003_general_user_own_request_skips_access_control(mocker):
    mock_target_loan_request = build_mock_loan_request(applicant_user_id=100)
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_current_user = SimpleNamespace(id=100, role="一般")

    loan_request_response = services.get_loan_request(
        current_user=mock_current_user, db=mocker.Mock(), loan_request_id=1
    )

    assert loan_request_response.loan_request_id == mock_target_loan_request.id
    assert loan_request_response.applicant_user_id == 100


# ========== 単体テストNo.4 ==========
# 管理者が他人の申請を取得する場合はアクセス制御をスキップして取得できること
def test_get_loan_request_004_admin_others_request_skips_access_control(mocker):
    mock_target_loan_request = build_mock_loan_request(applicant_user_id=999)
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_current_user = SimpleNamespace(id=100, role="管理者")

    loan_request_response = services.get_loan_request(
        current_user=mock_current_user, db=mocker.Mock(), loan_request_id=1
    )

    assert loan_request_response.applicant_user_id == 999


# ==================================================
# 貸出申請取消
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：cancel_loan_request_by_applicant
# テスト仕様書：test_specification/unit_test_specification/貸出申請・承認/貸出申請取消_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象貸出申請が存在しない場合に404エラーが発生すること
def test_cancel_loan_request_by_applicant_001_target_loan_request_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=None)
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.cancel_loan_request_by_applicant(
            current_user=mock_current_user, db=mocker.Mock(), loan_request_id=1, reason=None
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された貸出申請が見つかりません。"


# ========== 単体テストNo.2 ==========
# 対象の申請がログインユーザー自身の申請でない場合に404エラーが発生すること
def test_cancel_loan_request_by_applicant_002_others_request_raises_404(mocker):
    mock_target_loan_request = build_mock_loan_request(applicant_user_id=999, status="申請中")
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.cancel_loan_request_by_applicant(
            current_user=mock_current_user, db=mocker.Mock(), loan_request_id=1, reason=None
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された貸出申請が見つかりません。"


# ========== 単体テストNo.3 ==========
# 対象の申請の状態が「申請中」「承認済み」のいずれでもない場合に409エラーが発生すること
def test_cancel_loan_request_by_applicant_003_invalid_status_raises_409(mocker):
    mock_target_loan_request = build_mock_loan_request(applicant_user_id=100, status="却下")
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.cancel_loan_request_by_applicant(
            current_user=mock_current_user, db=mocker.Mock(), loan_request_id=1, reason=None
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "この申請は現在の状態では取消できません。"


# ========== 単体テストNo.4 ==========
# 対象の申請の状態が「申請中」の場合は取消できること
def test_cancel_loan_request_by_applicant_004_status_requested_cancels(mocker):
    mock_target_loan_request = build_mock_loan_request(applicant_user_id=100, status="申請中")
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_cancelled_loan_request = build_mock_loan_request(applicant_user_id=100, status="取消")
    mock_cancel_loan_request = mocker.patch(
        "app.services.crud.cancel_loan_request", return_value=mock_cancelled_loan_request
    )
    mock_current_user = SimpleNamespace(id=100, role="一般")

    loan_request_response = services.cancel_loan_request_by_applicant(
        current_user=mock_current_user, db=mocker.Mock(), loan_request_id=1, reason="私用のため"
    )

    mock_cancel_loan_request.assert_called_once()
    assert loan_request_response.status == "取消"


# ========== 単体テストNo.5 ==========
# 対象の申請の状態が「承認済み」の場合は取消できること
def test_cancel_loan_request_by_applicant_005_status_approved_cancels(mocker):
    mock_target_loan_request = build_mock_loan_request(applicant_user_id=100, status="承認済み")
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_cancelled_loan_request = build_mock_loan_request(applicant_user_id=100, status="取消")
    mock_cancel_loan_request = mocker.patch(
        "app.services.crud.cancel_loan_request", return_value=mock_cancelled_loan_request
    )
    mock_current_user = SimpleNamespace(id=100, role="一般")

    loan_request_response = services.cancel_loan_request_by_applicant(
        current_user=mock_current_user, db=mocker.Mock(), loan_request_id=1, reason="私用のため"
    )

    mock_cancel_loan_request.assert_called_once()
    assert loan_request_response.status == "取消"


# ==================================================
# 貸出申請承認
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：approve_loan_request
# テスト仕様書：test_specification/unit_test_specification/貸出申請・承認/貸出申請承認_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象貸出申請が存在しない場合に404エラーが発生すること
def test_approve_loan_request_001_target_loan_request_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=None)
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    with pytest.raises(HTTPException) as exc_info:
        services.approve_loan_request(
            current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された貸出申請が見つかりません。"


# ========== 単体テストNo.2 ==========
# 対象の申請の状態が「申請中」でない場合に409エラーが発生すること
def test_approve_loan_request_002_status_not_requested_raises_409(mocker):
    mock_target_loan_request = build_mock_loan_request(status="承認済み")
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    with pytest.raises(HTTPException) as exc_info:
        services.approve_loan_request(
            current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "この申請は現在の状態では承認できません。"


# ========== 単体テストNo.3 ==========
# 対象の申請の開始日が今日より前の場合に409エラーが発生すること
def test_approve_loan_request_003_start_date_before_today_raises_409(mocker):
    mock_target_loan_request = build_mock_loan_request(
        status="申請中", start_date=dt.date.today() - dt.timedelta(days=1)
    )
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    with pytest.raises(HTTPException) as exc_info:
        services.approve_loan_request(
            current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "開始日を過ぎているため、この申請は承認できません。"


# ========== 単体テストNo.4 ==========
# 同一備品について承認済み・貸出中の申請と期間が重複する場合に409エラーが発生すること
def test_approve_loan_request_004_overlapping_period_raises_409(mocker):
    mock_target_loan_request = build_mock_loan_request(
        status="申請中", start_date=dt.date.today() + dt.timedelta(days=1)
    )
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mocker.patch("app.services.crud.count_overlapping_loan_requests", return_value=1)
    mock_approve_loan_request = mocker.patch("app.services.crud.approve_loan_request")
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    with pytest.raises(HTTPException) as exc_info:
        services.approve_loan_request(
            current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "指定した期間は、既に承認済みまたは貸出中の申請と重複しています。"
    mock_approve_loan_request.assert_not_called()


# ========== 単体テストNo.5 ==========
# 期間重複の再検証で、承認対象自身を除外した上で件数を確認すること
def test_approve_loan_request_005_overlap_check_excludes_self(mocker):
    mock_target_loan_request = build_mock_loan_request(
        id=1, status="申請中", start_date=dt.date.today() + dt.timedelta(days=1)
    )
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_count_overlapping_loan_requests = mocker.patch(
        "app.services.crud.count_overlapping_loan_requests", return_value=0
    )
    mocker.patch("app.services.crud.approve_loan_request", return_value=build_mock_loan_request())
    mocker.patch("app.services.crud.create_notification")
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    services.approve_loan_request(current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1)

    assert mock_count_overlapping_loan_requests.call_args.args[4] == 1


# ========== 単体テストNo.6 ==========
# 重複がない場合に承認した管理者をログインユーザー（管理者）自身として申請が承認されること
def test_approve_loan_request_006_no_overlap_approves_with_login_admin(mocker):
    mock_target_loan_request = build_mock_loan_request(
        status="申請中", start_date=dt.date.today() + dt.timedelta(days=1)
    )
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mocker.patch("app.services.crud.count_overlapping_loan_requests", return_value=0)
    mock_approved_loan_request = build_mock_loan_request(
        status="承認済み", approved_rejected_by_user_id=1
    )
    mock_approve_loan_request = mocker.patch(
        "app.services.crud.approve_loan_request", return_value=mock_approved_loan_request
    )
    mocker.patch("app.services.crud.create_notification")
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    loan_request_response = services.approve_loan_request(
        current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1
    )

    mock_approve_loan_request.assert_called_once()
    assert mock_approve_loan_request.call_args.args[2] == 1
    assert loan_request_response.status == "承認済み"


# ========== 単体テストNo.7 ==========
# 承認成立時、申請者宛に「承認」通知が生成されること
def test_approve_loan_request_007_approval_creates_notification_to_applicant(mocker):
    mock_target_loan_request = build_mock_loan_request(
        status="申請中", start_date=dt.date.today() + dt.timedelta(days=1)
    )
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mocker.patch("app.services.crud.count_overlapping_loan_requests", return_value=0)
    mock_approved_loan_request = build_mock_loan_request(applicant_user_id=100, status="承認済み")
    mocker.patch("app.services.crud.approve_loan_request", return_value=mock_approved_loan_request)
    mock_create_notification = mocker.patch("app.services.crud.create_notification")
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    services.approve_loan_request(current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1)

    mock_create_notification.assert_called_once()
    called_args = mock_create_notification.call_args.args
    assert called_args[1] == 100
    assert called_args[2] == "承認"


# ==================================================
# 通知既読化
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：mark_notification_as_read_by_recipient
# テスト仕様書：test_specification/unit_test_specification/貸出申請・承認/通知既読化_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象通知が存在しない場合に404エラーが発生すること
def test_mark_notification_as_read_by_recipient_001_target_notification_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_notification_by_id", return_value=None)
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.mark_notification_as_read_by_recipient(
            current_user=mock_current_user, db=mocker.Mock(), notification_id=1
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された通知が見つかりません。"


# ========== 単体テストNo.2 ==========
# 対象の通知の宛先がログインユーザー自身でない場合に404エラーが発生すること
def test_mark_notification_as_read_by_recipient_002_others_notification_raises_404(mocker):
    mock_target_notification = build_mock_notification(recipient_user_id=999)
    mocker.patch("app.services.crud.get_notification_by_id", return_value=mock_target_notification)
    mock_current_user = SimpleNamespace(id=100, role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.mark_notification_as_read_by_recipient(
            current_user=mock_current_user, db=mocker.Mock(), notification_id=1
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された通知が見つかりません。"


# ========== 単体テストNo.3 ==========
# 対象の通知の宛先がログインユーザー自身の場合は既読化できること
def test_mark_notification_as_read_by_recipient_003_own_notification_marks_as_read(mocker):
    mock_target_notification = build_mock_notification(recipient_user_id=100)
    mocker.patch("app.services.crud.get_notification_by_id", return_value=mock_target_notification)
    mock_read_notification = build_mock_notification(recipient_user_id=100, read_flag=True)
    mock_mark_notification_as_read = mocker.patch(
        "app.services.crud.mark_notification_as_read", return_value=mock_read_notification
    )
    mock_current_user = SimpleNamespace(id=100, role="一般")

    notification_response = services.mark_notification_as_read_by_recipient(
        current_user=mock_current_user, db=mocker.Mock(), notification_id=1
    )

    mock_mark_notification_as_read.assert_called_once()
    assert notification_response.read_flag is True
