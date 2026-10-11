import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import services

# ==================================================
# ログイン処理
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：login
# テスト仕様書：test_specification/unit_test_specification/認証・ユーザー管理/ログイン処理_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# ユーザーが取得できない場合、タイミングサイドチャネル対策としてダミー照合を行った上で401エラーが発生すること
def test_login_001_user_not_found_raises_401(mocker):
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=None)
    mock_hash_password = mocker.patch("app.services.auth.hash_password", return_value="dummy-hash")
    mock_verify_password = mocker.patch("app.services.auth.verify_password")

    with pytest.raises(HTTPException) as exc_info:
        services.login(db=mocker.Mock(), user_id="u001", password="Password123")

    mock_hash_password.assert_called_once_with("Password123")
    mock_verify_password.assert_called_once_with("Password123", "dummy-hash")
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "ユーザーIDかパスワードが間違っています。"


# ========== 単体テストNo.2 ==========
# ロック解除日時が現在日時より後の場合に401エラーが発生すること
def test_login_002_locked_user_raises_401(mocker):
    locked_until = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5)
    mock_user = SimpleNamespace(locked_until=locked_until)
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_user)

    with pytest.raises(HTTPException) as exc_info:
        services.login(db=mocker.Mock(), user_id="u001", password="Password123")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == (
        "ログイン試行回数が上限に達したため、アカウントが一時的にロックされています。"
        "しばらくしてから再度お試しください。"
    )


# ========== 単体テストNo.3 ==========
# パスワード不一致かつ加算後の失敗回数が5未満の場合、ロック解除日時を変更せず401エラーが発生すること
def test_login_003_wrong_password_below_lock_threshold_raises_401(mocker):
    mock_user = SimpleNamespace(
        user_id="u001",
        locked_until=None,
        login_failure_count=2,
        hashed_password="hashed",
        token_generation=1,
        password_change_required_flag=False,
    )
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_user)
    mocker.patch("app.services.auth.verify_password", return_value=False)
    mock_update_login_result = mocker.patch("app.services.crud.update_user_login_result")

    with pytest.raises(HTTPException) as exc_info:
        services.login(db=mocker.Mock(), user_id="u001", password="WrongPassword")

    _, _, called_user_id, called_failure_count, called_locked_until = mock_update_login_result.call_args.args
    assert called_user_id == "u001"
    assert called_failure_count == 3
    assert called_locked_until is None
    assert exc_info.value.status_code == 401


# ========== 単体テストNo.4 ==========
# パスワード不一致かつ加算後の失敗回数が5に達した場合、ロック解除日時に現在日時+15分が設定されること
def test_login_004_wrong_password_reaching_lock_threshold_sets_locked_until(mocker):
    mock_user = SimpleNamespace(
        user_id="u001",
        locked_until=None,
        login_failure_count=4,
        hashed_password="hashed",
        token_generation=1,
        password_change_required_flag=False,
    )
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_user)
    mocker.patch("app.services.auth.verify_password", return_value=False)
    mock_update_login_result = mocker.patch("app.services.crud.update_user_login_result")

    with pytest.raises(HTTPException) as exc_info:
        services.login(db=mocker.Mock(), user_id="u001", password="WrongPassword")

    _, called_now, called_user_id, called_failure_count, called_locked_until = (
        mock_update_login_result.call_args.args
    )
    assert called_user_id == "u001"
    assert called_failure_count == 5
    assert called_locked_until == called_now + dt.timedelta(minutes=15)
    assert exc_info.value.status_code == 401


# ========== 単体テストNo.5 ==========
# 認証に成功した場合、失敗回数・ロック解除日時がリセットされトークンが発行されること
def test_login_005_successful_authentication_returns_token(mocker):
    mock_user = SimpleNamespace(
        user_id="u001",
        locked_until=None,
        login_failure_count=3,
        hashed_password="hashed",
        token_generation=2,
        password_change_required_flag=False,
    )
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_user)
    mocker.patch("app.services.auth.verify_password", return_value=True)
    mock_update_login_result = mocker.patch("app.services.crud.update_user_login_result")
    mocker.patch("app.services.auth.create_access_token", return_value="access-token")

    token_response = services.login(db=mocker.Mock(), user_id="u001", password="Password123")

    _, _, called_user_id, called_failure_count, called_locked_until = mock_update_login_result.call_args.args
    assert called_user_id == "u001"
    assert called_failure_count == 0
    assert called_locked_until is None
    assert token_response.access_token == "access-token"
    assert token_response.token_type == "bearer"
    assert token_response.password_change_required is False


# ==================================================
# ログアウト処理
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：logout
# テスト仕様書：test_specification/unit_test_specification/認証・ユーザー管理/ログアウト処理_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# トークン世代を+1し、有効フラグは変更前の値を維持して更新すること
def test_logout_001_increments_token_generation(mocker):
    mock_user = SimpleNamespace(user_id="u001", active_flag=True, token_generation=3)
    mock_update_active_flag = mocker.patch("app.services.crud.update_user_active_flag")

    result = services.logout(db=mocker.Mock(), current_user=mock_user)

    _, _, called_user_id, called_active_flag, called_token_generation = (
        mock_update_active_flag.call_args.args
    )
    assert called_user_id == "u001"
    assert called_active_flag is True
    assert called_token_generation == 4
    assert result is None


# ==================================================
# パスワード変更処理
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：change_password
# テスト仕様書：test_specification/unit_test_specification/認証・ユーザー管理/パスワード変更処理_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 現在のパスワードが一致しない場合に400エラーが発生すること
def test_change_password_001_current_password_mismatch_raises_400(mocker):
    mock_user = SimpleNamespace(user_id="u001", hashed_password="hashed", token_generation=1)
    mocker.patch("app.services.auth.verify_password", return_value=False)

    with pytest.raises(HTTPException) as exc_info:
        services.change_password(
            db=mocker.Mock(), current_user=mock_user, current_password="Wrong", new_password="New"
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "現在のパスワードが正しくありません。"


# ========== 単体テストNo.2 ==========
# 現在のパスワードが一致する場合、新しいパスワードへ更新しトークンを再発行すること
def test_change_password_002_matching_current_password_updates_and_reissues_token(mocker):
    mock_user = SimpleNamespace(user_id="u001", hashed_password="hashed", token_generation=2)
    mocker.patch("app.services.auth.verify_password", return_value=True)
    mocker.patch("app.services.auth.hash_password", return_value="new-hashed")
    mock_update_password = mocker.patch("app.services.crud.update_user_password")
    mocker.patch("app.services.auth.create_access_token", return_value="access-token")

    token_response = services.change_password(
        db=mocker.Mock(), current_user=mock_user, current_password="Current", new_password="New"
    )

    (
        _,
        _,
        called_user_id,
        called_hashed_password,
        called_change_required,
        called_token_generation,
    ) = mock_update_password.call_args.args
    assert called_user_id == "u001"
    assert called_hashed_password == "new-hashed"
    assert called_change_required is False
    assert called_token_generation == 3
    assert token_response.access_token == "access-token"
    assert token_response.token_type == "bearer"
    assert token_response.password_change_required is False


# ==================================================
# パスワード初期化
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：reset_password
# テスト仕様書：test_specification/unit_test_specification/認証・ユーザー管理/パスワード初期化_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象ユーザーが存在しない場合に404エラーが発生すること
def test_reset_password_001_target_user_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        services.reset_password(db=mocker.Mock(), user_id="u001", initial_password="Initial123")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定されたユーザーが見つかりません。"


# ========== 単体テストNo.2 ==========
# 対象ユーザーが存在する場合、初回パスワード変更要否フラグをtrueに設定しトークン世代を進めて更新すること
def test_reset_password_002_target_user_found_updates_password_and_flag(mocker):
    mock_target_user = SimpleNamespace(user_id="u001", token_generation=1)
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_target_user)
    mocker.patch("app.services.auth.hash_password", return_value="new-hashed")
    mock_updated_user = SimpleNamespace(
        user_id="u001",
        name="テスト太郎",
        department="総務部",
        role="一般",
        active_flag=True,
        password_change_required_flag=True,
        updated_at=dt.datetime.now(dt.UTC),
    )
    mock_update_password = mocker.patch(
        "app.services.crud.update_user_password", return_value=mock_updated_user
    )

    user_response = services.reset_password(
        db=mocker.Mock(), user_id="u001", initial_password="Initial123"
    )

    (
        _,
        _,
        called_user_id,
        called_hashed_password,
        called_change_required,
        called_token_generation,
    ) = mock_update_password.call_args.args
    assert called_user_id == "u001"
    assert called_hashed_password == "new-hashed"
    assert called_change_required is True
    assert called_token_generation == 2
    assert user_response.user_id == mock_updated_user.user_id
    assert user_response.name == mock_updated_user.name
    assert user_response.department == mock_updated_user.department
    assert user_response.role == mock_updated_user.role
    assert user_response.active_flag == mock_updated_user.active_flag
    assert user_response.password_change_required_flag is True
    assert user_response.updated_at == mock_updated_user.updated_at


# ==================================================
# ユーザー編集
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：update_user_info
# テスト仕様書：test_specification/unit_test_specification/認証・ユーザー管理/ユーザー編集_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象ユーザーが存在しない場合に404エラーが発生すること
def test_update_user_info_001_target_user_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        services.update_user_info(
            db=mocker.Mock(), user_id="u001", name="テスト太郎", department="総務部", role="一般"
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定されたユーザーが見つかりません。"


# ========== 単体テストNo.2 ==========
# 対象が有効な管理者で、ロールを一般に変更しようとした場合に、有効な管理者が1人のときは409エラーが発生すること
def test_update_user_info_002_last_active_admin_to_general_raises_409(mocker):
    mock_target_user = SimpleNamespace(user_id="u001", role="管理者", active_flag=True, token_generation=1)
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_target_user)
    mocker.patch("app.services.crud.count_active_admin", return_value=1)

    with pytest.raises(HTTPException) as exc_info:
        services.update_user_info(
            db=mocker.Mock(), user_id="u001", name="テスト太郎", department="総務部", role="一般"
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "最後の管理者のロールを変更することはできません。"


# ========== 単体テストNo.3 ==========
# 対象が有効な管理者で、ロールを一般に変更しようとした場合でも、有効な管理者が2人以上のときは変更できること
def test_update_user_info_003_other_active_admins_exist_allows_change(mocker):
    mock_target_user = SimpleNamespace(user_id="u001", role="管理者", active_flag=True, token_generation=1)
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_target_user)
    mocker.patch("app.services.crud.count_active_admin", return_value=2)
    mock_updated_user = SimpleNamespace(
        user_id="u001",
        name="テスト太郎",
        department="総務部",
        role="一般",
        active_flag=True,
        password_change_required_flag=False,
        updated_at=dt.datetime.now(dt.UTC),
    )
    mock_update_user = mocker.patch("app.services.crud.update_user", return_value=mock_updated_user)

    user_response = services.update_user_info(
        db=mocker.Mock(), user_id="u001", name="テスト太郎", department="総務部", role="一般"
    )

    called_token_generation = mock_update_user.call_args.args[-1]
    assert called_token_generation == 2
    assert user_response.user_id == mock_updated_user.user_id
    assert user_response.name == mock_updated_user.name
    assert user_response.department == mock_updated_user.department
    assert user_response.role == mock_updated_user.role
    assert user_response.active_flag == mock_updated_user.active_flag
    assert user_response.password_change_required_flag == mock_updated_user.password_change_required_flag
    assert user_response.updated_at == mock_updated_user.updated_at


# ========== 単体テストNo.4 ==========
# 対象ユーザーの有効フラグがfalseの場合は保護確認をスキップすること
def test_update_user_info_004_inactive_admin_skips_protection_check(mocker):
    mock_target_user = SimpleNamespace(user_id="u001", role="管理者", active_flag=False, token_generation=1)
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_target_user)
    mock_count_active_admin = mocker.patch("app.services.crud.count_active_admin")
    mock_updated_user = SimpleNamespace(
        user_id="u001",
        name="テスト太郎",
        department="総務部",
        role="一般",
        active_flag=False,
        password_change_required_flag=False,
        updated_at=dt.datetime.now(dt.UTC),
    )
    mocker.patch("app.services.crud.update_user", return_value=mock_updated_user)

    user_response = services.update_user_info(
        db=mocker.Mock(), user_id="u001", name="テスト太郎", department="総務部", role="一般"
    )

    mock_count_active_admin.assert_not_called()
    assert user_response.user_id == mock_updated_user.user_id
    assert user_response.name == mock_updated_user.name
    assert user_response.department == mock_updated_user.department
    assert user_response.role == mock_updated_user.role
    assert user_response.active_flag == mock_updated_user.active_flag
    assert user_response.password_change_required_flag == mock_updated_user.password_change_required_flag
    assert user_response.updated_at == mock_updated_user.updated_at


# ========== 単体テストNo.5 ==========
# ロールに変更がある場合、トークン世代を+1すること
def test_update_user_info_005_role_changed_increments_token_generation(mocker):
    mock_target_user = SimpleNamespace(user_id="u001", role="一般", active_flag=True, token_generation=1)
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_target_user)
    mock_updated_user = SimpleNamespace(
        user_id="u001",
        name="テスト太郎",
        department="総務部",
        role="管理者",
        active_flag=True,
        password_change_required_flag=False,
        updated_at=dt.datetime.now(dt.UTC),
    )
    mock_update_user = mocker.patch("app.services.crud.update_user", return_value=mock_updated_user)

    user_response = services.update_user_info(
        db=mocker.Mock(), user_id="u001", name="テスト太郎", department="総務部", role="管理者"
    )

    called_token_generation = mock_update_user.call_args.args[-1]
    assert called_token_generation == 2
    assert user_response.user_id == mock_updated_user.user_id
    assert user_response.name == mock_updated_user.name
    assert user_response.department == mock_updated_user.department
    assert user_response.role == mock_updated_user.role
    assert user_response.active_flag == mock_updated_user.active_flag
    assert user_response.password_change_required_flag == mock_updated_user.password_change_required_flag
    assert user_response.updated_at == mock_updated_user.updated_at


# ========== 単体テストNo.6 ==========
# ロールに変更がない場合、トークン世代を維持すること
def test_update_user_info_006_role_unchanged_keeps_token_generation(mocker):
    mock_target_user = SimpleNamespace(user_id="u001", role="一般", active_flag=True, token_generation=1)
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_target_user)
    mock_updated_user = SimpleNamespace(
        user_id="u001",
        name="テスト太郎",
        department="総務部",
        role="一般",
        active_flag=True,
        password_change_required_flag=False,
        updated_at=dt.datetime.now(dt.UTC),
    )
    mock_update_user = mocker.patch("app.services.crud.update_user", return_value=mock_updated_user)

    user_response = services.update_user_info(
        db=mocker.Mock(), user_id="u001", name="テスト太郎", department="総務部", role="一般"
    )

    called_token_generation = mock_update_user.call_args.args[-1]
    assert called_token_generation == 1
    assert user_response.user_id == mock_updated_user.user_id
    assert user_response.name == mock_updated_user.name
    assert user_response.department == mock_updated_user.department
    assert user_response.role == mock_updated_user.role
    assert user_response.active_flag == mock_updated_user.active_flag
    assert user_response.password_change_required_flag == mock_updated_user.password_change_required_flag
    assert user_response.updated_at == mock_updated_user.updated_at


# ==================================================
# ユーザー無効化
# テスト対象ファイル：services.py
# テスト対象クラス：-
# テスト対象メソッド：deactivate_user
# テスト仕様書：test_specification/unit_test_specification/認証・ユーザー管理/ユーザー無効化_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 対象ユーザーが存在しない場合に404エラーが発生すること
def test_deactivate_user_001_target_user_not_found_raises_404(mocker):
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        services.deactivate_user(db=mocker.Mock(), user_id="u001")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "指定されたユーザーが見つかりません。"


# ========== 単体テストNo.2 ==========
# 対象が有効な管理者で、有効な管理者が1人のときは409エラーが発生すること
def test_deactivate_user_002_last_active_admin_raises_409(mocker):
    mock_target_user = SimpleNamespace(user_id="u001", role="管理者", active_flag=True, token_generation=1)
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_target_user)
    mocker.patch("app.services.crud.count_active_admin", return_value=1)

    with pytest.raises(HTTPException) as exc_info:
        services.deactivate_user(db=mocker.Mock(), user_id="u001")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "最後の管理者を無効化することはできません。"


# ========== 単体テストNo.3 ==========
# 対象が有効な管理者でも、有効な管理者が2人以上のときは無効化できること
def test_deactivate_user_003_other_active_admins_exist_allows_deactivation(mocker):
    mock_target_user = SimpleNamespace(user_id="u001", role="管理者", active_flag=True, token_generation=1)
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_target_user)
    mocker.patch("app.services.crud.count_active_admin", return_value=2)
    mock_updated_user = SimpleNamespace(
        user_id="u001",
        name="テスト太郎",
        department="総務部",
        role="管理者",
        active_flag=False,
        password_change_required_flag=False,
        updated_at=dt.datetime.now(dt.UTC),
    )
    mock_update_active_flag = mocker.patch(
        "app.services.crud.update_user_active_flag", return_value=mock_updated_user
    )

    user_response = services.deactivate_user(db=mocker.Mock(), user_id="u001")

    _, _, called_user_id, called_active_flag, called_token_generation = (
        mock_update_active_flag.call_args.args
    )
    assert called_user_id == "u001"
    assert called_active_flag is False
    assert called_token_generation == 2
    assert user_response.user_id == mock_updated_user.user_id
    assert user_response.name == mock_updated_user.name
    assert user_response.department == mock_updated_user.department
    assert user_response.role == mock_updated_user.role
    assert user_response.active_flag == mock_updated_user.active_flag
    assert user_response.password_change_required_flag == mock_updated_user.password_change_required_flag
    assert user_response.updated_at == mock_updated_user.updated_at


# ========== 単体テストNo.4 ==========
# 対象ユーザーのロールが管理者でない場合は保護確認をスキップすること
def test_deactivate_user_004_general_user_skips_protection_check(mocker):
    mock_target_user = SimpleNamespace(user_id="u001", role="一般", active_flag=True, token_generation=1)
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_target_user)
    mock_count_active_admin = mocker.patch("app.services.crud.count_active_admin")
    mock_updated_user = SimpleNamespace(
        user_id="u001",
        name="テスト太郎",
        department="総務部",
        role="一般",
        active_flag=False,
        password_change_required_flag=False,
        updated_at=dt.datetime.now(dt.UTC),
    )
    mock_update_active_flag = mocker.patch(
        "app.services.crud.update_user_active_flag", return_value=mock_updated_user
    )

    user_response = services.deactivate_user(db=mocker.Mock(), user_id="u001")

    mock_count_active_admin.assert_not_called()
    mock_update_active_flag.assert_called_once()
    assert user_response.user_id == mock_updated_user.user_id
    assert user_response.name == mock_updated_user.name
    assert user_response.department == mock_updated_user.department
    assert user_response.role == mock_updated_user.role
    assert user_response.active_flag == mock_updated_user.active_flag
    assert user_response.password_change_required_flag == mock_updated_user.password_change_required_flag
    assert user_response.updated_at == mock_updated_user.updated_at


# ========== 単体テストNo.5 ==========
# 対象ユーザーの有効フラグがfalseの場合は保護確認をスキップすること
def test_deactivate_user_005_inactive_admin_skips_protection_check(mocker):
    mock_target_user = SimpleNamespace(user_id="u001", role="管理者", active_flag=False, token_generation=1)
    mocker.patch("app.services.crud.get_user_by_user_id", return_value=mock_target_user)
    mock_count_active_admin = mocker.patch("app.services.crud.count_active_admin")
    mock_updated_user = SimpleNamespace(
        user_id="u001",
        name="テスト太郎",
        department="総務部",
        role="管理者",
        active_flag=False,
        password_change_required_flag=False,
        updated_at=dt.datetime.now(dt.UTC),
    )
    mocker.patch("app.services.crud.update_user_active_flag", return_value=mock_updated_user)

    user_response = services.deactivate_user(db=mocker.Mock(), user_id="u001")

    mock_count_active_admin.assert_not_called()
    assert user_response.user_id == mock_updated_user.user_id
    assert user_response.name == mock_updated_user.name
    assert user_response.department == mock_updated_user.department
    assert user_response.role == mock_updated_user.role
    assert user_response.active_flag == mock_updated_user.active_flag
    assert user_response.password_change_required_flag == mock_updated_user.password_change_required_flag
    assert user_response.updated_at == mock_updated_user.updated_at
