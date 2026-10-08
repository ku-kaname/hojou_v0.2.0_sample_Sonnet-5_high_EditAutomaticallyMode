"""
オーケストレーション処理

【概要】
エンドポイント層・日次バッチ共通処理からの呼び出しを受け、データアクセス層・共通処理を呼び出して業務処理を行う
"""

import datetime as dt
import os

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import auth, crud
from app.models import User
from app.schemas import (
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
