import datetime as dt
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

from app import auth

# ==================================================
# パスワードハッシュ化
# テスト対象ファイル：auth.py
# テスト対象クラス：-
# テスト対象メソッド：hash_password
# テスト仕様書：test_specification/unit_test_specification/認証・認可（auth）/パスワードハッシュ化_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 平文パスワードをハッシュ化すること
def test_hash_password_001_hash_result_format():
    hashed_password = auth.hash_password("Password123")

    assert hashed_password != "Password123"
    assert hashed_password.startswith("$argon2id$")


# ========== 単体テストNo.2 ==========
# ソルトにより、同じ平文でも毎回異なるハッシュ値が生成されること
def test_hash_password_002_salt_makes_result_non_deterministic():
    first_hashed_password = auth.hash_password("Password123")
    second_hashed_password = auth.hash_password("Password123")

    assert first_hashed_password != second_hashed_password


# ==================================================
# パスワード検証
# テスト対象ファイル：auth.py
# テスト対象クラス：-
# テスト対象メソッド：verify_password
# テスト仕様書：test_specification/unit_test_specification/認証・認可（auth）/パスワード検証_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 平文とハッシュ済みパスワードが一致する場合にTrueを返すこと
def test_verify_password_001_matching_password_returns_true():
    hashed_password = auth.hash_password("Password123")

    assert auth.verify_password("Password123", hashed_password) is True


# ========== 単体テストNo.2 ==========
# 平文とハッシュ済みパスワードが一致しない場合にFalseを返すこと
def test_verify_password_002_mismatched_password_returns_false():
    hashed_password = auth.hash_password("Password123")

    assert auth.verify_password("WrongPassword", hashed_password) is False


# ==================================================
# トークン発行
# テスト対象ファイル：auth.py
# テスト対象クラス：-
# テスト対象メソッド：create_access_token
# テスト仕様書：test_specification/unit_test_specification/認証・認可（auth）/トークン発行_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 発行したトークンをデコードすると、ユーザーID・トークン世代・有効期限が正しく設定されていること
def test_create_access_token_001_payload_contains_user_id_and_generation():
    access_token = auth.create_access_token(user_id="u001", token_generation=1)

    payload = jwt.decode(access_token, auth.JWT_SECRET_KEY, algorithms=[auth.JWT_ALGORITHM])

    assert payload["sub"] == "u001"
    assert payload["tgen"] == 1
    assert payload["exp"] > dt.datetime.now(dt.UTC).timestamp()


# ==================================================
# 有効ユーザー検証
# テスト対象ファイル：auth.py
# テスト対象クラス：-
# テスト対象メソッド：get_current_active_user
# テスト仕様書：test_specification/unit_test_specification/認証・認可（auth）/有効ユーザー検証_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 署名不正・期限切れ等でデコードに失敗する場合に401エラーが発生すること
def test_get_current_active_user_001_decode_failure_raises_401(mocker):
    mocker.patch("app.auth.jwt.decode", side_effect=jwt.PyJWTError)

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_active_user(token="invalid-token", db=mocker.Mock())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "資格情報を検証できませんでした"


# ========== 単体テストNo.2 ==========
# デコード結果のsubが存在しない場合に401エラーが発生すること
def test_get_current_active_user_002_missing_sub_raises_401(mocker):
    mocker.patch("app.auth.jwt.decode", return_value={"tgen": 1})

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_active_user(token="token", db=mocker.Mock())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "資格情報を検証できませんでした"


# ========== 単体テストNo.3 ==========
# デコード結果のtgenが存在しない場合に401エラーが発生すること
def test_get_current_active_user_003_missing_token_generation_raises_401(mocker):
    mocker.patch("app.auth.jwt.decode", return_value={"sub": "u001"})

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_active_user(token="token", db=mocker.Mock())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "資格情報を検証できませんでした"


# ========== 単体テストNo.4 ==========
# crud.get_user_by_user_idがNoneを返す場合に401エラーが発生すること
def test_get_current_active_user_004_user_not_found_raises_401(mocker):
    mocker.patch("app.auth.jwt.decode", return_value={"sub": "u001", "tgen": 1})
    mocker.patch("app.auth.crud.get_user_by_user_id", return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_active_user(token="token", db=mocker.Mock())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "資格情報を検証できませんでした"


# ========== 単体テストNo.5 ==========
# 取得したユーザーのactive_flagがFalseの場合に401エラーが発生すること
def test_get_current_active_user_005_inactive_user_raises_401(mocker):
    mocker.patch("app.auth.jwt.decode", return_value={"sub": "u001", "tgen": 1})
    mock_user = SimpleNamespace(active_flag=False, token_generation=1)
    mocker.patch("app.auth.crud.get_user_by_user_id", return_value=mock_user)

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_active_user(token="token", db=mocker.Mock())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "資格情報を検証できませんでした"


# ========== 単体テストNo.6 ==========
# トークンのtgenとDB上のtoken_generationが異なる場合に401エラーが発生すること
def test_get_current_active_user_006_token_generation_mismatch_raises_401(mocker):
    mocker.patch("app.auth.jwt.decode", return_value={"sub": "u001", "tgen": 1})
    mock_user = SimpleNamespace(active_flag=True, token_generation=2)
    mocker.patch("app.auth.crud.get_user_by_user_id", return_value=mock_user)

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_active_user(token="token", db=mocker.Mock())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "資格情報を検証できませんでした"


# ========== 単体テストNo.7 ==========
# トークンが有効かつユーザーが有効・世代一致の場合にユーザーを返すこと
def test_get_current_active_user_007_valid_token_returns_user(mocker):
    mocker.patch("app.auth.jwt.decode", return_value={"sub": "u001", "tgen": 1})
    mock_user = SimpleNamespace(active_flag=True, token_generation=1)
    mocker.patch("app.auth.crud.get_user_by_user_id", return_value=mock_user)

    current_user = auth.get_current_active_user(token="token", db=mocker.Mock())

    assert current_user is mock_user


# ==================================================
# 管理者権限検証
# テスト対象ファイル：auth.py
# テスト対象クラス：-
# テスト対象メソッド：require_admin
# テスト仕様書：test_specification/unit_test_specification/認証・認可（auth）/管理者権限検証_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# ロールが"管理者"でない場合に403エラーが発生すること
def test_require_admin_001_non_admin_role_raises_403():
    non_admin_user = SimpleNamespace(role="利用者")

    with pytest.raises(HTTPException) as exc_info:
        auth.require_admin(current_user=non_admin_user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "この操作には管理者権限が必要です。"


# ========== 単体テストNo.2 ==========
# ロールが"管理者"の場合にユーザーを返すこと
def test_require_admin_002_admin_role_returns_user():
    admin_user = SimpleNamespace(role="管理者")

    current_admin = auth.require_admin(current_user=admin_user)

    assert current_admin is admin_user


# ==================================================
# 初回パスワード変更チェック
# テスト対象ファイル：auth.py
# テスト対象クラス：-
# テスト対象メソッド：require_password_changed
# テスト仕様書：test_specification/unit_test_specification/認証・認可（auth）/
#   初回パスワード変更チェック_単体テスト仕様書.md
# ==================================================


# ========== 単体テストNo.1 ==========
# 初回パスワード変更要否フラグがTrueの場合に403エラーが発生すること
def test_require_password_changed_001_change_required_raises_403():
    user_requiring_change = SimpleNamespace(password_change_required_flag=True)

    with pytest.raises(HTTPException) as exc_info:
        auth.require_password_changed(current_user=user_requiring_change)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "初回パスワード変更が完了していません。パスワードを変更してください。"


# ========== 単体テストNo.2 ==========
# 初回パスワード変更要否フラグがFalseの場合にユーザーを返すこと
def test_require_password_changed_002_change_not_required_returns_user():
    user_not_requiring_change = SimpleNamespace(password_change_required_flag=False)

    current_user = auth.require_password_changed(current_user=user_not_requiring_change)

    assert current_user is user_not_requiring_change
