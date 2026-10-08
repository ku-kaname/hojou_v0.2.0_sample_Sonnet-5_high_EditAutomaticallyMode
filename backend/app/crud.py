"""
データアクセス処理

【概要】
DBに対するCRUD操作を提供する
"""

import datetime as dt

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import User

# ====================================================================================================
# ユーザー情報取得
# - get_user_by_user_id : ユーザー情報取得

# 設計書：設計書/CRUD/認証・ユーザー管理/ユーザー情報取得_v0.2.0.md
# ====================================================================================================


def get_user_by_user_id(db: Session, user_id: str) -> User | None:
    """
    ユーザー情報取得

    設計書：設計書/CRUD/認証・ユーザー管理/ユーザー情報取得_v0.2.0.md

    【処理概要】
    - ユーザーID（業務キー）をもとにユーザー情報を1件取得する（有効フラグによる絞り込みは行わない）

    【パラメータ】
    - db (Session) : データベース (必須)
    - user_id (str) : ユーザーID (必須)

    【戻り値】
    - user (User | None) : ユーザー情報（見つからない場合はNone）

    【例外処理】
    - なし

    【処理フロー】
    1. ユーザー情報取得
    2. 戻り値を返却
    """

    # 1. ユーザー情報取得
    user = db.query(User).filter(User.user_id == user_id).one_or_none()

    # 2. 戻り値を返却
    return user


# ====================================================================================================
# 全ユーザー情報取得
# - get_all_user : 全ユーザー情報取得

# 設計書：設計書/CRUD/認証・ユーザー管理/全ユーザー情報取得_v0.2.0.md
# ====================================================================================================


def get_all_user(db: Session) -> list[User]:
    """
    全ユーザー情報取得

    設計書：設計書/CRUD/認証・ユーザー管理/全ユーザー情報取得_v0.2.0.md

    【処理概要】
    - 登録されている全てのユーザー情報を、有効フラグに関わらず全件取得する

    【パラメータ】
    - db (Session) : データベース (必須)

    【戻り値】
    - user_list (list[User]) : ユーザー情報リスト（ユーザーIDの昇順）

    【例外処理】
    - なし

    【処理フロー】
    1. 全ユーザー情報取得
    2. 戻り値を返却
    """

    # 1. 全ユーザー情報取得
    user_list = db.query(User).order_by(User.user_id.asc()).all()

    # 2. 戻り値を返却
    return user_list


# ====================================================================================================
# ユーザー作成
# - create_user : ユーザー作成

# 設計書：設計書/CRUD/認証・ユーザー管理/ユーザー作成_v0.2.0.md
# ====================================================================================================


def create_user(
    db: Session,
    today: dt.datetime,
    user_id: str,
    name: str,
    department: str,
    hashed_password: str,
    role: str,
) -> User:
    """
    ユーザー作成

    設計書：設計書/CRUD/認証・ユーザー管理/ユーザー作成_v0.2.0.md

    【処理概要】
    - ユーザー情報をデータベースへ新規登録する
    - 有効フラグ・初回パスワード変更要否フラグ・トークン世代・連続認証失敗回数は固定の初期値を設定する

    【パラメータ】
    - db (Session) : データベース (必須)
    - today (datetime) : 現在日時 (必須)
    - user_id (str) : ユーザーID (必須)
    - name (str) : 氏名 (必須)
    - department (str) : 所属 (任意)
    - hashed_password (str) : パスワードハッシュ (必須)
    - role (str) : ロール (必須)

    【戻り値】
    - user (User) : 登録したユーザー情報

    【例外処理】
    - なし

    【処理フロー】
    1. ユーザー情報登録
    2. 戻り値を返却
    """

    # 1. ユーザー情報登録
    user = User(
        user_id=user_id,
        name=name,
        department=department,
        hashed_password=hashed_password,
        role=role,
        active_flag=True,
        password_change_required_flag=True,
        token_generation=0,
        login_failure_count=0,
        created_at=today,
        updated_at=today,
    )
    db.add(user)
    db.flush()

    # 2. 戻り値を返却
    return user


# ====================================================================================================
# ユーザー更新
# - update_user : ユーザー情報更新
# - update_user_password : ユーザーパスワード更新
# - update_user_login_result : ユーザーログイン結果更新
# - update_user_active_flag : ユーザー有効化状態更新

# 設計書：
# - 設計書/CRUD/認証・ユーザー管理/ユーザー情報更新_v0.2.0.md
# - 設計書/CRUD/認証・ユーザー管理/ユーザーパスワード更新_v0.2.0.md
# - 設計書/CRUD/認証・ユーザー管理/ユーザーログイン結果更新_v0.2.0.md
# - 設計書/CRUD/認証・ユーザー管理/ユーザー有効化状態更新_v0.2.0.md
# ====================================================================================================


def update_user(
    db: Session,
    today: dt.datetime,
    user_id: str,
    name: str,
    department: str,
    role: str,
    token_generation: int,
) -> User | None:
    """
    ユーザー情報更新

    設計書：設計書/CRUD/認証・ユーザー管理/ユーザー情報更新_v0.2.0.md

    【処理概要】
    - ユーザーの氏名・所属・ロール・トークン世代を更新する（トークン世代の更新値は呼出元が決定する）

    【パラメータ】
    - db (Session) : データベース (必須)
    - today (datetime) : 現在日時 (必須)
    - user_id (str) : ユーザーID (必須)
    - name (str) : 氏名 (必須)
    - department (str) : 所属 (任意)
    - role (str) : ロール (必須)
    - token_generation (int) : トークン世代 (必須)

    【戻り値】
    - user (User | None) : 更新後のユーザー情報（見つからない場合はNone）

    【例外処理】
    - なし

    【処理フロー】
    1. ユーザー情報更新
    2. 戻り値を返却
    """

    # 1. ユーザー情報更新
    user = get_user_by_user_id(db, user_id)
    if user is None:
        return None
    user.name = name
    user.department = department
    user.role = role
    user.token_generation = token_generation
    user.updated_at = today
    db.flush()

    # 2. 戻り値を返却
    return user


def update_user_password(
    db: Session,
    today: dt.datetime,
    user_id: str,
    hashed_password: str,
    password_change_required_flag: bool,
    token_generation: int,
) -> User | None:
    """
    ユーザーパスワード更新

    設計書：設計書/CRUD/認証・ユーザー管理/ユーザーパスワード更新_v0.2.0.md

    【処理概要】
    - ユーザーのパスワードハッシュ・初回パスワード変更要否フラグ・トークン世代を更新する（設定値は呼出元が決定する）

    【パラメータ】
    - db (Session) : データベース (必須)
    - today (datetime) : 現在日時 (必須)
    - user_id (str) : ユーザーID (必須)
    - hashed_password (str) : パスワードハッシュ (必須)
    - password_change_required_flag (bool) : 初回パスワード変更要否フラグ (必須)
    - token_generation (int) : トークン世代 (必須)

    【戻り値】
    - user (User | None) : 更新後のユーザー情報（見つからない場合はNone）

    【例外処理】
    - なし

    【処理フロー】
    1. ユーザーパスワード更新
    2. 戻り値を返却
    """

    # 1. ユーザーパスワード更新
    user = get_user_by_user_id(db, user_id)
    if user is None:
        return None
    user.hashed_password = hashed_password
    user.password_change_required_flag = password_change_required_flag
    user.token_generation = token_generation
    user.updated_at = today
    db.flush()

    # 2. 戻り値を返却
    return user


def update_user_login_result(
    db: Session,
    today: dt.datetime,
    user_id: str,
    login_failure_count: int,
    locked_until: dt.datetime | None,
) -> User | None:
    """
    ユーザーログイン結果更新

    設計書：設計書/CRUD/認証・ユーザー管理/ユーザーログイン結果更新_v0.2.0.md

    【処理概要】
    - ログイン試行の結果に応じて、連続認証失敗回数・ロック解除日時を更新する（設定値は呼出元が決定する）

    【パラメータ】
    - db (Session) : データベース (必須)
    - today (datetime) : 現在日時 (必須)
    - user_id (str) : ユーザーID (必須)
    - login_failure_count (int) : 連続認証失敗回数 (必須)
    - locked_until (datetime | None) : ロック解除日時 (任意)

    【戻り値】
    - user (User | None) : 更新後のユーザー情報（見つからない場合はNone）

    【例外処理】
    - なし

    【処理フロー】
    1. ユーザーログイン結果更新
    2. 戻り値を返却
    """

    # 1. ユーザーログイン結果更新
    user = get_user_by_user_id(db, user_id)
    if user is None:
        return None
    user.login_failure_count = login_failure_count
    user.locked_until = locked_until
    user.updated_at = today
    db.flush()

    # 2. 戻り値を返却
    return user


def update_user_active_flag(
    db: Session,
    today: dt.datetime,
    user_id: str,
    active_flag: bool,
    token_generation: int,
) -> User | None:
    """
    ユーザー有効化状態更新

    設計書：設計書/CRUD/認証・ユーザー管理/ユーザー有効化状態更新_v0.2.0.md

    【処理概要】
    - ユーザーの有効フラグ・トークン世代を更新する（トークン世代の更新値は呼出元が決定する）

    【パラメータ】
    - db (Session) : データベース (必須)
    - today (datetime) : 現在日時 (必須)
    - user_id (str) : ユーザーID (必須)
    - active_flag (bool) : 有効フラグ (必須)
    - token_generation (int) : トークン世代 (必須)

    【戻り値】
    - user (User | None) : 更新後のユーザー情報（見つからない場合はNone）

    【例外処理】
    - なし

    【処理フロー】
    1. ユーザー有効化状態更新
    2. 戻り値を返却
    """

    # 1. ユーザー有効化状態更新
    user = get_user_by_user_id(db, user_id)
    if user is None:
        return None
    user.active_flag = active_flag
    user.token_generation = token_generation
    user.updated_at = today
    db.flush()

    # 2. 戻り値を返却
    return user


# ====================================================================================================
# 有効管理者数取得
# - count_active_admin : 有効管理者数取得

# 設計書：設計書/CRUD/認証・ユーザー管理/有効管理者数取得_v0.2.0.md
# ====================================================================================================


def count_active_admin(db: Session) -> int:
    """
    有効管理者数取得

    設計書：設計書/CRUD/認証・ユーザー管理/有効管理者数取得_v0.2.0.md

    【処理概要】
    - ロールが"管理者"かつ有効フラグがtrueのユーザー件数を取得する

    【パラメータ】
    - db (Session) : データベース (必須)

    【戻り値】
    - count (int) : 件数

    【例外処理】
    - なし

    【処理フロー】
    1. 有効管理者数取得
    2. 戻り値を返却
    """

    # 1. 有効管理者数取得
    count = (
        db.query(func.count(User.id))
        .filter(User.role == "管理者", User.active_flag.is_(True))
        .scalar()
    )

    # 2. 戻り値を返却
    return count
