"""
オーケストレーション処理

【概要】
エンドポイント層・日次バッチ共通処理からの呼び出しを受け、データアクセス層・共通処理を呼び出して業務処理を行う
"""

import datetime as dt
import os
import re
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import auth, crud
from app.models import User
from app.schemas import (
    EquipmentBulkImportErrorDetail,
    EquipmentBulkImportErrorResponse,
    EquipmentBulkImportResponse,
    EquipmentResponse,
    LoanRequestResponse,
    NotificationResponse,
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


# ====================================================================================================
# 貸出申請登録
# - create_loan_request : 貸出申請登録

# 設計書：設計書/services/貸出申請・承認/貸出申請登録_v0.2.0.md
# ====================================================================================================


def create_loan_request(
    current_user: User,
    db: Session,
    equipment_id: int,
    start_date: dt.date,
    due_date: dt.date,
    purpose: str,
) -> LoanRequestResponse:
    """
    貸出申請登録

    設計書：設計書/services/貸出申請・承認/貸出申請登録_v0.2.0.md

    【処理概要】
    - ログインユーザーが、自分名義で備品の貸出を申請する
    - 対象備品の有効性・開始日・返却予定日の整合性・同一備品の期間重複を確認した上で申請を登録し、
      全管理者宛に「新規申請」通知を生成する

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)
    - equipment_id (int) : 備品（内部ID） (必須)
    - start_date (date) : 開始日 (必須)
    - due_date (date) : 返却予定日 (必須)
    - purpose (str) : 用途 (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - HTTPException(404) : 対象備品が取得できない場合
    - HTTPException(409) : 対象備品が無効化されている場合
    - HTTPException(400) : 開始日が今日より前の場合
    - HTTPException(400) : 返却予定日が開始日より前の場合
    - HTTPException(409) : 同一備品について承認済み・貸出中の申請と期間が重複する場合

    【処理フロー】
    1. 現在日時取得
    2. 対象備品情報取得
    3. 備品有効性確認
    4. 開始日・返却予定日の整合性確認
    5. 貸出申請期間重複確認
    6. 貸出申請登録
    7. 通知対象の有効管理者ID一覧取得
    8. 新規申請通知の一括生成
    9. レスポンスへの変換
    10. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)
    today = now.date()

    # 2. 対象備品情報取得
    target_equipment = crud.get_equipment_by_id(db, equipment_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定された備品が見つかりません。",
        )

    # 3. 備品有効性確認
    # 3.② 例外処理：対象備品が無効化されている
    if not target_equipment.active_flag:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="指定された備品は無効化されているため、貸出を申請できません。",
        )

    # 4. 開始日・返却予定日の整合性確認
    # 4.(1) 例外処理：開始日が今日より前
    if start_date < today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="開始日には今日以降の日付を指定してください。",
        )
    # 4.(2) 例外処理：返却予定日が開始日より前
    if due_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="返却予定日には開始日以降の日付を指定してください。",
        )

    # 5. 貸出申請期間重複確認
    overlapping_count = crud.count_overlapping_loan_requests(db, equipment_id, start_date, due_date, None)
    # 5.(2) 例外処理：重複件数が1以上
    if overlapping_count >= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="指定した期間は、既に承認済みまたは貸出中の申請と重複しています。",
        )

    # 6. 貸出申請登録
    applicant_user_id = current_user.id
    created_loan_request = crud.create_loan_request(
        db, equipment_id, applicant_user_id, start_date, due_date, purpose, now
    )

    # 7. 通知対象の有効管理者ID一覧取得
    admin_user_id_list = crud.get_active_admin_user_id_list(db)

    # 8. 新規申請通知の一括生成
    for admin_user_id in admin_user_id_list:
        crud.create_notification(db, admin_user_id, "新規申請", created_loan_request.id, now)

    # 9. レスポンスへの変換
    loan_request_response = LoanRequestResponse(
        loan_request_id=created_loan_request.id,
        equipment_id=created_loan_request.equipment_id,
        start_date=created_loan_request.start_date,
        due_date=created_loan_request.due_date,
        purpose=created_loan_request.purpose,
        applicant_user_id=created_loan_request.applicant_user_id,
        status=created_loan_request.status,
        reject_cancel_reason=created_loan_request.reject_cancel_reason,
        approved_rejected_by_user_id=created_loan_request.approved_rejected_by_user_id,
        lent_by_user_id=created_loan_request.lent_by_user_id,
        returned_by_user_id=created_loan_request.returned_by_user_id,
        cancelled_by_user_id=created_loan_request.cancelled_by_user_id,
        requested_at=created_loan_request.requested_at,
        approved_rejected_at=created_loan_request.approved_rejected_at,
        lent_at=created_loan_request.lent_at,
        returned_at=created_loan_request.returned_at,
        cancelled_at=created_loan_request.cancelled_at,
        return_note=created_loan_request.return_note,
    )

    # 10. 戻り値を返却
    return loan_request_response


# ====================================================================================================
# 貸出申請取消
# - cancel_loan_request_by_applicant : 貸出申請取消

# 設計書：設計書/services/貸出申請・承認/貸出申請取消_v0.2.0.md
# ====================================================================================================


def cancel_loan_request_by_applicant(
    current_user: User,
    db: Session,
    loan_request_id: int,
    reason: str | None,
) -> LoanRequestResponse:
    """
    貸出申請取消

    設計書：設計書/services/貸出申請・承認/貸出申請取消_v0.2.0.md

    【処理概要】
    - ログインユーザーが、自分の申請を取消す
    - 対象の申請がログインユーザー自身の申請であり、状態が「申請中」または「承認済み」であることを
      確認した上で取消す

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)
    - loan_request_id (int) : 貸出申請（内部ID） (必須)
    - reason (str | None) : 取消理由 (任意)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - HTTPException(404) : 対象貸出申請が取得できない場合、または申請者がログインユーザー自身でない場合
    - HTTPException(409) : 対象貸出申請の状態が「申請中」「承認済み」のいずれでもない場合

    【処理フロー】
    1. 現在日時取得
    2. 対象貸出申請情報取得
    3. 申請者確認
    4. 状態確認
    5. 貸出申請取消
    6. レスポンスへの変換
    7. 戻り値を返却
    """

    not_found_exception = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="指定された貸出申請が見つかりません。",
    )

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 対象貸出申請情報取得
    target_loan_request = crud.get_loan_request_by_id(db, loan_request_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_loan_request is None:
        raise not_found_exception

    # 3. 申請者確認
    # 3.(1) 例外処理：申請者がログインユーザー自身でない
    if target_loan_request.applicant_user_id != current_user.id:
        raise not_found_exception

    # 4. 状態確認
    # 4.(1) 例外処理：状態が「申請中」「承認済み」のいずれでもない
    if target_loan_request.status not in ("申請中", "承認済み"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="この申請は現在の状態では取消できません。",
        )

    # 5. 貸出申請取消
    cancelled_loan_request = crud.cancel_loan_request(db, loan_request_id, current_user.id, reason, now)
    assert cancelled_loan_request is not None

    # 6. レスポンスへの変換
    loan_request_response = LoanRequestResponse(
        loan_request_id=cancelled_loan_request.id,
        equipment_id=cancelled_loan_request.equipment_id,
        start_date=cancelled_loan_request.start_date,
        due_date=cancelled_loan_request.due_date,
        purpose=cancelled_loan_request.purpose,
        applicant_user_id=cancelled_loan_request.applicant_user_id,
        status=cancelled_loan_request.status,
        reject_cancel_reason=cancelled_loan_request.reject_cancel_reason,
        approved_rejected_by_user_id=cancelled_loan_request.approved_rejected_by_user_id,
        lent_by_user_id=cancelled_loan_request.lent_by_user_id,
        returned_by_user_id=cancelled_loan_request.returned_by_user_id,
        cancelled_by_user_id=cancelled_loan_request.cancelled_by_user_id,
        requested_at=cancelled_loan_request.requested_at,
        approved_rejected_at=cancelled_loan_request.approved_rejected_at,
        lent_at=cancelled_loan_request.lent_at,
        returned_at=cancelled_loan_request.returned_at,
        cancelled_at=cancelled_loan_request.cancelled_at,
        return_note=cancelled_loan_request.return_note,
    )

    # 7. 戻り値を返却
    return loan_request_response


# ====================================================================================================
# 貸出申請一覧取得
# - get_loan_requests : 貸出申請一覧取得

# 設計書：設計書/services/貸出申請・承認/貸出申請一覧取得_v0.3.0.md
# ====================================================================================================


def get_loan_requests(
    current_user: User,
    db: Session,
    scope: Literal["mine", "all", "overdue"],
    status_filter: str | None,
) -> list[LoanRequestResponse]:
    """
    貸出申請一覧取得

    設計書：設計書/services/貸出申請・承認/貸出申請一覧取得_v0.3.0.md

    【処理概要】
    - ログインユーザーが、自分の申請・貸出状況を確認する
    - 管理者が、全申請の確認、または期限超過中の貸出一覧の確認を行う（全申請・期限超過の指定は管理者のみ許可する）

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)
    - scope (Literal["mine", "all", "overdue"]) : 対象範囲 (必須)
    - status_filter (str | None) : 状態 (任意)

    【戻り値】
    - loan_request_response_list (list[LoanRequestResponse]) : 貸出申請レスポンス一覧

    【例外処理】
    - HTTPException(403) : 対象範囲が"all"または"overdue"、かつログインユーザーが管理者でない場合

    【処理フロー】
    1. 現在日時取得
    2. 対象範囲の権限確認
    3. 検索条件の決定
    4. 貸出申請検索一覧取得
    5. レスポンスへの変換
    6. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)
    today = now.date()

    # 2. 対象範囲の権限確認
    # 2.① 例外処理：対象範囲が"all"または"overdue"、かつ管理者でない
    if scope in ("all", "overdue") and current_user.role != "管理者":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="この操作を行う権限がありません。",
        )

    # 3. 検索条件の決定
    if scope == "mine":
        search_applicant_user_id = current_user.id
        search_status = status_filter
        search_due_date_before = None
    elif scope == "all":
        search_applicant_user_id = None
        search_status = status_filter
        search_due_date_before = None
    else:
        search_applicant_user_id = None
        search_status = "貸出中"
        search_due_date_before = today

    # 4. 貸出申請検索一覧取得
    loan_request_list = crud.search_loan_requests(
        db,
        search_applicant_user_id,
        search_status,
        None,
        search_due_date_before,
        None,
        None,
        None,
        None,
    )

    # 5. レスポンスへの変換
    loan_request_response_list = [
        LoanRequestResponse(
            loan_request_id=loan_request.id,
            equipment_id=loan_request.equipment_id,
            start_date=loan_request.start_date,
            due_date=loan_request.due_date,
            purpose=loan_request.purpose,
            applicant_user_id=loan_request.applicant_user_id,
            status=loan_request.status,
            reject_cancel_reason=loan_request.reject_cancel_reason,
            approved_rejected_by_user_id=loan_request.approved_rejected_by_user_id,
            lent_by_user_id=loan_request.lent_by_user_id,
            returned_by_user_id=loan_request.returned_by_user_id,
            cancelled_by_user_id=loan_request.cancelled_by_user_id,
            requested_at=loan_request.requested_at,
            approved_rejected_at=loan_request.approved_rejected_at,
            lent_at=loan_request.lent_at,
            returned_at=loan_request.returned_at,
            cancelled_at=loan_request.cancelled_at,
            return_note=loan_request.return_note,
        )
        for loan_request in loan_request_list
    ]

    # 6. 戻り値を返却
    return loan_request_response_list


# ====================================================================================================
# 貸出申請詳細取得
# - get_loan_request : 貸出申請詳細取得

# 設計書：設計書/services/貸出申請・承認/貸出申請詳細取得_v0.2.0.md
# ====================================================================================================


def get_loan_request(current_user: User, db: Session, loan_request_id: int) -> LoanRequestResponse:
    """
    貸出申請詳細取得

    設計書：設計書/services/貸出申請・承認/貸出申請詳細取得_v0.2.0.md

    【処理概要】
    - ログインユーザーが、自分の申請の詳細を確認する
    - 管理者は、任意の申請の詳細を確認できる

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)
    - loan_request_id (int) : 貸出申請（内部ID） (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - HTTPException(404) : 対象貸出申請が取得できない場合、または一般ユーザーが他人の申請を取得しようとした場合

    【処理フロー】
    1. 対象貸出申請情報取得
    2. アクセス制御
    3. レスポンスへの変換
    4. 戻り値を返却
    """

    not_found_exception = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="指定された貸出申請が見つかりません。",
    )

    # 1. 対象貸出申請情報取得
    target_loan_request = crud.get_loan_request_by_id(db, loan_request_id)

    # 1.(2) 例外処理：取得結果がNone
    if target_loan_request is None:
        raise not_found_exception

    # 2. アクセス制御
    # 2.① 例外処理：管理者でなく、かつ申請者がログインユーザー自身でない
    if current_user.role != "管理者" and target_loan_request.applicant_user_id != current_user.id:
        raise not_found_exception

    # 3. レスポンスへの変換
    loan_request_response = LoanRequestResponse(
        loan_request_id=target_loan_request.id,
        equipment_id=target_loan_request.equipment_id,
        start_date=target_loan_request.start_date,
        due_date=target_loan_request.due_date,
        purpose=target_loan_request.purpose,
        applicant_user_id=target_loan_request.applicant_user_id,
        status=target_loan_request.status,
        reject_cancel_reason=target_loan_request.reject_cancel_reason,
        approved_rejected_by_user_id=target_loan_request.approved_rejected_by_user_id,
        lent_by_user_id=target_loan_request.lent_by_user_id,
        returned_by_user_id=target_loan_request.returned_by_user_id,
        cancelled_by_user_id=target_loan_request.cancelled_by_user_id,
        requested_at=target_loan_request.requested_at,
        approved_rejected_at=target_loan_request.approved_rejected_at,
        lent_at=target_loan_request.lent_at,
        returned_at=target_loan_request.returned_at,
        cancelled_at=target_loan_request.cancelled_at,
        return_note=target_loan_request.return_note,
    )

    # 4. 戻り値を返却
    return loan_request_response


# ====================================================================================================
# 貸出申請承認
# - approve_loan_request : 貸出申請承認

# 設計書：設計書/services/貸出申請・承認/貸出申請承認_v0.2.0.md
# ====================================================================================================


def approve_loan_request(current_admin: User, db: Session, loan_request_id: int) -> LoanRequestResponse:
    """
    貸出申請承認

    設計書：設計書/services/貸出申請・承認/貸出申請承認_v0.2.0.md

    【処理概要】
    - 管理者が、申請中の貸出申請を承認する
    - 状態・開始日・同一備品の期間重複（再検証）を確認した上で承認済みに更新し、申請者宛に「承認」通知を生成する

    【パラメータ】
    - current_admin (User) : 管理者検証結果 (必須)
    - db (Session) : データベース (必須)
    - loan_request_id (int) : 貸出申請（内部ID） (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - HTTPException(404) : 対象貸出申請が取得できない場合
    - HTTPException(409) : 対象貸出申請の状態が「申請中」でない場合
    - HTTPException(409) : 対象貸出申請の開始日が今日より前の場合
    - HTTPException(409) : 同一備品について承認済み・貸出中の申請と期間が重複する場合

    【処理フロー】
    1. 現在日時取得
    2. 対象貸出申請情報取得
    3. 状態確認
    4. 開始日確認
    5. 貸出申請期間重複確認
    6. 貸出申請承認
    7. 承認通知の生成
    8. レスポンスへの変換
    9. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)
    today = now.date()

    # 2. 対象貸出申請情報取得
    target_loan_request = crud.get_loan_request_by_id(db, loan_request_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_loan_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定された貸出申請が見つかりません。",
        )

    # 3. 状態確認
    # 3.(1) 例外処理：状態が「申請中」でない
    if target_loan_request.status != "申請中":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="この申請は現在の状態では承認できません。",
        )

    # 4. 開始日確認
    # 4.(1) 例外処理：開始日が今日より前
    if target_loan_request.start_date < today:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="開始日を過ぎているため、この申請は承認できません。",
        )

    # 5. 貸出申請期間重複確認
    overlapping_count = crud.count_overlapping_loan_requests(
        db,
        target_loan_request.equipment_id,
        target_loan_request.start_date,
        target_loan_request.due_date,
        loan_request_id,
    )
    # 5.(2) 例外処理：重複件数が1以上
    if overlapping_count >= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="指定した期間は、既に承認済みまたは貸出中の申請と重複しています。",
        )

    # 6. 貸出申請承認
    approved_loan_request = crud.approve_loan_request(db, loan_request_id, current_admin.id, now)
    assert approved_loan_request is not None

    # 7. 承認通知の生成
    crud.create_notification(db, approved_loan_request.applicant_user_id, "承認", loan_request_id, now)

    # 8. レスポンスへの変換
    loan_request_response = LoanRequestResponse(
        loan_request_id=approved_loan_request.id,
        equipment_id=approved_loan_request.equipment_id,
        start_date=approved_loan_request.start_date,
        due_date=approved_loan_request.due_date,
        purpose=approved_loan_request.purpose,
        applicant_user_id=approved_loan_request.applicant_user_id,
        status=approved_loan_request.status,
        reject_cancel_reason=approved_loan_request.reject_cancel_reason,
        approved_rejected_by_user_id=approved_loan_request.approved_rejected_by_user_id,
        lent_by_user_id=approved_loan_request.lent_by_user_id,
        returned_by_user_id=approved_loan_request.returned_by_user_id,
        cancelled_by_user_id=approved_loan_request.cancelled_by_user_id,
        requested_at=approved_loan_request.requested_at,
        approved_rejected_at=approved_loan_request.approved_rejected_at,
        lent_at=approved_loan_request.lent_at,
        returned_at=approved_loan_request.returned_at,
        cancelled_at=approved_loan_request.cancelled_at,
        return_note=approved_loan_request.return_note,
    )

    # 9. 戻り値を返却
    return loan_request_response


# ====================================================================================================
# 貸出申請却下
# - reject_loan_request : 貸出申請却下

# 設計書：設計書/services/貸出申請・承認/貸出申請却下_v0.2.0.md
# ====================================================================================================


def reject_loan_request(current_admin: User, db: Session, loan_request_id: int, reason: str) -> LoanRequestResponse:
    """
    貸出申請却下

    設計書：設計書/services/貸出申請・承認/貸出申請却下_v0.2.0.md

    【処理概要】
    - 管理者が、申請中の貸出申請を却下する
    - 状態を確認した上で却下理由とともに却下に更新し、申請者宛に「却下」通知を生成する

    【パラメータ】
    - current_admin (User) : 管理者検証結果 (必須)
    - db (Session) : データベース (必須)
    - loan_request_id (int) : 貸出申請（内部ID） (必須)
    - reason (str) : 却下理由 (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - HTTPException(404) : 対象貸出申請が取得できない場合
    - HTTPException(409) : 対象貸出申請の状態が「申請中」でない場合

    【処理フロー】
    1. 現在日時取得
    2. 対象貸出申請情報取得
    3. 状態確認
    4. 貸出申請却下
    5. 却下通知の生成
    6. レスポンスへの変換
    7. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 対象貸出申請情報取得
    target_loan_request = crud.get_loan_request_by_id(db, loan_request_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_loan_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定された貸出申請が見つかりません。",
        )

    # 3. 状態確認
    # 3.(1) 例外処理：状態が「申請中」でない
    if target_loan_request.status != "申請中":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="この申請は現在の状態では却下できません。",
        )

    # 4. 貸出申請却下
    rejected_loan_request = crud.reject_loan_request(db, loan_request_id, current_admin.id, reason, now)
    assert rejected_loan_request is not None

    # 5. 却下通知の生成
    crud.create_notification(db, rejected_loan_request.applicant_user_id, "却下", loan_request_id, now)

    # 6. レスポンスへの変換
    loan_request_response = LoanRequestResponse(
        loan_request_id=rejected_loan_request.id,
        equipment_id=rejected_loan_request.equipment_id,
        start_date=rejected_loan_request.start_date,
        due_date=rejected_loan_request.due_date,
        purpose=rejected_loan_request.purpose,
        applicant_user_id=rejected_loan_request.applicant_user_id,
        status=rejected_loan_request.status,
        reject_cancel_reason=rejected_loan_request.reject_cancel_reason,
        approved_rejected_by_user_id=rejected_loan_request.approved_rejected_by_user_id,
        lent_by_user_id=rejected_loan_request.lent_by_user_id,
        returned_by_user_id=rejected_loan_request.returned_by_user_id,
        cancelled_by_user_id=rejected_loan_request.cancelled_by_user_id,
        requested_at=rejected_loan_request.requested_at,
        approved_rejected_at=rejected_loan_request.approved_rejected_at,
        lent_at=rejected_loan_request.lent_at,
        returned_at=rejected_loan_request.returned_at,
        cancelled_at=rejected_loan_request.cancelled_at,
        return_note=rejected_loan_request.return_note,
    )

    # 7. 戻り値を返却
    return loan_request_response


# ====================================================================================================
# 貸出申請管理者取消
# - admin_cancel_loan_request : 貸出申請管理者取消

# 設計書：設計書/services/貸出申請・承認/貸出申請管理者取消_v0.2.0.md
# ====================================================================================================


def admin_cancel_loan_request(
    current_admin: User, db: Session, loan_request_id: int, reason: str
) -> LoanRequestResponse:
    """
    貸出申請管理者取消

    設計書：設計書/services/貸出申請・承認/貸出申請管理者取消_v0.2.0.md

    【処理概要】
    - 管理者が、承認済みの貸出申請を取消す
    - 状態を確認した上で取消理由とともに取消し、申請者宛に「取消」通知を生成する

    【パラメータ】
    - current_admin (User) : 管理者検証結果 (必須)
    - db (Session) : データベース (必須)
    - loan_request_id (int) : 貸出申請（内部ID） (必須)
    - reason (str) : 取消理由 (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - HTTPException(404) : 対象貸出申請が取得できない場合
    - HTTPException(409) : 対象貸出申請の状態が「承認済み」でない場合

    【処理フロー】
    1. 現在日時取得
    2. 対象貸出申請情報取得
    3. 状態確認
    4. 貸出申請取消
    5. 取消通知の生成
    6. レスポンスへの変換
    7. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 対象貸出申請情報取得
    target_loan_request = crud.get_loan_request_by_id(db, loan_request_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_loan_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定された貸出申請が見つかりません。",
        )

    # 3. 状態確認
    # 3.(1) 例外処理：状態が「承認済み」でない
    if target_loan_request.status != "承認済み":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="この申請は現在の状態では取消できません。",
        )

    # 4. 貸出申請取消
    cancelled_loan_request = crud.cancel_loan_request(db, loan_request_id, current_admin.id, reason, now)
    assert cancelled_loan_request is not None

    # 5. 取消通知の生成
    crud.create_notification(db, cancelled_loan_request.applicant_user_id, "取消", loan_request_id, now)

    # 6. レスポンスへの変換
    loan_request_response = LoanRequestResponse(
        loan_request_id=cancelled_loan_request.id,
        equipment_id=cancelled_loan_request.equipment_id,
        start_date=cancelled_loan_request.start_date,
        due_date=cancelled_loan_request.due_date,
        purpose=cancelled_loan_request.purpose,
        applicant_user_id=cancelled_loan_request.applicant_user_id,
        status=cancelled_loan_request.status,
        reject_cancel_reason=cancelled_loan_request.reject_cancel_reason,
        approved_rejected_by_user_id=cancelled_loan_request.approved_rejected_by_user_id,
        lent_by_user_id=cancelled_loan_request.lent_by_user_id,
        returned_by_user_id=cancelled_loan_request.returned_by_user_id,
        cancelled_by_user_id=cancelled_loan_request.cancelled_by_user_id,
        requested_at=cancelled_loan_request.requested_at,
        approved_rejected_at=cancelled_loan_request.approved_rejected_at,
        lent_at=cancelled_loan_request.lent_at,
        returned_at=cancelled_loan_request.returned_at,
        cancelled_at=cancelled_loan_request.cancelled_at,
        return_note=cancelled_loan_request.return_note,
    )

    # 7. 戻り値を返却
    return loan_request_response


# ====================================================================================================
# 通知一覧取得
# - get_notifications : 通知一覧取得

# 設計書：設計書/services/貸出申請・承認/通知一覧取得_v0.2.0.md
# ====================================================================================================


def get_notifications(current_user: User, db: Session) -> list[NotificationResponse]:
    """
    通知一覧取得

    設計書：設計書/services/貸出申請・承認/通知一覧取得_v0.2.0.md

    【処理概要】
    - ログインユーザーが、自分宛の通知一覧を確認する（作成日時の降順）

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - notification_response_list (list[NotificationResponse]) : 通知レスポンス一覧

    【例外処理】
    - なし

    【処理フロー】
    1. 通知一覧取得
    2. レスポンスへの変換
    3. 戻り値を返却
    """

    # 1. 通知一覧取得
    notification_list = crud.get_notifications_by_recipient(db, current_user.id)

    # 2. レスポンスへの変換
    notification_response_list = [
        NotificationResponse(
            notification_id=notification.id,
            notification_type=notification.notification_type,
            loan_request_id=notification.loan_request_id,
            read_flag=notification.read_flag,
            created_at=notification.created_at,
        )
        for notification in notification_list
    ]

    # 3. 戻り値を返却
    return notification_response_list


# ====================================================================================================
# 通知既読化
# - mark_notification_as_read_by_recipient : 通知既読化

# 設計書：設計書/services/貸出申請・承認/通知既読化_v0.2.0.md
# ====================================================================================================


def mark_notification_as_read_by_recipient(
    current_user: User, db: Session, notification_id: int
) -> NotificationResponse:
    """
    通知既読化

    設計書：設計書/services/貸出申請・承認/通知既読化_v0.2.0.md

    【処理概要】
    - ログインユーザーが、自分宛の通知を既読にする
    - 対象の通知がログインユーザー自身を宛先とする通知であることを確認した上で既読に更新する

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)
    - notification_id (int) : 通知（内部ID） (必須)

    【戻り値】
    - notification_response (NotificationResponse) : 通知レスポンス

    【例外処理】
    - HTTPException(404) : 対象通知が取得できない場合、または宛先がログインユーザー自身でない場合

    【処理フロー】
    1. 対象通知情報取得
    2. 宛先確認
    3. 通知既読化
    4. レスポンスへの変換
    5. 戻り値を返却
    """

    not_found_exception = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="指定された通知が見つかりません。",
    )

    # 1. 対象通知情報取得
    target_notification = crud.get_notification_by_id(db, notification_id)

    # 1.(2) 例外処理：取得結果がNone
    if target_notification is None:
        raise not_found_exception

    # 2. 宛先確認
    # 2.(1) 例外処理：宛先がログインユーザー自身でない
    if target_notification.recipient_user_id != current_user.id:
        raise not_found_exception

    # 3. 通知既読化
    read_notification = crud.mark_notification_as_read(db, notification_id)
    assert read_notification is not None

    # 4. レスポンスへの変換
    notification_response = NotificationResponse(
        notification_id=read_notification.id,
        notification_type=read_notification.notification_type,
        loan_request_id=read_notification.loan_request_id,
        read_flag=read_notification.read_flag,
        created_at=read_notification.created_at,
    )

    # 5. 戻り値を返却
    return notification_response


# ====================================================================================================
# ノーショー自動取消（開始日超過・返却予定日超過）
# - cancel_no_show_loan_requests_by_start_date : ノーショー自動取消（開始日超過）
# - cancel_no_show_loan_requests_by_due_date : ノーショー自動取消（返却予定日超過）

# 設計書：
# - 設計書/services/貸出申請・承認/ノーショー自動取消（開始日超過）_v0.3.0.md
# - 設計書/services/貸出申請・承認/ノーショー自動取消（返却予定日超過）_v0.3.0.md
# ====================================================================================================


def cancel_no_show_loan_requests_by_start_date(db: Session) -> int:
    """
    ノーショー自動取消（開始日超過）

    設計書：設計書/services/貸出申請・承認/ノーショー自動取消（開始日超過）_v0.3.0.md

    【処理概要】
    - 申請中のまま開始日を過ぎた貸出申請を自動的に取消し、各申請の申請者宛に「取消」通知を生成する

    【パラメータ】
    - db (Session) : データベース (必須)

    【戻り値】
    - cancelled_count (int) : 自動取消件数

    【例外処理】
    - なし

    【処理フロー】
    1. 現在日時取得
    2. 対象貸出申請一覧取得
    3. 対象貸出申請の取消
    4. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)
    today = now.date()

    # 2. 対象貸出申請一覧取得
    target_loan_request_list = crud.search_loan_requests(db, None, "申請中", today, None, None, None, None, None)

    # 3. 対象貸出申請の取消
    for target_loan_request in target_loan_request_list:
        # 3.① 貸出申請を取消す
        cancelled_loan_request = crud.cancel_loan_request(
            db,
            target_loan_request.id,
            None,
            "申請中のまま開始日を過ぎたため、自動的に取消しました。",
            now,
        )
        assert cancelled_loan_request is not None
        # 3.② 取消成立時、申請者宛に「取消」通知を生成する
        crud.create_notification(db, cancelled_loan_request.applicant_user_id, "取消", cancelled_loan_request.id, now)

    # 4. 戻り値を返却
    cancelled_count = len(target_loan_request_list)
    return cancelled_count


def cancel_no_show_loan_requests_by_due_date(db: Session) -> int:
    """
    ノーショー自動取消（返却予定日超過）

    設計書：設計書/services/貸出申請・承認/ノーショー自動取消（返却予定日超過）_v0.3.0.md

    【処理概要】
    - 承認済みのまま返却予定日を過ぎた貸出申請を自動的に取消し、各申請の申請者宛に「取消」通知を生成する

    【パラメータ】
    - db (Session) : データベース (必須)

    【戻り値】
    - cancelled_count (int) : 自動取消件数

    【例外処理】
    - なし

    【処理フロー】
    1. 現在日時取得
    2. 対象貸出申請一覧取得
    3. 対象貸出申請の取消
    4. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)
    today = now.date()

    # 2. 対象貸出申請一覧取得
    target_loan_request_list = crud.search_loan_requests(db, None, "承認済み", None, today, None, None, None, None)

    # 3. 対象貸出申請の取消
    for target_loan_request in target_loan_request_list:
        # 3.① 貸出申請を取消す
        cancelled_loan_request = crud.cancel_loan_request(
            db,
            target_loan_request.id,
            None,
            "承認済みのまま返却予定日を過ぎたため、自動的に取消しました。",
            now,
        )
        assert cancelled_loan_request is not None
        # 3.② 取消成立時、申請者宛に「取消」通知を生成する
        crud.create_notification(db, cancelled_loan_request.applicant_user_id, "取消", cancelled_loan_request.id, now)

    # 4. 戻り値を返却
    cancelled_count = len(target_loan_request_list)
    return cancelled_count


# ====================================================================================================
# 貸出処理
# - lend_loan_request : 貸出処理

# 設計書：設計書/services/貸出・返却・履歴/貸出処理_v0.2.0.md
# ====================================================================================================


def lend_loan_request(current_admin: User, db: Session, loan_request_id: int) -> LoanRequestResponse:
    """
    貸出処理

    設計書：設計書/services/貸出・返却・履歴/貸出処理_v0.2.0.md

    【処理概要】
    - 管理者が、承認済みの貸出申請に対して貸出処理を行う
    - 状態・開始日・対象備品の有効性・同一備品の貸出中重複を確認した上で貸出中に更新する

    【パラメータ】
    - current_admin (User) : 管理者検証結果 (必須)
    - db (Session) : データベース (必須)
    - loan_request_id (int) : 貸出申請（内部ID） (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - HTTPException(404) : 対象貸出申請が取得できない場合
    - HTTPException(409) : 対象貸出申請の状態が「承認済み」でない場合
    - HTTPException(409) : 対象貸出申請の開始日が今日より後の場合
    - HTTPException(409) : 対象備品が無効化されている場合
    - HTTPException(409) : 同一備品について、貸出中の別申請が存在する場合

    【処理フロー】
    1. 現在日時取得
    2. 対象貸出申請情報取得
    3. 状態確認
    4. 開始日確認
    5. 対象備品確認
    6. 貸出申請期間重複確認
    7. 貸出処理
    8. レスポンスへの変換
    9. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)
    today = now.date()

    # 2. 対象貸出申請情報取得
    target_loan_request = crud.get_loan_request_by_id(db, loan_request_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_loan_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定された貸出申請が見つかりません。",
        )

    # 3. 状態確認
    # 3.(1) 例外処理：状態が「承認済み」でない
    if target_loan_request.status != "承認済み":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="この申請は現在の状態では貸出処理できません。",
        )

    # 4. 開始日確認
    # 4.(1) 例外処理：開始日が今日より後
    if target_loan_request.start_date > today:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="開始日前のため、この申請は貸出処理できません。",
        )

    # 5. 対象備品確認
    target_equipment = crud.get_equipment_by_id(db, target_loan_request.equipment_id)
    # 5.(2) 例外処理：対象備品が無効化されている
    if target_equipment is None or not target_equipment.active_flag:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="指定された備品は無効化されているため、貸出処理できません。",
        )

    # 6. 貸出申請期間重複確認
    overlapping_count = crud.count_overlapping_loan_requests(
        db,
        target_loan_request.equipment_id,
        target_loan_request.start_date,
        target_loan_request.due_date,
        loan_request_id,
    )
    # 6.(2) 例外処理：重複件数が1以上
    if overlapping_count >= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="同一備品について、貸出中の別申請が存在するため貸出処理できません。",
        )

    # 7. 貸出処理
    lent_loan_request = crud.lend_loan_request(db, loan_request_id, current_admin.id, now)
    assert lent_loan_request is not None

    # 8. レスポンスへの変換
    loan_request_response = LoanRequestResponse(
        loan_request_id=lent_loan_request.id,
        equipment_id=lent_loan_request.equipment_id,
        start_date=lent_loan_request.start_date,
        due_date=lent_loan_request.due_date,
        purpose=lent_loan_request.purpose,
        applicant_user_id=lent_loan_request.applicant_user_id,
        status=lent_loan_request.status,
        reject_cancel_reason=lent_loan_request.reject_cancel_reason,
        approved_rejected_by_user_id=lent_loan_request.approved_rejected_by_user_id,
        lent_by_user_id=lent_loan_request.lent_by_user_id,
        returned_by_user_id=lent_loan_request.returned_by_user_id,
        cancelled_by_user_id=lent_loan_request.cancelled_by_user_id,
        requested_at=lent_loan_request.requested_at,
        approved_rejected_at=lent_loan_request.approved_rejected_at,
        lent_at=lent_loan_request.lent_at,
        returned_at=lent_loan_request.returned_at,
        cancelled_at=lent_loan_request.cancelled_at,
        return_note=lent_loan_request.return_note,
    )

    # 9. 戻り値を返却
    return loan_request_response


# ====================================================================================================
# 返却処理
# - return_loan_request : 返却処理

# 設計書：設計書/services/貸出・返却・履歴/返却処理_v0.2.0.md
# ====================================================================================================


def return_loan_request(
    current_admin: User, db: Session, loan_request_id: int, return_note: str | None
) -> LoanRequestResponse:
    """
    返却処理

    設計書：設計書/services/貸出・返却・履歴/返却処理_v0.2.0.md

    【処理概要】
    - 管理者が、貸出中の貸出申請に対して返却処理を行う
    - 状態を確認した上で返却済みに更新し、返却時状態メモを記録する

    【パラメータ】
    - current_admin (User) : 管理者検証結果 (必須)
    - db (Session) : データベース (必須)
    - loan_request_id (int) : 貸出申請（内部ID） (必須)
    - return_note (str | None) : 返却時状態メモ (任意)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - HTTPException(404) : 対象貸出申請が取得できない場合
    - HTTPException(409) : 対象貸出申請の状態が「貸出中」でない場合

    【処理フロー】
    1. 現在日時取得
    2. 対象貸出申請情報取得
    3. 状態確認
    4. 返却処理
    5. レスポンスへの変換
    6. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)

    # 2. 対象貸出申請情報取得
    target_loan_request = crud.get_loan_request_by_id(db, loan_request_id)

    # 2.(2) 例外処理：取得結果がNone
    if target_loan_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定された貸出申請が見つかりません。",
        )

    # 3. 状態確認
    # 3.(1) 例外処理：状態が「貸出中」でない
    if target_loan_request.status != "貸出中":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="この申請は現在の状態では返却処理できません。",
        )

    # 4. 返却処理
    returned_loan_request = crud.return_loan_request(db, loan_request_id, current_admin.id, return_note, now)
    assert returned_loan_request is not None

    # 5. レスポンスへの変換
    loan_request_response = LoanRequestResponse(
        loan_request_id=returned_loan_request.id,
        equipment_id=returned_loan_request.equipment_id,
        start_date=returned_loan_request.start_date,
        due_date=returned_loan_request.due_date,
        purpose=returned_loan_request.purpose,
        applicant_user_id=returned_loan_request.applicant_user_id,
        status=returned_loan_request.status,
        reject_cancel_reason=returned_loan_request.reject_cancel_reason,
        approved_rejected_by_user_id=returned_loan_request.approved_rejected_by_user_id,
        lent_by_user_id=returned_loan_request.lent_by_user_id,
        returned_by_user_id=returned_loan_request.returned_by_user_id,
        cancelled_by_user_id=returned_loan_request.cancelled_by_user_id,
        requested_at=returned_loan_request.requested_at,
        approved_rejected_at=returned_loan_request.approved_rejected_at,
        lent_at=returned_loan_request.lent_at,
        returned_at=returned_loan_request.returned_at,
        cancelled_at=returned_loan_request.cancelled_at,
        return_note=returned_loan_request.return_note,
    )

    # 6. 戻り値を返却
    return loan_request_response


def _sanitize_csv_cell(value: str) -> str:
    """CSVの数式インジェクション対策として、先頭が特定の記号のセルにシングルクォートを付与する"""

    if value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


# ====================================================================================================
# 貸出履歴CSV出力
# - export_loan_requests_csv : 貸出履歴CSV出力

# 設計書：設計書/services/貸出・返却・履歴/貸出履歴CSV出力_v0.2.0.md
# ====================================================================================================


def export_loan_requests_csv(
    current_admin: User,
    db: Session,
    start_date_from: dt.date | None,
    start_date_to: dt.date | None,
    equipment_id: int | None,
    applicant_user_id: int | None,
) -> bytes:
    """
    貸出履歴CSV出力

    設計書：設計書/services/貸出・返却・履歴/貸出履歴CSV出力_v0.2.0.md

    【処理概要】
    - 管理者が、条件（開始日範囲・備品・申請者）を指定して貸出申請の全履歴をCSV形式で出力する
    - 数式インジェクション対策として、セルの先頭が「=」「+」「-」「@」のいずれかの場合はシングルクォートを付与する

    【パラメータ】
    - current_admin (User) : 管理者検証結果 (必須)
    - db (Session) : データベース (必須)
    - start_date_from (date | None) : 開始日下限（含む） (任意)
    - start_date_to (date | None) : 開始日上限（含む） (任意)
    - equipment_id (int | None) : 備品（内部ID） (任意)
    - applicant_user_id (int | None) : 申請者（ユーザー内部ID） (任意)

    【戻り値】
    - csv_bytes (bytes) : UTF-8（BOM付き）でエンコードされたCSVデータ

    【例外処理】
    - なし

    【処理フロー】
    1. 対象貸出申請一覧取得
    2. CSV組み立て
    3. 戻り値を返却
    """

    # 1. 対象貸出申請一覧取得
    target_loan_request_list = crud.search_loan_requests(
        db, applicant_user_id, None, None, None, None, equipment_id, start_date_from, start_date_to
    )

    # 2. CSV組み立て
    # 2.(1) ヘッダー行
    header = [
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
    csv_line_list = [",".join(header)]
    # 2.(2) データ行
    for loan_request in target_loan_request_list:
        row = [
            str(loan_request.id),
            str(loan_request.equipment_id),
            str(loan_request.applicant_user_id),
            str(loan_request.start_date),
            str(loan_request.due_date),
            loan_request.purpose,
            loan_request.status,
            loan_request.reject_cancel_reason or "",
            str(loan_request.approved_rejected_by_user_id or ""),
            str(loan_request.lent_by_user_id or ""),
            str(loan_request.returned_by_user_id or ""),
            str(loan_request.cancelled_by_user_id or ""),
            str(loan_request.requested_at),
            str(loan_request.approved_rejected_at or ""),
            str(loan_request.lent_at or ""),
            str(loan_request.returned_at or ""),
            str(loan_request.cancelled_at or ""),
            loan_request.return_note or "",
        ]
        sanitized_row = [_sanitize_csv_cell(cell) for cell in row]
        csv_line_list.append(",".join(sanitized_row))
    csv_text = "\n".join(csv_line_list)

    # 3. 戻り値を返却
    csv_bytes = csv_text.encode("utf-8-sig")
    return csv_bytes


# ====================================================================================================
# 返却期限通知（前日・期限超過中）
# - notify_due_date_tomorrow : 返却期限通知（前日）
# - notify_due_date_overdue : 返却期限通知（期限超過中）

# 設計書：
# - 設計書/services/貸出・返却・履歴/返却期限通知（前日）_v0.2.0.md
# - 設計書/services/貸出・返却・履歴/返却期限通知（期限超過中）_v0.2.0.md
# ====================================================================================================


def notify_due_date_tomorrow(db: Session) -> int:
    """
    返却期限通知（前日）

    設計書：設計書/services/貸出・返却・履歴/返却期限通知（前日）_v0.2.0.md

    【処理概要】
    - 返却予定日が翌日の貸出中の貸出申請に対し、当日まだ通知していない場合に限り「返却期限」通知を生成する

    【パラメータ】
    - db (Session) : データベース (必須)

    【戻り値】
    - notified_count (int) : 通知生成件数

    【例外処理】
    - なし

    【処理フロー】
    1. 現在日時取得
    2. 対象貸出申請一覧取得
    3. 対象貸出申請への通知生成
    4. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)
    today = now.date()
    tomorrow = today + dt.timedelta(days=1)
    today_start = dt.datetime.combine(today, dt.time.min, tzinfo=dt.UTC)
    today_end = today_start + dt.timedelta(days=1)

    # 2. 対象貸出申請一覧取得
    target_loan_request_list = crud.search_loan_requests(db, None, "貸出中", None, None, tomorrow, None, None, None)

    # 3. 対象貸出申請への通知生成
    notified_count = 0
    for target_loan_request in target_loan_request_list:
        # 3.(1) 当日通知存在確認
        already_notified = crud.exists_notification_today(
            db, target_loan_request.id, "返却期限", today_start, today_end
        )
        # 3.(2) 当日未通知の場合のみ、「返却期限」通知を生成する
        if not already_notified:
            crud.create_notification(
                db, target_loan_request.applicant_user_id, "返却期限", target_loan_request.id, now
            )
            notified_count += 1

    # 4. 戻り値を返却
    return notified_count


def notify_due_date_overdue(db: Session) -> int:
    """
    返却期限通知（期限超過中）

    設計書：設計書/services/貸出・返却・履歴/返却期限通知（期限超過中）_v0.2.0.md

    【処理概要】
    - 返却予定日を過ぎても貸出中のままの貸出申請に対し、当日まだ通知していない場合に限り「返却期限」通知を生成する

    【パラメータ】
    - db (Session) : データベース (必須)

    【戻り値】
    - notified_count (int) : 通知生成件数

    【例外処理】
    - なし

    【処理フロー】
    1. 現在日時取得
    2. 対象貸出申請一覧取得
    3. 対象貸出申請への通知生成
    4. 戻り値を返却
    """

    # 1. 現在日時取得
    now = dt.datetime.now(dt.UTC)
    today = now.date()
    today_start = dt.datetime.combine(today, dt.time.min, tzinfo=dt.UTC)
    today_end = today_start + dt.timedelta(days=1)

    # 2. 対象貸出申請一覧取得
    target_loan_request_list = crud.search_loan_requests(db, None, "貸出中", None, today, None, None, None, None)

    # 3. 対象貸出申請への通知生成
    notified_count = 0
    for target_loan_request in target_loan_request_list:
        # 3.(1) 当日通知存在確認
        already_notified = crud.exists_notification_today(
            db, target_loan_request.id, "返却期限", today_start, today_end
        )
        # 3.(2) 当日未通知の場合のみ、「返却期限」通知を生成する
        if not already_notified:
            crud.create_notification(
                db, target_loan_request.applicant_user_id, "返却期限", target_loan_request.id, now
            )
            notified_count += 1

    # 4. 戻り値を返却
    return notified_count
