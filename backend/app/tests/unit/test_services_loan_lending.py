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


# 備品レスポンスの元になるcrud層レスポンス（Equipment相当）のモックを組み立てる。
def build_mock_equipment(**overrides):
    defaults = {
        "id": 1,
        "active_flag": True,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# export_loan_requests_csvの戻り値（UTF-8 BOM付きバイト列）をデコードし、行・セル単位に分解する。
def decode_csv_rows(csv_bytes):
    csv_text = csv_bytes.decode("utf-8-sig")
    return [line.split(",") for line in csv_text.split("\n")]


# ==================================================
# 貸出処理
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：lend_loan_request
# テスト仕様書：test_specification/unit_test_specification/貸出・返却・履歴/貸出処理_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象貸出申請が存在しない場合に404エラーが発生すること
def test_lend_loan_request_001_target_loan_request_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=None)
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    with pytest.raises(HTTPException) as exc_info:
        services.lend_loan_request(
            current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された貸出申請が見つかりません。"


# ========== 単体テストNo.2 ==========
# 対象の申請の状態が「承認済み」でない場合に409エラーが発生すること
def test_lend_loan_request_002_status_not_approved_raises_409(mocker):
    mock_target_loan_request = build_mock_loan_request(status="申請中")
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    with pytest.raises(HTTPException) as exc_info:
        services.lend_loan_request(
            current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "この申請は現在の状態では貸出処理できません。"


# ========== 単体テストNo.3 ==========
# 対象の申請の開始日が今日より後の場合に409エラーが発生すること
def test_lend_loan_request_003_start_date_after_today_raises_409(mocker):
    mock_target_loan_request = build_mock_loan_request(
        status="承認済み", start_date=dt.date.today() + dt.timedelta(days=1)
    )
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    with pytest.raises(HTTPException) as exc_info:
        services.lend_loan_request(
            current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "開始日前のため、この申請は貸出処理できません。"


# ========== 単体テストNo.4 ==========
# 対象備品の有効フラグがfalseの場合に409エラーが発生すること
def test_lend_loan_request_004_inactive_equipment_raises_409(mocker):
    mock_target_loan_request = build_mock_loan_request(status="承認済み", start_date=dt.date.today())
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mocker.patch(
        "app.services.crud.get_equipment_by_id",
        return_value=build_mock_equipment(active_flag=False),
    )
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    with pytest.raises(HTTPException) as exc_info:
        services.lend_loan_request(
            current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "指定された備品は無効化されているため、貸出処理できません。"


# ========== 単体テストNo.5 ==========
# 同一備品について貸出中の別申請と期間が重複する場合に409エラーが発生すること
def test_lend_loan_request_005_overlapping_period_raises_409(mocker):
    mock_target_loan_request = build_mock_loan_request(status="承認済み", start_date=dt.date.today())
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mocker.patch(
        "app.services.crud.get_equipment_by_id",
        return_value=build_mock_equipment(active_flag=True),
    )
    mocker.patch("app.services.crud.count_overlapping_loan_requests", return_value=1)
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    with pytest.raises(HTTPException) as exc_info:
        services.lend_loan_request(
            current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "同一備品について、貸出中の別申請が存在するため貸出処理できません。"


# ========== 単体テストNo.6 ==========
# 期間重複の再検証で、貸出処理対象自身を除外した上で件数を確認すること
def test_lend_loan_request_006_overlap_check_excludes_self(mocker):
    mock_target_loan_request = build_mock_loan_request(
        id=1, status="承認済み", start_date=dt.date.today()
    )
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mocker.patch(
        "app.services.crud.get_equipment_by_id",
        return_value=build_mock_equipment(active_flag=True),
    )
    mock_count_overlapping_loan_requests = mocker.patch(
        "app.services.crud.count_overlapping_loan_requests", return_value=0
    )
    mocker.patch("app.services.crud.lend_loan_request", return_value=build_mock_loan_request())
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    services.lend_loan_request(current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1)

    assert mock_count_overlapping_loan_requests.call_args.args[4] == 1


# ========== 単体テストNo.7 ==========
# 重複がない場合に貸出処理した管理者をログインユーザー（管理者）自身として申請が貸出中に更新されること
def test_lend_loan_request_007_no_overlap_lends_with_login_admin(mocker):
    mock_target_loan_request = build_mock_loan_request(status="承認済み", start_date=dt.date.today())
    mocker.patch("app.services.crud.get_loan_request_by_id", return_value=mock_target_loan_request)
    mocker.patch(
        "app.services.crud.get_equipment_by_id",
        return_value=build_mock_equipment(active_flag=True),
    )
    mocker.patch("app.services.crud.count_overlapping_loan_requests", return_value=0)
    mock_lent_loan_request = build_mock_loan_request(status="貸出中", lent_by_user_id=1)
    mock_lend_loan_request = mocker.patch(
        "app.services.crud.lend_loan_request", return_value=mock_lent_loan_request
    )
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    loan_request_response = services.lend_loan_request(
        current_admin=mock_current_admin, db=mocker.Mock(), loan_request_id=1
    )

    assert mock_lend_loan_request.call_args.args[2] == mock_current_admin.id
    assert loan_request_response.lent_by_user_id == 1


# ==================================================
# 貸出履歴CSV出力
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：export_loan_requests_csv
# テスト仕様書：test_specification/unit_test_specification/貸出・返却・履歴/貸出履歴CSV出力_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 入力値（開始日範囲・備品・申請者）が検索条件として正しく渡されること
def test_export_loan_requests_csv_001_passes_search_conditions(mocker):
    mock_db = mocker.Mock()
    mock_search_loan_requests = mocker.patch(
        "app.services.crud.search_loan_requests", return_value=[]
    )
    mock_current_admin = SimpleNamespace(id=1, role="管理者")
    start_date_from = dt.date(2026, 9, 1)
    start_date_to = dt.date(2026, 9, 30)

    services.export_loan_requests_csv(
        current_admin=mock_current_admin,
        db=mock_db,
        start_date_from=start_date_from,
        start_date_to=start_date_to,
        equipment_id=1,
        applicant_user_id=100,
    )

    call_args = mock_search_loan_requests.call_args.args
    assert call_args[0] is mock_db
    assert call_args[1] == 100
    assert call_args[2] is None
    assert call_args[6] == 1
    assert call_args[7] == start_date_from
    assert call_args[8] == start_date_to


# ========== 単体テストNo.2 ==========
# 貸出履歴検索結果が0件の場合、ヘッダー行のみのCSVが出力されること
def test_export_loan_requests_csv_002_no_results_returns_header_only(mocker):
    mocker.patch("app.services.crud.search_loan_requests", return_value=[])
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    csv_bytes = services.export_loan_requests_csv(
        current_admin=mock_current_admin,
        db=mocker.Mock(),
        start_date_from=None,
        start_date_to=None,
        equipment_id=None,
        applicant_user_id=None,
    )

    expected_header = (
        "loan_request_id,equipment_id,applicant_user_id,start_date,due_date,"
        "purpose,status,reject_cancel_reason,approved_rejected_by_user_id,"
        "lent_by_user_id,returned_by_user_id,cancelled_by_user_id,requested_at,"
        "approved_rejected_at,lent_at,returned_at,cancelled_at,return_note"
    )
    assert csv_bytes.decode("utf-8-sig") == expected_header


# ========== 単体テストNo.3 ==========
# セルの値の先頭が「=」の場合、シングルクォートを付与して無害化すること
def test_export_loan_requests_csv_003_sanitizes_leading_equals(mocker):
    mock_loan_request = build_mock_loan_request(purpose="=SUM(A1:A2)")
    mocker.patch("app.services.crud.search_loan_requests", return_value=[mock_loan_request])
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    csv_bytes = services.export_loan_requests_csv(
        current_admin=mock_current_admin,
        db=mocker.Mock(),
        start_date_from=None,
        start_date_to=None,
        equipment_id=None,
        applicant_user_id=None,
    )

    rows = decode_csv_rows(csv_bytes)
    assert rows[1][5] == "'=SUM(A1:A2)"


# ========== 単体テストNo.4 ==========
# セルの値の先頭が「+」の場合、シングルクォートを付与して無害化すること
def test_export_loan_requests_csv_004_sanitizes_leading_plus(mocker):
    mock_loan_request = build_mock_loan_request(purpose="+1234")
    mocker.patch("app.services.crud.search_loan_requests", return_value=[mock_loan_request])
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    csv_bytes = services.export_loan_requests_csv(
        current_admin=mock_current_admin,
        db=mocker.Mock(),
        start_date_from=None,
        start_date_to=None,
        equipment_id=None,
        applicant_user_id=None,
    )

    rows = decode_csv_rows(csv_bytes)
    assert rows[1][5] == "'+1234"


# ========== 単体テストNo.5 ==========
# セルの値の先頭が「-」の場合、シングルクォートを付与して無害化すること
def test_export_loan_requests_csv_005_sanitizes_leading_minus(mocker):
    mock_loan_request = build_mock_loan_request(purpose="-1234")
    mocker.patch("app.services.crud.search_loan_requests", return_value=[mock_loan_request])
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    csv_bytes = services.export_loan_requests_csv(
        current_admin=mock_current_admin,
        db=mocker.Mock(),
        start_date_from=None,
        start_date_to=None,
        equipment_id=None,
        applicant_user_id=None,
    )

    rows = decode_csv_rows(csv_bytes)
    assert rows[1][5] == "'-1234"


# ========== 単体テストNo.6 ==========
# セルの値の先頭が「@」の場合、シングルクォートを付与して無害化すること
def test_export_loan_requests_csv_006_sanitizes_leading_at(mocker):
    mock_loan_request = build_mock_loan_request(purpose="@SUM(A1:A2)")
    mocker.patch("app.services.crud.search_loan_requests", return_value=[mock_loan_request])
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    csv_bytes = services.export_loan_requests_csv(
        current_admin=mock_current_admin,
        db=mocker.Mock(),
        start_date_from=None,
        start_date_to=None,
        equipment_id=None,
        applicant_user_id=None,
    )

    rows = decode_csv_rows(csv_bytes)
    assert rows[1][5] == "'@SUM(A1:A2)"


# ========== 単体テストNo.7 ==========
# セルの値の先頭が無害化対象外の文字列の場合、変更せずそのまま出力すること
def test_export_loan_requests_csv_007_leaves_non_sanitize_target_unchanged(mocker):
    mock_loan_request = build_mock_loan_request(purpose="社内研修用")
    mocker.patch("app.services.crud.search_loan_requests", return_value=[mock_loan_request])
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    csv_bytes = services.export_loan_requests_csv(
        current_admin=mock_current_admin,
        db=mocker.Mock(),
        start_date_from=None,
        start_date_to=None,
        equipment_id=None,
        applicant_user_id=None,
    )

    rows = decode_csv_rows(csv_bytes)
    assert rows[1][5] == "社内研修用"


# ========== 単体テストNo.8 ==========
# null許容項目が未設定の場合、空文字列としてセルに設定されること
def test_export_loan_requests_csv_008_nullable_fields_become_empty_string(mocker):
    mock_loan_request = build_mock_loan_request()
    mocker.patch("app.services.crud.search_loan_requests", return_value=[mock_loan_request])
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    csv_bytes = services.export_loan_requests_csv(
        current_admin=mock_current_admin,
        db=mocker.Mock(),
        start_date_from=None,
        start_date_to=None,
        equipment_id=None,
        applicant_user_id=None,
    )

    rows = decode_csv_rows(csv_bytes)
    # null許容項目：reject_cancel_reason・approved_rejected_by_user_id・lent_by_user_id・
    # returned_by_user_id・cancelled_by_user_id・approved_rejected_at・lent_at・returned_at・
    # cancelled_at・return_noteの各セル
    nullable_cell_indexes = [7, 8, 9, 10, 11, 13, 14, 15, 16, 17]
    assert [rows[1][index] for index in nullable_cell_indexes] == [""] * len(nullable_cell_indexes)


# ========== 単体テストNo.9 ==========
# CSV文字列がUTF-8（BOM付き）でエンコードされたバイト列として返却されること
def test_export_loan_requests_csv_009_encoded_as_utf8_bom(mocker):
    mock_loan_request = build_mock_loan_request(purpose="社内研修用")
    mocker.patch("app.services.crud.search_loan_requests", return_value=[mock_loan_request])
    mock_current_admin = SimpleNamespace(id=1, role="管理者")

    csv_bytes = services.export_loan_requests_csv(
        current_admin=mock_current_admin,
        db=mocker.Mock(),
        start_date_from=None,
        start_date_to=None,
        equipment_id=None,
        applicant_user_id=None,
    )

    assert csv_bytes[:3] == b"\xef\xbb\xbf"
    csv_bytes.decode("utf-8-sig")
