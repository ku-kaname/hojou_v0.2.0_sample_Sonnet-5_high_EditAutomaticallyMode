import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import services

# ==================================================
# 備品詳細取得
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：get_equipment
# テスト仕様書：test_specification/unit_test_specification/備品管理/備品詳細取得_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象備品が存在しない場合に404エラーが発生すること
def test_get_equipment_001_target_equipment_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=None)
    mock_current_user = SimpleNamespace(role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.get_equipment(current_user=mock_current_user, db=mocker.Mock(), equipment_id=1)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された備品が見つかりません。"


# ========== 単体テストNo.2 ==========
# 一般ユーザーが無効化済み備品を取得しようとした場合に404エラーが発生すること
def test_get_equipment_002_general_user_inactive_equipment_raises_404(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=False)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_current_user = SimpleNamespace(role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.get_equipment(current_user=mock_current_user, db=mocker.Mock(), equipment_id=1)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された備品が見つかりません。"


# ========== 単体テストNo.3 ==========
# 管理者が無効化済み備品を取得する場合はアクセス制御をスキップして取得できること
def test_get_equipment_003_admin_inactive_equipment_skips_access_control(mocker):
    now = dt.datetime.now(dt.UTC)
    mock_target_equipment = SimpleNamespace(
        id=1,
        asset_number="A-001",
        name="ノートPC",
        category="PC",
        description="",
        location="",
        active_flag=False,
        created_at=now,
        updated_at=now,
    )
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mocker.patch("app.services.crud.get_reservations_by_equipment_id", return_value=[])
    mock_current_user = SimpleNamespace(role="管理者")

    equipment_response = services.get_equipment(
        current_user=mock_current_user, db=mocker.Mock(), equipment_id=1
    )

    assert equipment_response.equipment_id == 1
    assert equipment_response.active_flag is False


# ========== 単体テストNo.4 ==========
# 状態"貸出中"の予約が存在する場合、貸出状況="貸出中"・返却予定日が設定されること
def test_get_equipment_004_loaned_reservation_exists_sets_loan_status(mocker):
    now = dt.datetime.now(dt.UTC)
    due_date = dt.date(2026, 11, 1)
    mock_target_equipment = SimpleNamespace(
        id=1,
        asset_number="A-001",
        name="ノートPC",
        category="PC",
        description="",
        location="",
        active_flag=True,
        created_at=now,
        updated_at=now,
    )
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_reservation = SimpleNamespace(status="貸出中", due_date=due_date)
    mocker.patch("app.services.crud.get_reservations_by_equipment_id", return_value=[mock_reservation])
    mock_current_user = SimpleNamespace(role="一般")

    equipment_response = services.get_equipment(
        current_user=mock_current_user, db=mocker.Mock(), equipment_id=1
    )

    assert equipment_response.loan_status == "貸出中"
    assert equipment_response.due_date == due_date


# ========== 単体テストNo.5 ==========
# 状態"貸出中"の予約が存在しない場合、貸出状況="貸出可"・返却予定日がnullとなること
def test_get_equipment_005_no_loaned_reservation_sets_available_status(mocker):
    now = dt.datetime.now(dt.UTC)
    mock_target_equipment = SimpleNamespace(
        id=1,
        asset_number="A-001",
        name="ノートPC",
        category="PC",
        description="",
        location="",
        active_flag=True,
        created_at=now,
        updated_at=now,
    )
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mocker.patch("app.services.crud.get_reservations_by_equipment_id", return_value=[])
    mock_current_user = SimpleNamespace(role="一般")

    equipment_response = services.get_equipment(
        current_user=mock_current_user, db=mocker.Mock(), equipment_id=1
    )

    assert equipment_response.loan_status == "貸出可"
    assert equipment_response.due_date is None


# ==================================================
# 備品予約状況確認
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：get_equipment_reservations
# テスト仕様書：test_specification/unit_test_specification/備品管理/備品予約状況確認_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象備品が存在しない場合に404エラーが発生すること
def test_get_equipment_reservations_001_target_equipment_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=None)
    mock_current_user = SimpleNamespace(role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.get_equipment_reservations(
            current_user=mock_current_user, db=mocker.Mock(), equipment_id=1
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された備品が見つかりません。"


# ========== 単体テストNo.2 ==========
# 一般ユーザーが無効化済み備品の予約状況を確認しようとした場合に404エラーが発生すること
def test_get_equipment_reservations_002_general_user_inactive_equipment_raises_404(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=False)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_current_user = SimpleNamespace(role="一般")

    with pytest.raises(HTTPException) as exc_info:
        services.get_equipment_reservations(
            current_user=mock_current_user, db=mocker.Mock(), equipment_id=1
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された備品が見つかりません。"


# ========== 単体テストNo.3 ==========
# 管理者が無効化済み備品の予約状況を確認する場合はアクセス制御をスキップして取得できること
def test_get_equipment_reservations_003_admin_inactive_equipment_skips_access_control(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=False)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mocker.patch("app.services.crud.get_reservations_by_equipment_id", return_value=[])
    mock_current_user = SimpleNamespace(role="管理者")

    reservation_list = services.get_equipment_reservations(
        current_user=mock_current_user, db=mocker.Mock(), equipment_id=1
    )

    assert reservation_list == []


# ========== 単体テストNo.4 ==========
# ログインユーザーが管理者の場合、借用者氏名がレスポンスに含まれること
def test_get_equipment_reservations_004_admin_includes_applicant_name(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=True)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_reservation = SimpleNamespace(
        id=1,
        start_date=dt.date(2026, 10, 1),
        due_date=dt.date(2026, 10, 10),
        status="貸出中",
        applicant_name="テスト太郎",
    )
    mocker.patch("app.services.crud.get_reservations_by_equipment_id", return_value=[mock_reservation])
    mock_current_user = SimpleNamespace(role="管理者")

    reservation_list = services.get_equipment_reservations(
        current_user=mock_current_user, db=mocker.Mock(), equipment_id=1
    )

    assert reservation_list[0].applicant_name == "テスト太郎"


# ========== 単体テストNo.5 ==========
# ログインユーザーが一般ユーザーの場合、借用者氏名がレスポンスに含まれないこと
def test_get_equipment_reservations_005_general_user_excludes_applicant_name(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=True)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_reservation = SimpleNamespace(
        id=1,
        start_date=dt.date(2026, 10, 1),
        due_date=dt.date(2026, 10, 10),
        status="貸出中",
        applicant_name="テスト太郎",
    )
    mocker.patch("app.services.crud.get_reservations_by_equipment_id", return_value=[mock_reservation])
    mock_current_user = SimpleNamespace(role="一般")

    reservation_list = services.get_equipment_reservations(
        current_user=mock_current_user, db=mocker.Mock(), equipment_id=1
    )

    assert reservation_list[0].applicant_name is None


# ========== 単体テストNo.6 ==========
# 対象備品の予約が1件もない場合、空のリストが返却されること
def test_get_equipment_reservations_006_no_reservations_returns_empty_list(mocker):
    mock_target_equipment = SimpleNamespace(active_flag=True)
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mocker.patch("app.services.crud.get_reservations_by_equipment_id", return_value=[])
    mock_current_user = SimpleNamespace(role="一般")

    reservation_list = services.get_equipment_reservations(
        current_user=mock_current_user, db=mocker.Mock(), equipment_id=1
    )

    assert reservation_list == []


# ==================================================
# 備品編集
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：update_equipment
# テスト仕様書：test_specification/unit_test_specification/備品管理/備品編集_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象備品が存在しない場合に404エラーが発生すること
def test_update_equipment_001_target_equipment_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        services.update_equipment(
            db=mocker.Mock(),
            equipment_id=1,
            asset_number="A-001",
            name="ノートPC",
            category="PC",
            description="",
            location="",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定された備品が見つかりません。"


# ========== 単体テストNo.2 ==========
# 資産番号を変更しようとした場合に、変更後の資産番号が既存の別備品と重複していれば409エラーが発生すること
def test_update_equipment_002_asset_number_changed_duplicate_raises_409(mocker):
    mock_target_equipment = SimpleNamespace(asset_number="A-001")
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_duplicate_equipment = SimpleNamespace(asset_number="A-002")
    mock_get_equipment_by_asset_number = mocker.patch(
        "app.services.crud.get_equipment_by_asset_number", return_value=mock_duplicate_equipment
    )
    mock_update_equipment = mocker.patch("app.services.crud.update_equipment")

    with pytest.raises(HTTPException) as exc_info:
        services.update_equipment(
            db=mocker.Mock(),
            equipment_id=1,
            asset_number="A-002",
            name="ノートPC",
            category="PC",
            description="",
            location="",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "この資産番号は既に使用されています。"
    mock_get_equipment_by_asset_number.assert_called_once()
    mock_update_equipment.assert_not_called()


# ========== 単体テストNo.3 ==========
# 資産番号を変更する場合でも、重複がなければ更新できること
def test_update_equipment_003_asset_number_changed_no_duplicate_updates(mocker):
    now = dt.datetime.now(dt.UTC)
    mock_target_equipment = SimpleNamespace(asset_number="A-001")
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_get_equipment_by_asset_number = mocker.patch(
        "app.services.crud.get_equipment_by_asset_number", return_value=None
    )
    mock_updated_equipment = SimpleNamespace(
        id=1,
        asset_number="A-002",
        name="ノートPC",
        category="PC",
        description="",
        location="",
        active_flag=True,
        created_at=now,
        updated_at=now,
    )
    mock_update_equipment = mocker.patch(
        "app.services.crud.update_equipment", return_value=mock_updated_equipment
    )
    mocker.patch("app.services.crud.get_reservations_by_equipment_id", return_value=[])

    equipment_response = services.update_equipment(
        db=mocker.Mock(),
        equipment_id=1,
        asset_number="A-002",
        name="ノートPC",
        category="PC",
        description="",
        location="",
    )

    mock_get_equipment_by_asset_number.assert_called_once()
    mock_update_equipment.assert_called_once()
    assert mock_update_equipment.call_args.args[3] == "A-002"
    assert equipment_response.asset_number == "A-002"


# ========== 単体テストNo.4 ==========
# 資産番号に変更がない場合は重複確認をスキップすること
def test_update_equipment_004_asset_number_unchanged_skips_duplicate_check(mocker):
    now = dt.datetime.now(dt.UTC)
    mock_target_equipment = SimpleNamespace(asset_number="A-001")
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_get_equipment_by_asset_number = mocker.patch(
        "app.services.crud.get_equipment_by_asset_number"
    )
    mock_updated_equipment = SimpleNamespace(
        id=1,
        asset_number="A-001",
        name="ノートPC",
        category="PC",
        description="",
        location="",
        active_flag=True,
        created_at=now,
        updated_at=now,
    )
    mocker.patch("app.services.crud.update_equipment", return_value=mock_updated_equipment)
    mocker.patch("app.services.crud.get_reservations_by_equipment_id", return_value=[])

    services.update_equipment(
        db=mocker.Mock(),
        equipment_id=1,
        asset_number="A-001",
        name="ノートPC",
        category="PC",
        description="",
        location="",
    )

    mock_get_equipment_by_asset_number.assert_not_called()


# ========== 単体テストNo.5 ==========
# 状態"貸出中"の予約が存在する場合、貸出状況="貸出中"・返却予定日が設定されること
def test_update_equipment_005_loaned_reservation_exists_sets_loan_status(mocker):
    now = dt.datetime.now(dt.UTC)
    due_date = dt.date(2026, 11, 1)
    mock_target_equipment = SimpleNamespace(asset_number="A-001")
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_updated_equipment = SimpleNamespace(
        id=1,
        asset_number="A-001",
        name="ノートPC",
        category="PC",
        description="",
        location="",
        active_flag=True,
        created_at=now,
        updated_at=now,
    )
    mocker.patch("app.services.crud.update_equipment", return_value=mock_updated_equipment)
    mock_reservation = SimpleNamespace(status="貸出中", due_date=due_date)
    mocker.patch("app.services.crud.get_reservations_by_equipment_id", return_value=[mock_reservation])

    equipment_response = services.update_equipment(
        db=mocker.Mock(),
        equipment_id=1,
        asset_number="A-001",
        name="ノートPC",
        category="PC",
        description="",
        location="",
    )

    assert equipment_response.loan_status == "貸出中"
    assert equipment_response.due_date == due_date


# ========== 単体テストNo.6 ==========
# 状態"貸出中"の予約が存在しない場合、貸出状況="貸出可"・返却予定日がnullとなること
def test_update_equipment_006_no_loaned_reservation_sets_available_status(mocker):
    now = dt.datetime.now(dt.UTC)
    mock_target_equipment = SimpleNamespace(asset_number="A-001")
    mocker.patch("app.services.crud.get_equipment_by_id", return_value=mock_target_equipment)
    mock_updated_equipment = SimpleNamespace(
        id=1,
        asset_number="A-001",
        name="ノートPC",
        category="PC",
        description="",
        location="",
        active_flag=True,
        created_at=now,
        updated_at=now,
    )
    mocker.patch("app.services.crud.update_equipment", return_value=mock_updated_equipment)
    mocker.patch("app.services.crud.get_reservations_by_equipment_id", return_value=[])

    equipment_response = services.update_equipment(
        db=mocker.Mock(),
        equipment_id=1,
        asset_number="A-001",
        name="ノートPC",
        category="PC",
        description="",
        location="",
    )

    assert equipment_response.loan_status == "貸出可"
    assert equipment_response.due_date is None


# ==================================================
# 備品CSV一括登録
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：bulk_import_equipment
# テスト仕様書：test_specification/unit_test_specification/備品管理/備品CSV一括登録_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# ファイルサイズが5MBを超える場合に400エラーが発生すること
def test_bulk_import_equipment_001_file_size_exceeds_limit_raises_400(mocker):
    file_content = b"a" * (5 * 1024 * 1024 + 1)

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    assert exc_info.value.status_code == 400
    error_list = exc_info.value.detail["error_list"]
    assert len(error_list) == 1
    assert error_list[0]["row_number"] is None
    assert error_list[0]["message"] == "ファイルサイズが上限（5MB）を超えています。"


# ========== 単体テストNo.2 ==========
# UTF-8としてデコードできないバイト列の場合に400エラーが発生すること
def test_bulk_import_equipment_002_decode_failure_raises_400(mocker):
    file_content = b"\xff\xfe"

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    assert exc_info.value.status_code == 400
    error_list = exc_info.value.detail["error_list"]
    assert error_list[0]["message"] == "ファイルの文字コードが不正です。UTF-8で保存してください。"


# ========== 単体テストNo.3 ==========
# ヘッダー行の列数が5でない場合に400エラーが発生すること
def test_bulk_import_equipment_003_invalid_header_column_count_raises_400(mocker):
    file_content = "資産番号,備品名,分類,説明".encode()

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    assert exc_info.value.status_code == 400
    error_list = exc_info.value.detail["error_list"]
    assert error_list[0]["message"] == (
        "ヘッダー行の列構成が不正です。列は資産番号・備品名・分類・説明・保管場所の順にしてください。"
    )


# ========== 単体テストNo.4 ==========
# データ行数が1,000を超える場合に400エラーが発生すること
def test_bulk_import_equipment_004_data_row_count_exceeds_limit_raises_400(mocker):
    header = "資産番号,備品名,分類,説明,保管場所"
    data_row = "A-001,ノートPC,PC,,"
    file_content = "\n".join([header] + [data_row] * 1001).encode("utf-8")

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    assert exc_info.value.status_code == 400
    error_list = exc_info.value.detail["error_list"]
    assert error_list[0]["message"] == "データ行数が上限（1,000行）を超えています。"


# ========== 単体テストNo.5 ==========
# データ行の列数が5でない場合、そのエラーのみ収集し以降（資産番号重複チェック等）の検証を当該行について行わないこと
def test_bulk_import_equipment_005_invalid_column_count_row_excluded_from_duplicate_check(mocker):
    header = "資産番号,備品名,分類,説明,保管場所"
    invalid_row = "A-001,ノートPC,PC,説明"  # 4列
    valid_row = "A-002,モニター,PC,,"
    file_content = "\n".join([header, invalid_row, valid_row]).encode("utf-8")
    mock_get_existing_asset_numbers = mocker.patch(
        "app.services.crud.get_existing_asset_numbers", return_value=[]
    )

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    error_list = exc_info.value.detail["error_list"]
    assert any(
        error["row_number"] == 1 and error["message"] == "列数が不正です。" for error in error_list
    )
    called_asset_number_list = mock_get_existing_asset_numbers.call_args.args[1]
    assert "A-001" not in called_asset_number_list


# ========== 単体テストNo.6 ==========
# 資産番号が空・32桁超・半角英数字と-以外の文字を含むのいずれかの場合に該当行をエラー一覧へ追加すること
def test_bulk_import_equipment_006_invalid_asset_number_length_adds_error(mocker):
    header = "資産番号,備品名,分類,説明,保管場所"
    invalid_asset_number = "A" * 33
    data_row = f"{invalid_asset_number},ノートPC,PC,,"
    file_content = "\n".join([header, data_row]).encode("utf-8")
    mocker.patch("app.services.crud.get_existing_asset_numbers", return_value=[])

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    error_list = exc_info.value.detail["error_list"]
    assert any(
        error["row_number"] == 1 and error["message"] == "資産番号が不正です。" for error in error_list
    )


# ========== 単体テストNo.7 ==========
# 備品名が空または100桁超の場合に該当行をエラー一覧へ追加すること
def test_bulk_import_equipment_007_invalid_name_length_adds_error(mocker):
    header = "資産番号,備品名,分類,説明,保管場所"
    invalid_name = "あ" * 101
    data_row = f"A-001,{invalid_name},PC,,"
    file_content = "\n".join([header, data_row]).encode("utf-8")
    mocker.patch("app.services.crud.get_existing_asset_numbers", return_value=[])

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    error_list = exc_info.value.detail["error_list"]
    assert any(
        error["row_number"] == 1 and error["message"] == "備品名が不正です。" for error in error_list
    )


# ========== 単体テストNo.8 ==========
# 分類が空または50桁超の場合に該当行をエラー一覧へ追加すること
def test_bulk_import_equipment_008_invalid_category_length_adds_error(mocker):
    header = "資産番号,備品名,分類,説明,保管場所"
    invalid_category = "あ" * 51
    data_row = f"A-001,ノートPC,{invalid_category},,"
    file_content = "\n".join([header, data_row]).encode("utf-8")
    mocker.patch("app.services.crud.get_existing_asset_numbers", return_value=[])

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    error_list = exc_info.value.detail["error_list"]
    assert any(
        error["row_number"] == 1 and error["message"] == "分類が不正です。" for error in error_list
    )


# ========== 単体テストNo.9 ==========
# 説明が500桁超の場合に該当行をエラー一覧へ追加すること
def test_bulk_import_equipment_009_invalid_description_length_adds_error(mocker):
    header = "資産番号,備品名,分類,説明,保管場所"
    invalid_description = "あ" * 501
    data_row = f"A-001,ノートPC,PC,{invalid_description},"
    file_content = "\n".join([header, data_row]).encode("utf-8")
    mocker.patch("app.services.crud.get_existing_asset_numbers", return_value=[])

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    error_list = exc_info.value.detail["error_list"]
    assert any(
        error["row_number"] == 1 and error["message"] == "説明が不正です。" for error in error_list
    )


# ========== 単体テストNo.10 ==========
# 保管場所が100桁超の場合に該当行をエラー一覧へ追加すること
def test_bulk_import_equipment_010_invalid_location_length_adds_error(mocker):
    header = "資産番号,備品名,分類,説明,保管場所"
    invalid_location = "あ" * 101
    data_row = f"A-001,ノートPC,PC,,{invalid_location}"
    file_content = "\n".join([header, data_row]).encode("utf-8")
    mocker.patch("app.services.crud.get_existing_asset_numbers", return_value=[])

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    error_list = exc_info.value.detail["error_list"]
    assert any(
        error["row_number"] == 1 and error["message"] == "保管場所が不正です。" for error in error_list
    )


# ========== 単体テストNo.11 ==========
# 同じ資産番号が複数のデータ行に出現する場合、最初に出現した行を除く2件目以降の行番号をエラー一覧へ追加すること
def test_bulk_import_equipment_011_duplicate_asset_number_within_csv_adds_error_for_second_occurrence(
    mocker,
):
    header = "資産番号,備品名,分類,説明,保管場所"
    data_row_1 = "A-001,ノートPC,PC,,"
    data_row_2 = "A-001,モニター,PC,,"
    file_content = "\n".join([header, data_row_1, data_row_2]).encode("utf-8")
    mocker.patch("app.services.crud.get_existing_asset_numbers", return_value=[])

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    error_list = exc_info.value.detail["error_list"]
    duplicate_error_list = [error for error in error_list if error["message"] == "資産番号が重複しています。"]
    assert len(duplicate_error_list) == 1
    assert duplicate_error_list[0]["row_number"] == 2


# ========== 単体テストNo.12 ==========
# データベースに既に登録済みの資産番号の場合、該当行をエラー一覧へ追加すること
def test_bulk_import_equipment_012_duplicate_asset_number_in_db_adds_error(mocker):
    header = "資産番号,備品名,分類,説明,保管場所"
    data_row = "A-001,ノートPC,PC,,"
    file_content = "\n".join([header, data_row]).encode("utf-8")
    mocker.patch("app.services.crud.get_existing_asset_numbers", return_value=["A-001"])

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    error_list = exc_info.value.detail["error_list"]
    assert any(
        error["row_number"] == 1 and error["message"] == "この資産番号は既に使用されています。"
        for error in error_list
    )


# ========== 単体テストNo.13 ==========
# 検証エラーが複数件ある場合、全件を登録せず行番号の昇順に整列したエラー一覧を返却すること
def test_bulk_import_equipment_013_multiple_errors_sorted_ascending_by_row_number(mocker):
    header = "資産番号,備品名,分類,説明,保管場所"
    row_1 = "A-001,ノートPC,PC,,"
    row_2 = "A-001,モニター,PC,,"  # 行2：行1との資産番号重複（重複チェック段で追加されるエラー）
    row_3 = ",キーボード,PC,,"  # 行3：資産番号が空（項目検証段で追加されるエラー）
    file_content = "\n".join([header, row_1, row_2, row_3]).encode("utf-8")
    mocker.patch("app.services.crud.get_existing_asset_numbers", return_value=[])
    mock_bulk_create_equipment = mocker.patch("app.services.crud.bulk_create_equipment")

    with pytest.raises(HTTPException) as exc_info:
        services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    mock_bulk_create_equipment.assert_not_called()
    error_list = exc_info.value.detail["error_list"]
    row_number_list = [error["row_number"] for error in error_list]
    assert row_number_list == [2, 3]


# ========== 単体テストNo.14 ==========
# 検証エラーが1件もない場合、全データ行を一括登録し、
# 貸出状況="貸出可"固定・返却予定日=null固定でレスポンスを返却すること
def test_bulk_import_equipment_014_valid_csv_bulk_creates_equipment(mocker):
    header = "資産番号,備品名,分類,説明,保管場所"
    row_1 = "A-001,ノートPC,PC,,"
    row_2 = "A-002,モニター,PC,,"
    file_content = "\n".join([header, row_1, row_2]).encode("utf-8")
    mocker.patch("app.services.crud.get_existing_asset_numbers", return_value=[])
    now = dt.datetime.now(dt.UTC)
    mock_created_equipment_list = [
        SimpleNamespace(
            id=1,
            asset_number="A-001",
            name="ノートPC",
            category="PC",
            description="",
            location="",
            active_flag=True,
            created_at=now,
            updated_at=now,
        ),
        SimpleNamespace(
            id=2,
            asset_number="A-002",
            name="モニター",
            category="PC",
            description="",
            location="",
            active_flag=True,
            created_at=now,
            updated_at=now,
        ),
    ]
    mock_bulk_create_equipment = mocker.patch(
        "app.services.crud.bulk_create_equipment", return_value=mock_created_equipment_list
    )

    bulk_import_response = services.bulk_import_equipment(db=mocker.Mock(), file_content=file_content)

    mock_bulk_create_equipment.assert_called_once()
    called_equipment_create_list = mock_bulk_create_equipment.call_args.args[2]
    assert len(called_equipment_create_list) == 2
    assert bulk_import_response.registered_count == 2
    assert bulk_import_response.equipment_list[0].loan_status == "貸出可"
    assert bulk_import_response.equipment_list[0].due_date is None
    assert bulk_import_response.equipment_list[1].asset_number == "A-002"
