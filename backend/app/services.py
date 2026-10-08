"""
オーケストレーション処理

【概要】
エンドポイント層・日次バッチ共通処理からの呼び出しを受け、データアクセス層・共通処理を呼び出して業務処理を行う
"""

import datetime as dt
import os
import re

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import auth, crud
from app.models import User
from app.schemas import (
    EquipmentBulkImportErrorDetail,
    EquipmentBulkImportErrorResponse,
    EquipmentBulkImportResponse,
    EquipmentResponse,
    ReservationResponse,
    TokenResponse,
    UserCreateResponse,
    UserGetResponse,
    UserUpdateResponse,
)

# ====================================================================================================
# ログイン・ログアウト
# - login : ログイン処理
# - logout : ログアウト処理

# 設計書：
# - 設計書/services/認証・ユーザー管理/ログイン処理_v0.2.0.md
# - 設計書/services/認証・ユーザー管理/ログアウト処理_v0.2.0.md
# ====================================================================================================


def login(db: Session, user_id: str, password: str) -> TokenResponse:
    """
    ログイン処理

    設計書：設計書/services/認証・ユーザー管理/ログイン処理_v0.2.0.md

    【処理概要】
    - ユーザーID・パスワードによる認証を行い、成功時にアクセストークンを発行する

    【パラメータ】
    - db (Session) : データベース (必須)
    - user_id (str) : ユーザーID (必須)
    - password (str) : パスワード (必須)

    【戻り値】
    - token_response (TokenResponse) : トークン発行レスポンス

    【例外処理】
    - HTTPException(401) : ユーザーが取得できない場合
    - HTTPException(401) : ロック解除日時が現在日時より後の場合
    - HTTPException(401) : パスワード照合結果がfalseの場合

    【処理フロー】
    1. 現在日時取得
    2. ユーザーの存在確認
    3. ロック状態の確認
    4. パスワードの照合
    5. 認証失敗時のログイン結果更新
    6. 認証成功時のログイン結果更新
    7. アクセストークンの発行
    8. 戻り値を返却
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="ユーザーIDかパスワードが間違っています。",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. ユーザーの存在確認
    # 2.(1) ユーザー情報をDBから取得する
    user = crud.get_user_by_user_id(db, user_id)

    # 2.(2) 例外処理：ユーザーが取得できない（タイミングサイドチャネル対策）
    if user is None:
        auth.verify_password(password, auth.hash_password(password))
        raise credentials_exception

    # 3. ロック状態の確認
    # 3.(1).① 例外処理：ロック解除日時が現在日時より後
    if user.locked_until is not None and user.locked_until > now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ログイン試行回数が上限に達したため、アカウントが一時的にロックされています。しばらくしてから再度お試しください。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. パスワードの照合
    is_valid = auth.verify_password(password, user.hashed_password)
    if not is_valid:
        # 5. 認証失敗時のログイン結果更新
        login_failure_count = user.login_failure_count + 1
        locked_until = user.locked_until
        if login_failure_count >= 5:
            locked_until = now + dt.timedelta(minutes=15)
        crud.update_user_login_result(db, now, user_id, login_failure_count, locked_until)
        raise credentials_exception

    # 6. 認証成功時のログイン結果更新
    crud.update_user_login_result(db, now, user_id, 0, None)

    # 7. アクセストークンの発行
    access_token = auth.create_access_token(user_id, user.token_generation)

    # 8. 戻り値を返却
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        password_change_required=user.password_change_required_flag,
    )


def logout(db: Session, current_user: User) -> None:
    """
    ログアウト処理

    設計書：設計書/services/認証・ユーザー管理/ログアウト処理_v0.2.0.md

    【処理概要】
    - トークン世代を+1することで、発行済みのアクセストークンを以降の有効ユーザー検証で無効とする

    【パラメータ】
    - db (Session) : データベース (必須)
    - current_user (User) : ログインユーザー検証結果 (必須)

    【戻り値】
    - なし

    【例外処理】
    - なし

    【処理フロー】
    1. 現在日時取得
    2. トークン世代更新
    3. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. トークン世代更新
    crud.update_user_active_flag(
        db, now, current_user.user_id, current_user.active_flag, current_user.token_generation + 1
    )

    # 3. 戻り値を返却（なし）
    return None


# ====================================================================================================
# パスワード変更・初期化
# - change_password : パスワード変更処理
# - reset_password : パスワード初期化

# 設計書：
# - 設計書/services/認証・ユーザー管理/パスワード変更処理_v0.2.0.md
# - 設計書/services/認証・ユーザー管理/パスワード初期化_v0.2.0.md
# ====================================================================================================


def change_password(
    db: Session, current_user: User, current_password: str, new_password: str
) -> TokenResponse:
    """
    パスワード変更処理

    設計書：設計書/services/認証・ユーザー管理/パスワード変更処理_v0.2.0.md

    【処理概要】
    - ログイン中のユーザー本人のパスワードを変更する
    - 更新によりトークン世代が進むため、新しいアクセストークンを即時発行する

    【パラメータ】
    - db (Session) : データベース (必須)
    - current_user (User) : ログインユーザー検証結果 (必須)
    - current_password (str) : 現在のパスワード (必須)
    - new_password (str) : 新しいパスワード (必須)

    【戻り値】
    - token_response (TokenResponse) : トークン発行レスポンス

    【例外処理】
    - HTTPException(400) : 現在のパスワードの照合結果がfalseの場合

    【処理フロー】
    1. 現在日時取得
    2. 現在のパスワードの照合
    3. 新しいパスワードのハッシュ化
    4. パスワードの更新
    5. アクセストークンの発行
    6. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 現在のパスワードの照合
    # 2.(2) 例外処理：照合結果がfalse
    if not auth.verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="現在のパスワードが正しくありません。",
        )

    # 3. 新しいパスワードのハッシュ化
    hashed_password = auth.hash_password(new_password)

    # 4. パスワードの更新
    new_token_generation = current_user.token_generation + 1
    crud.update_user_password(db, now, current_user.user_id, hashed_password, False, new_token_generation)

    # 5. アクセストークンの発行
    access_token = auth.create_access_token(current_user.user_id, new_token_generation)

    # 6. 戻り値を返却
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        password_change_required=False,
    )


def reset_password(db: Session, user_id: str, initial_password: str) -> UserUpdateResponse:
    """
    パスワード初期化

    設計書：設計書/services/認証・ユーザー管理/パスワード初期化_v0.2.0.md

    【処理概要】
    - 管理者が、既存ユーザーのパスワードを初期化する

    【パラメータ】
    - db (Session) : データベース (必須)
    - user_id (str) : ユーザーID (必須)
    - initial_password (str) : 初期パスワード (必須)

    【戻り値】
    - user_response (UserUpdateResponse) : ユーザー情報更新レスポンス

    【例外処理】
    - HTTPException(404) : 対象ユーザーが取得できない場合

    【処理フロー】
    1. 現在日時取得
    2. 対象ユーザー情報取得
    3. 初期パスワードのハッシュ化
    4. パスワードの更新
    5. レスポンスへの変換
    6. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 対象ユーザー情報取得
    target_user = crud.get_user_by_user_id(db, user_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定されたユーザーが見つかりません。",
        )

    # 3. 初期パスワードのハッシュ化
    hashed_password = auth.hash_password(initial_password)

    # 4. パスワードの更新
    updated_user = crud.update_user_password(
        db, now, user_id, hashed_password, True, target_user.token_generation + 1
    )
    assert updated_user is not None

    # 5. レスポンスへの変換
    user_response = UserUpdateResponse(
        user_id=updated_user.user_id,
        name=updated_user.name,
        department=updated_user.department,
        role=updated_user.role,
        active_flag=updated_user.active_flag,
        password_change_required_flag=updated_user.password_change_required_flag,
        updated_at=updated_user.updated_at,
    )

    # 6. 戻り値を返却
    return user_response


# ====================================================================================================
# ユーザー登録・編集
# - register_user : ユーザー登録
# - update_user_info : ユーザー編集

# 設計書：
# - 設計書/services/認証・ユーザー管理/ユーザー登録_v0.2.0.md
# - 設計書/services/認証・ユーザー管理/ユーザー編集_v0.2.0.md
# ====================================================================================================


def register_user(
    db: Session,
    user_id: str,
    name: str,
    department: str,
    role: str,
    initial_password: str,
) -> UserCreateResponse:
    """
    ユーザー登録

    設計書：設計書/services/認証・ユーザー管理/ユーザー登録_v0.2.0.md

    【処理概要】
    - 管理者が、新しいユーザーを登録する
    - ユーザーIDが既に使用されていないことを確認し、初期パスワードをハッシュ化してユーザーレコードを新規作成する

    【パラメータ】
    - db (Session) : データベース (必須)
    - user_id (str) : ユーザーID (必須)
    - name (str) : 氏名 (必須)
    - department (str) : 所属 (任意)
    - role (str) : ロール (必須)
    - initial_password (str) : 初期パスワード (必須)

    【戻り値】
    - user_response (UserCreateResponse) : ユーザー作成レスポンス

    【例外処理】
    - HTTPException(409) : ユーザーIDが既に使用されている場合

    【処理フロー】
    1. 現在日時取得
    2. ユーザーID重複確認
    3. 初期パスワードのハッシュ化
    4. ユーザーレコードの作成
    5. レスポンスへの変換
    6. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. ユーザーID重複確認
    # 2.(2) 例外処理：取得結果が存在する
    if crud.get_user_by_user_id(db, user_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="このユーザーIDは既に使用されています。",
        )

    # 3. 初期パスワードのハッシュ化
    hashed_password = auth.hash_password(initial_password)

    # 4. ユーザーレコードの作成
    created_user = crud.create_user(db, now, user_id, name, department, hashed_password, role)

    # 5. レスポンスへの変換
    user_response = UserCreateResponse(
        user_id=created_user.user_id,
        name=created_user.name,
        department=created_user.department,
        role=created_user.role,
        active_flag=created_user.active_flag,
        password_change_required_flag=created_user.password_change_required_flag,
        created_at=created_user.created_at,
    )

    # 6. 戻り値を返却
    return user_response


def update_user_info(
    db: Session, user_id: str, name: str, department: str, role: str
) -> UserUpdateResponse:
    """
    ユーザー編集

    設計書：設計書/services/認証・ユーザー管理/ユーザー編集_v0.2.0.md

    【処理概要】
    - 管理者が、既存ユーザーの氏名・所属・ロールを変更する
    - ロールを"管理者"から"一般"へ変更する場合、最後の有効な管理者を一般ロールへ変更できないことを確認する
    - ロールに変更がある場合はトークン世代を進める

    【パラメータ】
    - db (Session) : データベース (必須)
    - user_id (str) : ユーザーID (必須)
    - name (str) : 氏名 (必須)
    - department (str) : 所属 (任意)
    - role (str) : ロール (必須)

    【戻り値】
    - user_response (UserUpdateResponse) : ユーザー情報更新レスポンス

    【例外処理】
    - HTTPException(404) : 対象ユーザーが取得できない場合
    - HTTPException(409) : 最後の有効な管理者のロールを一般へ変更しようとした場合

    【処理フロー】
    1. 現在日時取得
    2. 対象ユーザー情報取得
    3. 最後の有効管理者保護の確認
    4. トークン世代の算出
    5. ユーザー情報更新
    6. レスポンスへの変換
    7. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 対象ユーザー情報取得
    target_user = crud.get_user_by_user_id(db, user_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定されたユーザーが見つかりません。",
        )

    # 3. 最後の有効管理者保護の確認
    if target_user.role == "管理者" and target_user.active_flag and role == "一般":
        active_admin_count = crud.count_active_admin(db)
        # 3.(3) 例外処理：有効管理者数が1
        if active_admin_count == 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="最後の管理者のロールを変更することはできません。",
            )

    # 4. トークン世代の算出
    if role != target_user.role:
        token_generation = target_user.token_generation + 1
    else:
        token_generation = target_user.token_generation

    # 5. ユーザー情報更新
    updated_user = crud.update_user(db, now, user_id, name, department, role, token_generation)
    assert updated_user is not None

    # 6. レスポンスへの変換
    user_response = UserUpdateResponse(
        user_id=updated_user.user_id,
        name=updated_user.name,
        department=updated_user.department,
        role=updated_user.role,
        active_flag=updated_user.active_flag,
        password_change_required_flag=updated_user.password_change_required_flag,
        updated_at=updated_user.updated_at,
    )

    # 7. 戻り値を返却
    return user_response


# ====================================================================================================
# ユーザー有効化状態変更
# - deactivate_user : ユーザー無効化
# - activate_user : ユーザー再有効化

# 設計書：
# - 設計書/services/認証・ユーザー管理/ユーザー無効化_v0.2.0.md
# - 設計書/services/認証・ユーザー管理/ユーザー再有効化_v0.2.0.md
# ====================================================================================================


def deactivate_user(db: Session, user_id: str) -> UserUpdateResponse:
    """
    ユーザー無効化

    設計書：設計書/services/認証・ユーザー管理/ユーザー無効化_v0.2.0.md

    【処理概要】
    - 管理者が、既存ユーザーを無効化する
    - 最後の有効な管理者を無効化できないことを確認する
    - 有効フラグをfalseに更新し、トークン世代を進めて既存トークンを失効させる

    【パラメータ】
    - db (Session) : データベース (必須)
    - user_id (str) : ユーザーID (必須)

    【戻り値】
    - user_response (UserUpdateResponse) : ユーザー情報更新レスポンス

    【例外処理】
    - HTTPException(404) : 対象ユーザーが取得できない場合
    - HTTPException(409) : 最後の有効な管理者を無効化しようとした場合

    【処理フロー】
    1. 現在日時取得
    2. 対象ユーザー情報取得
    3. 最後の有効管理者保護の確認
    4. ユーザー有効化状態更新
    5. レスポンスへの変換
    6. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 対象ユーザー情報取得
    target_user = crud.get_user_by_user_id(db, user_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定されたユーザーが見つかりません。",
        )

    # 3. 最後の有効管理者保護の確認
    if target_user.role == "管理者" and target_user.active_flag:
        active_admin_count = crud.count_active_admin(db)
        # 3.(3) 例外処理：有効管理者数が1
        if active_admin_count == 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="最後の管理者を無効化することはできません。",
            )

    # 4. ユーザー有効化状態更新
    updated_user = crud.update_user_active_flag(
        db, now, user_id, False, target_user.token_generation + 1
    )
    assert updated_user is not None

    # 5. レスポンスへの変換
    user_response = UserUpdateResponse(
        user_id=updated_user.user_id,
        name=updated_user.name,
        department=updated_user.department,
        role=updated_user.role,
        active_flag=updated_user.active_flag,
        password_change_required_flag=updated_user.password_change_required_flag,
        updated_at=updated_user.updated_at,
    )

    # 6. 戻り値を返却
    return user_response


def activate_user(db: Session, user_id: str) -> UserUpdateResponse:
    """
    ユーザー再有効化

    設計書：設計書/services/認証・ユーザー管理/ユーザー再有効化_v0.2.0.md

    【処理概要】
    - 管理者が、無効化済みのユーザーを再度有効化する
    - 有効フラグをtrueに更新する。トークン世代は更新前の値を維持する

    【パラメータ】
    - db (Session) : データベース (必須)
    - user_id (str) : ユーザーID (必須)

    【戻り値】
    - user_response (UserUpdateResponse) : ユーザー情報更新レスポンス

    【例外処理】
    - HTTPException(404) : 対象ユーザーが取得できない場合

    【処理フロー】
    1. 現在日時取得
    2. 対象ユーザー情報取得
    3. ユーザー有効化状態更新
    4. レスポンスへの変換
    5. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 対象ユーザー情報取得
    target_user = crud.get_user_by_user_id(db, user_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定されたユーザーが見つかりません。",
        )

    # 3. ユーザー有効化状態更新
    updated_user = crud.update_user_active_flag(
        db, now, user_id, True, target_user.token_generation
    )
    assert updated_user is not None

    # 4. レスポンスへの変換
    user_response = UserUpdateResponse(
        user_id=updated_user.user_id,
        name=updated_user.name,
        department=updated_user.department,
        role=updated_user.role,
        active_flag=updated_user.active_flag,
        password_change_required_flag=updated_user.password_change_required_flag,
        updated_at=updated_user.updated_at,
    )

    # 5. 戻り値を返却
    return user_response


# ====================================================================================================
# ユーザー情報取得
# - get_users : ユーザー一覧取得
# - get_user : ユーザー詳細取得
# - get_my_info : 自分の情報取得

# 設計書：
# - 設計書/services/認証・ユーザー管理/ユーザー一覧取得_v0.2.0.md
# - 設計書/services/認証・ユーザー管理/ユーザー詳細取得_v0.2.0.md
# - 設計書/services/認証・ユーザー管理/自分の情報取得_v0.2.0.md
# ====================================================================================================


def get_users(db: Session) -> list[UserGetResponse]:
    """
    ユーザー一覧取得

    設計書：設計書/services/認証・ユーザー管理/ユーザー一覧取得_v0.2.0.md

    【処理概要】
    - 登録されている全ユーザーの情報を取得する

    【パラメータ】
    - db (Session) : データベース (必須)

    【戻り値】
    - user_list (list[UserGetResponse]) : ユーザー情報取得レスポンス一覧

    【例外処理】
    - なし

    【処理フロー】
    1. 全ユーザー情報取得
    2. レスポンスへの変換
    3. 戻り値を返却
    """

    # 1. 全ユーザー情報取得
    all_user_list = crud.get_all_user(db)

    # 2. レスポンスへの変換
    user_list = [
        UserGetResponse(
            user_id=target_user.user_id,
            name=target_user.name,
            department=target_user.department,
            role=target_user.role,
            active_flag=target_user.active_flag,
            password_change_required_flag=target_user.password_change_required_flag,
            created_at=target_user.created_at,
            updated_at=target_user.updated_at,
        )
        for target_user in all_user_list
    ]

    # 3. 戻り値を返却
    return user_list


def get_user(db: Session, user_id: str) -> UserGetResponse:
    """
    ユーザー詳細取得

    設計書：設計書/services/認証・ユーザー管理/ユーザー詳細取得_v0.2.0.md

    【処理概要】
    - 管理者が、指定したユーザーの詳細情報を確認する

    【パラメータ】
    - db (Session) : データベース (必須)
    - user_id (str) : ユーザーID (必須)

    【戻り値】
    - user_response (UserGetResponse) : ユーザー情報取得レスポンス

    【例外処理】
    - HTTPException(404) : 対象ユーザーが取得できない場合

    【処理フロー】
    1. 対象ユーザー情報取得
    2. レスポンスへの変換
    3. 戻り値を返却
    """

    # 1. 対象ユーザー情報取得
    target_user = crud.get_user_by_user_id(db, user_id)

    # 1.(2) 例外処理：取得結果がNone
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定されたユーザーが見つかりません。",
        )

    # 2. レスポンスへの変換
    user_response = UserGetResponse(
        user_id=target_user.user_id,
        name=target_user.name,
        department=target_user.department,
        role=target_user.role,
        active_flag=target_user.active_flag,
        password_change_required_flag=target_user.password_change_required_flag,
        created_at=target_user.created_at,
        updated_at=target_user.updated_at,
    )

    # 3. 戻り値を返却
    return user_response


def get_my_info(current_user: User) -> UserGetResponse:
    """
    自分の情報取得

    設計書：設計書/services/認証・ユーザー管理/自分の情報取得_v0.2.0.md

    【処理概要】
    - ログイン中のユーザー本人が、自分の情報を取得する

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)

    【戻り値】
    - user_response (UserGetResponse) : ユーザー情報取得レスポンス

    【例外処理】
    - なし

    【処理フロー】
    1. レスポンスへの変換
    2. 戻り値を返却
    """

    # 1. レスポンスへの変換
    user_response = UserGetResponse(
        user_id=current_user.user_id,
        name=current_user.name,
        department=current_user.department,
        role=current_user.role,
        active_flag=current_user.active_flag,
        password_change_required_flag=current_user.password_change_required_flag,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )

    # 2. 戻り値を返却
    return user_response


# ====================================================================================================
# 初期管理者アカウント作成
# - create_initial_admin : 初期管理者アカウント作成

# 設計書：設計書/services/認証・ユーザー管理/初期管理者アカウント作成_v0.2.0.md
# ====================================================================================================


def create_initial_admin(db: Session) -> None:
    """
    初期管理者アカウント作成

    設計書：設計書/services/認証・ユーザー管理/初期管理者アカウント作成_v0.2.0.md

    【処理概要】
    - システム構築時に環境変数で指定した値で、初期管理者アカウントを起動時に自動作成する
    - 既にユーザーが存在する場合は何も行わない

    【パラメータ】
    - db (Session) : データベース (必須)

    【戻り値】
    - なし

    【例外処理】
    - なし

    【処理フロー】
    1. 環境変数から初期管理者情報取得
    2. 既存ユーザー確認
    3. パスワードハッシュ化
    4. 現在日時取得
    5. ユーザー作成
    6. 戻り値を返却
    """

    # 1. 環境変数から初期管理者情報取得
    initial_admin_user_id = os.environ["INITIAL_ADMIN_USER_ID"]
    initial_admin_name = os.environ["INITIAL_ADMIN_NAME"]
    initial_admin_password = os.environ["INITIAL_ADMIN_PASSWORD"]

    # 2. 既存ユーザー確認
    if crud.get_user_by_user_id(db, initial_admin_user_id) is not None:
        return None

    # 3. パスワードハッシュ化
    hashed_password = auth.hash_password(initial_admin_password)

    # 4. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 5. ユーザー作成
    crud.create_user(db, now, initial_admin_user_id, initial_admin_name, "", hashed_password, "管理者")

    # 6. 戻り値を返却（なし）
    return None


def _derive_loan_status_and_due_date(
    reservation_list: list[crud.ReservationResult],
) -> tuple[str, dt.date | None]:
    """
    予約情報リストから、貸出状況・返却予定日を導出する（状態="貸出中"の要素は常に最大1件）
    """

    loaned_reservation = next(
        (reservation for reservation in reservation_list if reservation.status == "貸出中"),
        None,
    )
    if loaned_reservation is None:
        return "貸出可", None
    return "貸出中", loaned_reservation.due_date


# ====================================================================================================
# 備品検索・一覧取得
# - search_equipment : 備品検索・一覧取得

# 設計書：設計書/services/備品管理/備品検索一覧取得_v0.2.0.md
# ====================================================================================================


def search_equipment(
    current_user: User,
    db: Session,
    category: str | None,
    keyword: str | None,
    loan_status: str | None,
    include_inactive: bool,
) -> list[EquipmentResponse]:
    """
    備品検索・一覧取得

    設計書：設計書/services/備品管理/備品検索一覧取得_v0.2.0.md

    【処理概要】
    - 備品を分類・キーワード・貸出状況で検索し、各備品の現在の貸出状況とともに一覧で取得する
    - 無効化済み備品は管理者のみ参照可能とする

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)
    - category (str | None) : 分類 (任意)
    - keyword (str | None) : キーワード (任意)
    - loan_status (str | None) : 貸出状況 (任意)
    - include_inactive (bool) : 無効化済み備品を含める (必須)

    【戻り値】
    - equipment_list (list[EquipmentResponse]) : 備品レスポンス一覧

    【例外処理】
    - なし

    【処理フロー】
    1. 無効化済み備品を含める条件の決定
    2. 備品検索・一覧取得
    3. レスポンスへの変換
    4. 戻り値を返却
    """

    # 1. 無効化済み備品を含める条件の決定
    include_inactive_applied = include_inactive if current_user.role == "管理者" else False

    # 2. 備品検索・一覧取得
    equipment_search_result_list = crud.search_equipment(
        db, category, keyword, loan_status, include_inactive_applied
    )

    # 3. レスポンスへの変換
    equipment_list = [
        EquipmentResponse(
            equipment_id=equipment_search_result.id,
            asset_number=equipment_search_result.asset_number,
            name=equipment_search_result.name,
            category=equipment_search_result.category,
            description=equipment_search_result.description,
            location=equipment_search_result.location,
            active_flag=equipment_search_result.active_flag,
            loan_status="貸出中" if equipment_search_result.due_date is not None else "貸出可",
            due_date=equipment_search_result.due_date,
            created_at=equipment_search_result.created_at,
            updated_at=equipment_search_result.updated_at,
        )
        for equipment_search_result in equipment_search_result_list
    ]

    # 4. 戻り値を返却
    return equipment_list


# ====================================================================================================
# 備品詳細取得
# - get_equipment : 備品詳細取得

# 設計書：設計書/services/備品管理/備品詳細取得_v0.2.0.md
# ====================================================================================================


def get_equipment(current_user: User, db: Session, equipment_id: int) -> EquipmentResponse:
    """
    備品詳細取得

    設計書：設計書/services/備品管理/備品詳細取得_v0.2.0.md

    【処理概要】
    - 指定した備品の詳細情報（現在の貸出状況を含む）を取得する
    - 無効化済み備品は管理者のみ参照可能とする

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)
    - equipment_id (int) : 備品ID (必須)

    【戻り値】
    - equipment_response (EquipmentResponse) : 備品レスポンス

    【例外処理】
    - HTTPException(404) : 対象備品が取得できない場合、または一般ユーザーが無効化済み備品を取得しようとした場合

    【処理フロー】
    1. 対象備品情報取得
    2. 無効化済み備品へのアクセス制御
    3. 貸出状況の判定
    4. レスポンスへの変換
    5. 戻り値を返却
    """

    not_found_exception = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="指定された備品が見つかりません。",
    )

    # 1. 対象備品情報取得
    target_equipment = crud.get_equipment_by_id(db, equipment_id)

    # 1.(2) 例外処理：取得結果がNone
    if target_equipment is None:
        raise not_found_exception

    # 2. 無効化済み備品へのアクセス制御
    # 2.① 例外処理：一般ユーザーかつ無効化済み備品
    if current_user.role != "管理者" and not target_equipment.active_flag:
        raise not_found_exception

    # 3. 貸出状況の判定
    reservation_list = crud.get_reservations_by_equipment_id(db, equipment_id)
    loan_status, due_date = _derive_loan_status_and_due_date(reservation_list)

    # 4. レスポンスへの変換
    equipment_response = EquipmentResponse(
        equipment_id=target_equipment.id,
        asset_number=target_equipment.asset_number,
        name=target_equipment.name,
        category=target_equipment.category,
        description=target_equipment.description,
        location=target_equipment.location,
        active_flag=target_equipment.active_flag,
        loan_status=loan_status,
        due_date=due_date,
        created_at=target_equipment.created_at,
        updated_at=target_equipment.updated_at,
    )

    # 5. 戻り値を返却
    return equipment_response


# ====================================================================================================
# 備品登録
# - create_equipment : 備品登録

# 設計書：設計書/services/備品管理/備品登録_v0.2.0.md
# ====================================================================================================


def create_equipment(
    db: Session,
    asset_number: str,
    name: str,
    category: str,
    description: str,
    location: str,
) -> EquipmentResponse:
    """
    備品登録

    設計書：設計書/services/備品管理/備品登録_v0.2.0.md

    【処理概要】
    - 資産番号の重複が無いことを確認した上で、新規備品を登録する

    【パラメータ】
    - db (Session) : データベース (必須)
    - asset_number (str) : 資産番号 (必須)
    - name (str) : 備品名 (必須)
    - category (str) : 分類 (必須)
    - description (str) : 説明 (任意)
    - location (str) : 保管場所 (任意)

    【戻り値】
    - equipment_response (EquipmentResponse) : 備品レスポンス

    【例外処理】
    - HTTPException(409) : 資産番号が既存の備品と重複する場合

    【処理フロー】
    1. 現在日時取得
    2. 資産番号重複チェック
    3. 備品情報登録
    4. レスポンスへの変換
    5. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 資産番号重複チェック
    duplicate_equipment = crud.get_equipment_by_asset_number(db, asset_number)

    # 2.(2) 例外処理：取得結果がNoneでない
    if duplicate_equipment is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="この資産番号は既に使用されています。",
        )

    # 3. 備品情報登録
    created_equipment = crud.create_equipment(db, asset_number, name, category, description, location, now)

    # 4. レスポンスへの変換
    equipment_response = EquipmentResponse(
        equipment_id=created_equipment.id,
        asset_number=created_equipment.asset_number,
        name=created_equipment.name,
        category=created_equipment.category,
        description=created_equipment.description,
        location=created_equipment.location,
        active_flag=created_equipment.active_flag,
        loan_status="貸出可",
        due_date=None,
        created_at=created_equipment.created_at,
        updated_at=created_equipment.updated_at,
    )

    # 5. 戻り値を返却
    return equipment_response


# ====================================================================================================
# 備品編集
# - update_equipment : 備品編集

# 設計書：設計書/services/備品管理/備品編集_v0.2.0.md
# ====================================================================================================


def update_equipment(
    db: Session,
    equipment_id: int,
    asset_number: str,
    name: str,
    category: str,
    description: str,
    location: str,
) -> EquipmentResponse:
    """
    備品編集

    設計書：設計書/services/備品管理/備品編集_v0.2.0.md

    【処理概要】
    - 既存備品の資産番号・備品名・分類・説明・保管場所を変更する

    【パラメータ】
    - db (Session) : データベース (必須)
    - equipment_id (int) : 備品ID (必須)
    - asset_number (str) : 資産番号 (必須)
    - name (str) : 備品名 (必須)
    - category (str) : 分類 (必須)
    - description (str) : 説明 (任意)
    - location (str) : 保管場所 (任意)

    【戻り値】
    - equipment_response (EquipmentResponse) : 備品レスポンス

    【例外処理】
    - HTTPException(404) : 対象備品が取得できない場合
    - HTTPException(409) : 変更後の資産番号が対象備品以外の既存備品と重複する場合

    【処理フロー】
    1. 現在日時取得
    2. 対象備品情報取得
    3. 資産番号重複チェック
    4. 備品情報更新
    5. 備品予約状況取得
    6. 貸出状況・返却予定日の導出
    7. レスポンスへの変換
    8. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 対象備品情報取得
    target_equipment = crud.get_equipment_by_id(db, equipment_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定された備品が見つかりません。",
        )

    # 3. 資産番号重複チェック
    # 3.① 資産番号に変更がある場合のみ重複確認を行う
    if asset_number != target_equipment.asset_number:
        duplicate_equipment = crud.get_equipment_by_asset_number(db, asset_number)

        # 3.(3) 例外処理：取得結果がNoneでない
        if duplicate_equipment is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="この資産番号は既に使用されています。",
            )

    # 4. 備品情報更新
    updated_equipment = crud.update_equipment(
        db, now, equipment_id, asset_number, name, category, description, location
    )
    assert updated_equipment is not None

    # 5. 備品予約状況取得
    reservation_list = crud.get_reservations_by_equipment_id(db, equipment_id)

    # 6. 貸出状況・返却予定日の導出
    loan_status, due_date = _derive_loan_status_and_due_date(reservation_list)

    # 7. レスポンスへの変換
    equipment_response = EquipmentResponse(
        equipment_id=updated_equipment.id,
        asset_number=updated_equipment.asset_number,
        name=updated_equipment.name,
        category=updated_equipment.category,
        description=updated_equipment.description,
        location=updated_equipment.location,
        active_flag=updated_equipment.active_flag,
        loan_status=loan_status,
        due_date=due_date,
        created_at=updated_equipment.created_at,
        updated_at=updated_equipment.updated_at,
    )

    # 8. 戻り値を返却
    return equipment_response


# ====================================================================================================
# 備品無効化・再有効化
# - deactivate_equipment : 備品無効化
# - activate_equipment : 備品再有効化

# 設計書：
# - 設計書/services/備品管理/備品無効化_v0.2.0.md
# - 設計書/services/備品管理/備品再有効化_v0.2.0.md
# ====================================================================================================


def deactivate_equipment(db: Session, equipment_id: int) -> EquipmentResponse:
    """
    備品無効化

    設計書：設計書/services/備品管理/備品無効化_v0.2.0.md

    【処理概要】
    - 既存備品を無効化する

    【パラメータ】
    - db (Session) : データベース (必須)
    - equipment_id (int) : 備品ID (必須)

    【戻り値】
    - equipment_response (EquipmentResponse) : 備品レスポンス

    【例外処理】
    - HTTPException(404) : 対象備品が取得できない場合

    【処理フロー】
    1. 現在日時取得
    2. 対象備品情報取得
    3. 備品有効化状態更新
    4. 備品予約状況取得
    5. 貸出状況・返却予定日の導出
    6. レスポンスへの変換
    7. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 対象備品情報取得
    target_equipment = crud.get_equipment_by_id(db, equipment_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定された備品が見つかりません。",
        )

    # 3. 備品有効化状態更新
    updated_equipment = crud.update_equipment_active_flag(db, now, equipment_id, False)
    assert updated_equipment is not None

    # 4. 備品予約状況取得
    reservation_list = crud.get_reservations_by_equipment_id(db, equipment_id)

    # 5. 貸出状況・返却予定日の導出
    loan_status, due_date = _derive_loan_status_and_due_date(reservation_list)

    # 6. レスポンスへの変換
    equipment_response = EquipmentResponse(
        equipment_id=updated_equipment.id,
        asset_number=updated_equipment.asset_number,
        name=updated_equipment.name,
        category=updated_equipment.category,
        description=updated_equipment.description,
        location=updated_equipment.location,
        active_flag=updated_equipment.active_flag,
        loan_status=loan_status,
        due_date=due_date,
        created_at=updated_equipment.created_at,
        updated_at=updated_equipment.updated_at,
    )

    # 7. 戻り値を返却
    return equipment_response


def activate_equipment(db: Session, equipment_id: int) -> EquipmentResponse:
    """
    備品再有効化

    設計書：設計書/services/備品管理/備品再有効化_v0.2.0.md

    【処理概要】
    - 無効化済みの備品を再有効化する

    【パラメータ】
    - db (Session) : データベース (必須)
    - equipment_id (int) : 備品ID (必須)

    【戻り値】
    - equipment_response (EquipmentResponse) : 備品レスポンス

    【例外処理】
    - HTTPException(404) : 対象備品が取得できない場合

    【処理フロー】
    1. 現在日時取得
    2. 対象備品情報取得
    3. 備品有効化状態更新
    4. 備品予約状況取得
    5. 貸出状況・返却予定日の導出
    6. レスポンスへの変換
    7. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 対象備品情報取得
    target_equipment = crud.get_equipment_by_id(db, equipment_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定された備品が見つかりません。",
        )

    # 3. 備品有効化状態更新
    updated_equipment = crud.update_equipment_active_flag(db, now, equipment_id, True)
    assert updated_equipment is not None

    # 4. 備品予約状況取得
    reservation_list = crud.get_reservations_by_equipment_id(db, equipment_id)

    # 5. 貸出状況・返却予定日の導出
    loan_status, due_date = _derive_loan_status_and_due_date(reservation_list)

    # 6. レスポンスへの変換
    equipment_response = EquipmentResponse(
        equipment_id=updated_equipment.id,
        asset_number=updated_equipment.asset_number,
        name=updated_equipment.name,
        category=updated_equipment.category,
        description=updated_equipment.description,
        location=updated_equipment.location,
        active_flag=updated_equipment.active_flag,
        loan_status=loan_status,
        due_date=due_date,
        created_at=updated_equipment.created_at,
        updated_at=updated_equipment.updated_at,
    )

    # 7. 戻り値を返却
    return equipment_response


# ====================================================================================================
# 備品予約状況確認
# - get_equipment_reservations : 備品予約状況確認

# 設計書：設計書/services/備品管理/備品予約状況確認_v0.2.0.md
# ====================================================================================================


def get_equipment_reservations(
    current_user: User, db: Session, equipment_id: int
) -> list[ReservationResponse]:
    """
    備品予約状況確認

    設計書：設計書/services/備品管理/備品予約状況確認_v0.2.0.md

    【処理概要】
    - 指定した備品の承認済み・貸出中の予約期間を取得する
    - 借用者氏名は管理者のみレスポンスに含める

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)
    - equipment_id (int) : 備品ID (必須)

    【戻り値】
    - reservation_list (list[ReservationResponse]) : 予約情報レスポンス一覧（該当する申請が無い場合は空のリスト）

    【例外処理】
    - HTTPException(404) : 対象備品が取得できない場合、または一般ユーザーが無効化済み備品の予約状況を
      確認しようとした場合

    【処理フロー】
    1. 対象備品情報取得
    2. 無効化済み備品へのアクセス制御
    3. 備品予約状況取得
    4. レスポンスへの変換
    5. 戻り値を返却
    """

    not_found_exception = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="指定された備品が見つかりません。",
    )

    # 1. 対象備品情報取得
    target_equipment = crud.get_equipment_by_id(db, equipment_id)

    # 1.(2) 例外処理：取得結果がNone
    if target_equipment is None:
        raise not_found_exception

    # 2. 無効化済み備品へのアクセス制御
    # 2.① 例外処理：一般ユーザーかつ無効化済み備品
    if current_user.role != "管理者" and not target_equipment.active_flag:
        raise not_found_exception

    # 3. 備品予約状況取得
    equipment_reservation_list = crud.get_reservations_by_equipment_id(db, equipment_id)

    # 4. レスポンスへの変換
    is_admin = current_user.role == "管理者"
    reservation_list = [
        ReservationResponse(
            loan_request_id=equipment_reservation.id,
            start_date=equipment_reservation.start_date,
            due_date=equipment_reservation.due_date,
            status=equipment_reservation.status,
            applicant_name=equipment_reservation.applicant_name if is_admin else None,
        )
        for equipment_reservation in equipment_reservation_list
    ]

    # 5. 戻り値を返却
    return reservation_list


# ====================================================================================================
# 備品CSV一括登録
# - bulk_import_equipment : 備品CSV一括登録

# 設計書：設計書/services/備品管理/備品CSV一括登録_v0.2.0.md
# ====================================================================================================


_EQUIPMENT_CSV_MAX_FILE_SIZE = 5 * 1024 * 1024
_EQUIPMENT_CSV_MAX_ROW_COUNT = 1000
_EQUIPMENT_CSV_COLUMN_COUNT = 5
_EQUIPMENT_CSV_ASSET_NUMBER_PATTERN = re.compile(r"[A-Za-z0-9-]+")


def bulk_import_equipment(db: Session, file_content: bytes) -> EquipmentBulkImportResponse:
    """
    備品CSV一括登録

    設計書：設計書/services/備品管理/備品CSV一括登録_v0.2.0.md

    【処理概要】
    - CSVファイルから複数の備品を一括登録する
    - ファイルサイズ・文字コード・ヘッダー行・データ行数・各行の項目・資産番号の重複を検証し、
      1件でもエラーがあれば全件登録しない

    【パラメータ】
    - db (Session) : データベース (必須)
    - file_content (bytes) : ファイル内容 (必須)

    【戻り値】
    - bulk_import_response (EquipmentBulkImportResponse) : 備品CSV一括登録レスポンス

    【例外処理】
    - HTTPException(400) : ファイルサイズが5MBを超える場合
    - HTTPException(400) : 文字コードのデコードに失敗する場合
    - HTTPException(400) : ヘッダー行の列数が5でない場合
    - HTTPException(400) : データ行数が1,000を超える場合
    - HTTPException(400) : 各データ行の項目検証・資産番号の重複チェックで1件以上のエラーがある場合

    【処理フロー】
    1. ファイルサイズ検証
    2. 文字コードデコード
    3. CSV解析
    4. ヘッダー行の列構成検証
    5. データ行数検証
    6. 各データ行の項目検証
    7. CSV内資産番号重複チェック
    8. DB内資産番号重複チェック
    9. エラー一覧の判定
    10. 現在日時取得
    11. 複数備品同時登録
    12. レスポンスへの変換
    13. 戻り値を返却
    """

    # 1. ファイルサイズ検証
    # 1.① 例外処理：ファイルサイズが上限を超える
    if len(file_content) > _EQUIPMENT_CSV_MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=EquipmentBulkImportErrorResponse(
                error_list=[
                    EquipmentBulkImportErrorDetail(
                        row_number=None, message="ファイルサイズが上限（5MB）を超えています。"
                    )
                ]
            ).model_dump(),
        )

    # 2. 文字コードデコード
    # 2.(2) 例外処理：デコードに失敗する
    try:
        decoded_content = file_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=EquipmentBulkImportErrorResponse(
                error_list=[
                    EquipmentBulkImportErrorDetail(
                        row_number=None, message="ファイルの文字コードが不正です。UTF-8で保存してください。"
                    )
                ]
            ).model_dump(),
        ) from exc

    # 3. CSV解析
    line_list = decoded_content.splitlines()
    header_line = line_list[0] if line_list else ""
    header_column_list = header_line.split(",")
    data_line_list = line_list[1:]

    # 4. ヘッダー行の列構成検証
    # 4.① 例外処理：ヘッダー行の列数が5でない
    if len(header_column_list) != _EQUIPMENT_CSV_COLUMN_COUNT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=EquipmentBulkImportErrorResponse(
                error_list=[
                    EquipmentBulkImportErrorDetail(
                        row_number=None,
                        message="ヘッダー行の列構成が不正です。列は資産番号・備品名・分類・説明・保管場所の順にしてください。",
                    )
                ]
            ).model_dump(),
        )

    # 5. データ行数検証
    # 5.① 例外処理：データ行の件数が1,000を超える
    if len(data_line_list) > _EQUIPMENT_CSV_MAX_ROW_COUNT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=EquipmentBulkImportErrorResponse(
                error_list=[
                    EquipmentBulkImportErrorDetail(
                        row_number=None, message="データ行数が上限（1,000行）を超えています。"
                    )
                ]
            ).model_dump(),
        )

    # 6. 各データ行の項目検証
    error_list: list[EquipmentBulkImportErrorDetail] = []
    asset_number_valid_row_list: list[tuple[int, str, str, str, str, str]] = []
    for row_number, data_line in enumerate(data_line_list, start=1):
        column_list = data_line.split(",")

        # 6.① 列数が5でない行は、以降（7.・8.）の検証を行わない
        if len(column_list) != _EQUIPMENT_CSV_COLUMN_COUNT:
            error_list.append(EquipmentBulkImportErrorDetail(row_number=row_number, message="列数が不正です。"))
            continue

        asset_number, name, category, description, location = column_list

        is_asset_number_valid = 1 <= len(asset_number) <= 32 and bool(
            _EQUIPMENT_CSV_ASSET_NUMBER_PATTERN.fullmatch(asset_number)
        )
        if not is_asset_number_valid:
            error_list.append(EquipmentBulkImportErrorDetail(row_number=row_number, message="資産番号が不正です。"))
        if not 1 <= len(name) <= 100:
            error_list.append(EquipmentBulkImportErrorDetail(row_number=row_number, message="備品名が不正です。"))
        if not 1 <= len(category) <= 50:
            error_list.append(EquipmentBulkImportErrorDetail(row_number=row_number, message="分類が不正です。"))
        if len(description) > 500:
            error_list.append(EquipmentBulkImportErrorDetail(row_number=row_number, message="説明が不正です。"))
        if len(location) > 100:
            error_list.append(EquipmentBulkImportErrorDetail(row_number=row_number, message="保管場所が不正です。"))

        if is_asset_number_valid:
            asset_number_valid_row_list.append((row_number, asset_number, name, category, description, location))

    # 7. CSV内資産番号重複チェック
    asset_number_to_row_number_list: dict[str, list[int]] = {}
    for row_number, asset_number, *_rest in asset_number_valid_row_list:
        asset_number_to_row_number_list.setdefault(asset_number, []).append(row_number)
    for duplicated_row_number_list in asset_number_to_row_number_list.values():
        for duplicated_row_number in duplicated_row_number_list[1:]:
            error_list.append(
                EquipmentBulkImportErrorDetail(row_number=duplicated_row_number, message="資産番号が重複しています。")
            )

    # 8. DB内資産番号重複チェック
    asset_number_list_to_check = [asset_number for _row_number, asset_number, *_rest in asset_number_valid_row_list]
    existing_asset_number_set = set(crud.get_existing_asset_numbers(db, asset_number_list_to_check))
    for row_number, asset_number, *_rest in asset_number_valid_row_list:
        if asset_number in existing_asset_number_set:
            error_list.append(
                EquipmentBulkImportErrorDetail(row_number=row_number, message="この資産番号は既に使用されています。")
            )

    # 9. エラー一覧の判定
    # 9.① 例外処理：エラー一覧の件数が1件以上
    if error_list:

        def _error_sort_key(error: EquipmentBulkImportErrorDetail) -> int:
            return error.row_number if error.row_number is not None else 0

        sorted_error_list = sorted(error_list, key=_error_sort_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=EquipmentBulkImportErrorResponse(error_list=sorted_error_list).model_dump(),
        )

    # 10. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 11. 複数備品同時登録
    equipment_create_list = [
        crud.EquipmentCreateItem(
            asset_number=asset_number,
            name=name,
            category=category,
            description=description,
            location=location,
        )
        for _row_number, asset_number, name, category, description, location in asset_number_valid_row_list
    ]
    created_equipment_list = crud.bulk_create_equipment(db, now, equipment_create_list)

    # 12. レスポンスへの変換
    equipment_list = [
        EquipmentResponse(
            equipment_id=created_equipment.id,
            asset_number=created_equipment.asset_number,
            name=created_equipment.name,
            category=created_equipment.category,
            description=created_equipment.description,
            location=created_equipment.location,
            active_flag=created_equipment.active_flag,
            loan_status="貸出可",
            due_date=None,
            created_at=created_equipment.created_at,
            updated_at=created_equipment.updated_at,
        )
        for created_equipment in created_equipment_list
    ]
    bulk_import_response = EquipmentBulkImportResponse(
        registered_count=len(created_equipment_list),
        equipment_list=equipment_list,
    )

    # 13. 戻り値を返却
    return bulk_import_response
