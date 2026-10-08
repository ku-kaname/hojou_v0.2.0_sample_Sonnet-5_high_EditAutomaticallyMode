"""
データアクセス処理

【概要】
DBに対するCRUD操作を提供する
"""

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Equipment, LoanRequest, User

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


# ====================================================================================================
# 備品管理専用データ構造
# - EquipmentSearchResult : 備品検索結果
# - ReservationResult : 予約結果
# - EquipmentCreateItem : 備品登録項目

# 設計書：
# - 設計書/CRUD/備品管理/備品検索一覧取得_v0.2.0.md
# - 設計書/CRUD/備品管理/備品予約状況取得_v0.2.0.md
# - 設計書/CRUD/備品管理/複数備品同時登録_v0.2.0.md
# ====================================================================================================


@dataclass
class EquipmentSearchResult:
    """
    備品検索結果

    【概要】
    備品検索・一覧取得専用の戻り値（ORMモデルではない）。EQUIPMENTの全項目と、貸出中の場合の返却予定日を保持する

    【属性】
    - id (int): 内部ID
    - asset_number (str): 資産番号
    - name (str): 備品名
    - category (str): 分類
    - description (str): 説明
    - location (str): 保管場所
    - active_flag (bool): 有効フラグ
    - created_at (datetime): 作成日時
    - updated_at (datetime): 更新日時
    - due_date (date | None): 返却予定日（貸出中の場合のみ値を持つ）
    """

    id: int
    asset_number: str
    name: str
    category: str
    description: str
    location: str
    active_flag: bool
    created_at: dt.datetime
    updated_at: dt.datetime
    due_date: dt.date | None


@dataclass
class ReservationResult:
    """
    予約結果

    【概要】
    備品予約状況取得専用の戻り値（ORMモデルではない）。LOAN_REQUESTの内部ID・開始日・返却予定日・状態と申請者氏名を保持する

    【属性】
    - id (int): 内部ID
    - start_date (date): 開始日
    - due_date (date): 返却予定日
    - status (str): 状態
    - applicant_name (str): 申請者氏名
    """

    id: int
    start_date: dt.date
    due_date: dt.date
    status: str
    applicant_name: str


@dataclass
class EquipmentCreateItem:
    """
    備品登録項目

    【概要】
    複数備品同時登録専用の入力項目（ORMモデルではない）。資産番号・備品名・分類・説明・保管場所を保持する

    【属性】
    - asset_number (str): 資産番号
    - name (str): 備品名
    - category (str): 分類
    - description (str): 説明
    - location (str): 保管場所
    """

    asset_number: str
    name: str
    category: str
    description: str
    location: str


# ====================================================================================================
# 備品検索・一覧取得
# - search_equipment : 備品検索・一覧取得

# 設計書：設計書/CRUD/備品管理/備品検索一覧取得_v0.2.0.md
# ====================================================================================================


def search_equipment(
    db: Session,
    category: str | None,
    keyword: str | None,
    loan_status: str | None,
    include_inactive: bool,
) -> list[EquipmentSearchResult]:
    """
    備品検索・一覧取得

    設計書：設計書/CRUD/備品管理/備品検索一覧取得_v0.2.0.md

    【処理概要】
    - EQUIPMENTテーブルと、LOAN_REQUESTテーブルのうち状態が「貸出中」の行のみを備品の内部IDで左外部結合し、
      各備品の現在の貸出状態と、貸出中の場合の返却予定日を導出する
    - 分類・キーワード・貸出状態・有効フラグで絞り込み、資産番号の昇順で返却する

    【パラメータ】
    - db (Session) : データベース (必須)
    - category (str | None) : 分類 (任意)
    - keyword (str | None) : キーワード (任意)
    - loan_status (str | None) : 貸出状態 (任意)
    - include_inactive (bool) : 無効化済み備品を含める (必須)

    【戻り値】
    - equipment_search_result_list (list[EquipmentSearchResult]) :
      備品検索結果リスト（該当する備品が無い場合は空のリスト）

    【例外処理】
    - なし

    【処理フロー】
    1. 備品一覧取得
    2. 戻り値を返却
    """

    # 1. 備品一覧取得
    # 1.(1) EQUIPMENTテーブルと、LOAN_REQUESTテーブルの「貸出中」の行を左外部結合する
    loan_request_join_condition = and_(
        LoanRequest.equipment_id == Equipment.id,
        LoanRequest.status == "貸出中",
    )
    query = db.query(Equipment, LoanRequest.due_date).outerjoin(
        LoanRequest, loan_request_join_condition
    )

    # 1.(2) 分類で絞り込み
    if category is not None:
        query = query.filter(Equipment.category == category)

    # 1.(3) キーワード（備品名の部分一致）で絞り込み
    if keyword is not None:
        query = query.filter(Equipment.name.contains(keyword))

    # 1.(4) 貸出状態で絞り込み
    if loan_status == "貸出中":
        query = query.filter(LoanRequest.id.isnot(None))
    elif loan_status == "貸出可":
        query = query.filter(LoanRequest.id.is_(None))

    # 1.(5) 有効フラグで絞り込み
    if not include_inactive:
        query = query.filter(Equipment.active_flag.is_(True))

    # 1.(6) 資産番号の昇順で取得
    row_list = query.order_by(Equipment.asset_number.asc()).all()
    equipment_search_result_list = [
        EquipmentSearchResult(
            id=equipment.id,
            asset_number=equipment.asset_number,
            name=equipment.name,
            category=equipment.category,
            description=equipment.description,
            location=equipment.location,
            active_flag=equipment.active_flag,
            created_at=equipment.created_at,
            updated_at=equipment.updated_at,
            due_date=due_date,
        )
        for equipment, due_date in row_list
    ]

    # 2. 戻り値を返却
    return equipment_search_result_list


# ====================================================================================================
# 備品情報取得
# - get_equipment_by_id : 備品情報取得
# - get_equipment_by_asset_number : 資産番号重複チェック

# 設計書：
# - 設計書/CRUD/備品管理/備品情報取得_v0.2.0.md
# - 設計書/CRUD/備品管理/資産番号重複チェック_v0.2.0.md
# ====================================================================================================


def get_equipment_by_id(db: Session, equipment_id: int) -> Equipment | None:
    """
    備品情報取得

    設計書：設計書/CRUD/備品管理/備品情報取得_v0.2.0.md

    【処理概要】
    - 内部IDをもとに備品情報を1件取得する（有効フラグによる絞り込みは行わない）

    【パラメータ】
    - db (Session) : データベース (必須)
    - equipment_id (int) : 内部ID (必須)

    【戻り値】
    - equipment (Equipment | None) : 備品情報（見つからない場合はNone）

    【例外処理】
    - なし

    【処理フロー】
    1. 備品情報取得
    2. 戻り値を返却
    """

    # 1. 備品情報取得
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).one_or_none()

    # 2. 戻り値を返却
    return equipment


def get_equipment_by_asset_number(db: Session, asset_number: str) -> Equipment | None:
    """
    資産番号重複チェック

    設計書：設計書/CRUD/備品管理/資産番号重複チェック_v0.2.0.md

    【処理概要】
    - 資産番号をもとに備品情報を1件取得する（有効フラグによる絞り込みは行わない）

    【パラメータ】
    - db (Session) : データベース (必須)
    - asset_number (str) : 資産番号 (必須)

    【戻り値】
    - equipment (Equipment | None) : 備品情報（該当する備品が無い場合はNone）

    【例外処理】
    - なし

    【処理フロー】
    1. 資産番号重複チェック
    2. 戻り値を返却
    """

    # 1. 資産番号重複チェック
    equipment = (
        db.query(Equipment).filter(Equipment.asset_number == asset_number).one_or_none()
    )

    # 2. 戻り値を返却
    return equipment


# ====================================================================================================
# 備品登録
# - create_equipment : 備品登録
# - bulk_create_equipment : 複数備品同時登録

# 設計書：
# - 設計書/CRUD/備品管理/備品登録_v0.2.0.md
# - 設計書/CRUD/備品管理/複数備品同時登録_v0.2.0.md
# ====================================================================================================


def create_equipment(
    db: Session,
    asset_number: str,
    name: str,
    category: str,
    description: str,
    location: str,
    today: dt.datetime,
) -> Equipment:
    """
    備品登録

    設計書：設計書/CRUD/備品管理/備品登録_v0.2.0.md

    【処理概要】
    - 備品情報をデータベースへ新規登録する（有効フラグは固定の初期値を設定する）

    【パラメータ】
    - db (Session) : データベース (必須)
    - asset_number (str) : 資産番号 (必須)
    - name (str) : 備品名 (必須)
    - category (str) : 分類 (必須)
    - description (str) : 説明 (任意)
    - location (str) : 保管場所 (任意)
    - today (datetime) : 現在日時 (必須)

    【戻り値】
    - equipment (Equipment) : 登録した備品情報

    【例外処理】
    - なし

    【処理フロー】
    1. 備品情報登録
    2. 戻り値を返却
    """

    # 1. 備品情報登録
    equipment = Equipment(
        asset_number=asset_number,
        name=name,
        category=category,
        description=description,
        location=location,
        active_flag=True,
        created_at=today,
        updated_at=today,
    )
    db.add(equipment)
    db.flush()

    # 2. 戻り値を返却
    return equipment


def bulk_create_equipment(
    db: Session,
    today: dt.datetime,
    equipment_create_list: list[EquipmentCreateItem],
) -> list[Equipment]:
    """
    複数備品同時登録

    設計書：設計書/CRUD/備品管理/複数備品同時登録_v0.2.0.md

    【処理概要】
    - 検証済みの複数の備品情報を一括でデータベースへ登録する（有効フラグは固定の初期値を設定する）

    【パラメータ】
    - db (Session) : データベース (必須)
    - today (datetime) : 現在日時 (必須)
    - equipment_create_list (list[EquipmentCreateItem]) : 備品登録情報リスト (必須)

    【戻り値】
    - equipment_list (list[Equipment]) : 登録した備品情報リスト（入力値と同じ件数・順序）

    【例外処理】
    - なし

    【処理フロー】
    1. 複数備品情報登録
    2. 戻り値を返却
    """

    # 1. 複数備品情報登録
    equipment_list = [
        Equipment(
            asset_number=equipment_create_item.asset_number,
            name=equipment_create_item.name,
            category=equipment_create_item.category,
            description=equipment_create_item.description,
            location=equipment_create_item.location,
            active_flag=True,
            created_at=today,
            updated_at=today,
        )
        for equipment_create_item in equipment_create_list
    ]
    db.add_all(equipment_list)
    db.flush()

    # 2. 戻り値を返却
    return equipment_list


# ====================================================================================================
# 備品情報更新
# - update_equipment : 備品情報更新
# - update_equipment_active_flag : 備品有効化状態更新

# 設計書：
# - 設計書/CRUD/備品管理/備品情報更新_v0.2.0.md
# - 設計書/CRUD/備品管理/備品有効化状態更新_v0.2.0.md
# ====================================================================================================


def update_equipment(
    db: Session,
    today: dt.datetime,
    equipment_id: int,
    asset_number: str,
    name: str,
    category: str,
    description: str,
    location: str,
) -> Equipment | None:
    """
    備品情報更新

    設計書：設計書/CRUD/備品管理/備品情報更新_v0.2.0.md

    【処理概要】
    - 備品の資産番号・備品名・分類・説明・保管場所を更新する

    【パラメータ】
    - db (Session) : データベース (必須)
    - today (datetime) : 現在日時 (必須)
    - equipment_id (int) : 内部ID (必須)
    - asset_number (str) : 資産番号 (必須)
    - name (str) : 備品名 (必須)
    - category (str) : 分類 (必須)
    - description (str) : 説明 (任意)
    - location (str) : 保管場所 (任意)

    【戻り値】
    - equipment (Equipment | None) : 更新後の備品情報（見つからない場合はNone）

    【例外処理】
    - なし

    【処理フロー】
    1. 備品情報更新
    2. 戻り値を返却
    """

    # 1. 備品情報更新
    equipment = get_equipment_by_id(db, equipment_id)
    if equipment is None:
        return None
    equipment.asset_number = asset_number
    equipment.name = name
    equipment.category = category
    equipment.description = description
    equipment.location = location
    equipment.updated_at = today
    db.flush()

    # 2. 戻り値を返却
    return equipment


def update_equipment_active_flag(
    db: Session,
    today: dt.datetime,
    equipment_id: int,
    active_flag: bool,
) -> Equipment | None:
    """
    備品有効化状態更新

    設計書：設計書/CRUD/備品管理/備品有効化状態更新_v0.2.0.md

    【処理概要】
    - 備品の有効フラグを更新する

    【パラメータ】
    - db (Session) : データベース (必須)
    - today (datetime) : 現在日時 (必須)
    - equipment_id (int) : 内部ID (必須)
    - active_flag (bool) : 有効フラグ (必須)

    【戻り値】
    - equipment (Equipment | None) : 更新後の備品情報（見つからない場合はNone）

    【例外処理】
    - なし

    【処理フロー】
    1. 備品有効化状態更新
    2. 戻り値を返却
    """

    # 1. 備品有効化状態更新
    equipment = get_equipment_by_id(db, equipment_id)
    if equipment is None:
        return None
    equipment.active_flag = active_flag
    equipment.updated_at = today
    db.flush()

    # 2. 戻り値を返却
    return equipment


# ====================================================================================================
# 備品予約状況取得
# - get_reservations_by_equipment_id : 備品予約状況取得

# 設計書：設計書/CRUD/備品管理/備品予約状況取得_v0.2.0.md
# ====================================================================================================


def get_reservations_by_equipment_id(db: Session, equipment_id: int) -> list[ReservationResult]:
    """
    備品予約状況取得

    設計書：設計書/CRUD/備品管理/備品予約状況取得_v0.2.0.md

    【処理概要】
    - 指定した備品について、承認済み・貸出中の申請の期間を、申請者のUSERテーブルと結合して取得する
    - 申請者氏名は常に取得し、レスポンスへ含めるかどうかの判定は呼出元の責務とする

    【パラメータ】
    - db (Session) : データベース (必須)
    - equipment_id (int) : 備品（内部ID） (必須)

    【戻り値】
    - reservation_list (list[ReservationResult]) : 予約情報リスト（開始日の昇順。該当する申請が無い場合は空のリスト）

    【例外処理】
    - なし

    【処理フロー】
    1. 備品予約状況取得
    2. 戻り値を返却
    """

    # 1. 備品予約状況取得
    row_list = (
        db.query(
            LoanRequest.id,
            LoanRequest.start_date,
            LoanRequest.due_date,
            LoanRequest.status,
            User.name,
        )
        .join(User, User.id == LoanRequest.applicant_user_id)
        .filter(
            LoanRequest.equipment_id == equipment_id,
            LoanRequest.status.in_(["承認済み", "貸出中"]),
        )
        .order_by(LoanRequest.start_date.asc())
        .all()
    )
    reservation_list = [
        ReservationResult(
            id=loan_request_id,
            start_date=start_date,
            due_date=due_date,
            status=status,
            applicant_name=applicant_name,
        )
        for loan_request_id, start_date, due_date, status, applicant_name in row_list
    ]

    # 2. 戻り値を返却
    return reservation_list


# ====================================================================================================
# 資産番号一覧重複チェック
# - get_existing_asset_numbers : 資産番号一覧重複チェック

# 設計書：設計書/CRUD/備品管理/資産番号一覧重複チェック_v0.2.0.md
# ====================================================================================================


def get_existing_asset_numbers(db: Session, asset_number_list: list[str]) -> list[str]:
    """
    資産番号一覧重複チェック

    設計書：設計書/CRUD/備品管理/資産番号一覧重複チェック_v0.2.0.md

    【処理概要】
    - 入力値の資産番号リストのうち、EQUIPMENTテーブルに既に存在するものを取得する

    【パラメータ】
    - db (Session) : データベース (必須)
    - asset_number_list (list[str]) : 資産番号リスト (必須)

    【戻り値】
    - existing_asset_number_list (list[str]) : 登録済み資産番号リスト（既存の資産番号が無い場合は空のリスト）

    【例外処理】
    - なし

    【処理フロー】
    1. 資産番号一覧重複チェック
    2. 戻り値を返却
    """

    # 1. 資産番号一覧重複チェック
    row_list = (
        db.query(Equipment.asset_number)
        .filter(Equipment.asset_number.in_(asset_number_list))
        .all()
    )
    existing_asset_number_list = [asset_number for (asset_number,) in row_list]

    # 2. 戻り値を返却
    return existing_asset_number_list
