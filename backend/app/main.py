"""
アプリ起動構成

【概要】
FastAPIアプリケーションの生成、CORS設定、ヘルスチェックエンドポイントを提供する
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, File, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import auth, services
from app.database import SessionLocal, engine, get_db
from app.models import User
from app.scheduler import shutdown_scheduler, start_scheduler
from app.schemas import (
    EquipmentBulkImportResponse,
    EquipmentCreateRequest,
    EquipmentResponse,
    EquipmentUpdateRequest,
    LoanRequestAdminCancelRequest,
    LoanRequestCancelRequest,
    LoanRequestCreateRequest,
    LoanRequestRejectRequest,
    LoanRequestResponse,
    NotificationResponse,
    PasswordChangeRequest,
    PasswordResetRequest,
    ReservationResponse,
    TokenResponse,
    UserCreateRequest,
    UserCreateResponse,
    UserGetResponse,
    UserUpdateRequest,
    UserUpdateResponse,
)

# ====================================================================================================
# アプリ起動・終了処理
# - _lifespan : アプリ起動・終了処理

# 設計書：設計書/アーキテクチャ方針_v0.2.0.md
# ====================================================================================================


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    アプリ起動・終了処理

    設計書：設計書/アーキテクチャ方針_v0.2.0.md

    【処理概要】
    - アプリ起動時に日次バッチのスケジューラを起動し、初期管理者アカウントを作成する
    - アプリ終了時にスケジューラを停止する

    【パラメータ】
    - app (FastAPI) : FastAPIアプリケーション (必須)

    【戻り値】
    - なし

    【例外処理】
    - なし

    【処理フロー】
    1. スケジューラの起動
    2. 初期管理者アカウントの作成
    3. アプリ終了までの待機
    4. スケジューラの停止
    """

    # 1. スケジューラの起動
    start_scheduler()

    # 2. 初期管理者アカウントの作成
    # 2.(1) DBセッションを生成（get_dbはFastAPIの依存性注入専用のため、直接SessionLocalを使用する）
    db = SessionLocal()
    try:
        # 2.(2) 初期管理者アカウントの作成
        services.create_initial_admin(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # 3. アプリ終了までの待機
    yield

    # 4. スケジューラの停止
    shutdown_scheduler()


app = FastAPI(title="社内備品貸出管理Webアプリ", lifespan=_lifespan)

_cors_allowed_origins = [
    origin.strip() for origin in os.environ["CORS_ALLOWED_ORIGINS"].split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====================================================================================================
# ヘルスチェック
# - health_check : ヘルスチェック

# 設計書：設計書/エンドポイント_v0.2.0.md
# ====================================================================================================


@app.get("/health-check")
def health_check() -> JSONResponse:
    """
    ヘルスチェック

    設計書：設計書/エンドポイント_v0.2.0.md

    【処理概要】
    - データベースへの疎通確認を行う
    - アーキテクチャ方針の例外規定により、オーケストレーション層を経由せず本処理から直接確認する

    【パラメータ】
    - なし

    【戻り値】
    - response (JSONResponse) : 疎通確認結果（成功：200／失敗：503）

    【例外処理】
    - なし（DB接続失敗時は例外を発生させず、503レスポンスとして返却する）

    【処理フロー】
    1. データベースへの疎通確認
    2. 戻り値を返却
    """

    # 1. データベースへの疎通確認
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        # 2. 戻り値を返却（疎通失敗）
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error"},
        )

    # 2. 戻り値を返却（疎通成功）
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ok"})


# ====================================================================================================
# ログイン・ログアウト
# - login_endpoint : ログイン
# - logout_endpoint : ログアウト

# 設計書：
# - 設計書/main/認証・ユーザー管理/ログイン_v0.2.0.md
# - 設計書/main/認証・ユーザー管理/ログアウト_v0.2.0.md
# ====================================================================================================


@app.post("/token")
def login_endpoint(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    ログイン

    設計書：設計書/main/認証・ユーザー管理/ログイン_v0.2.0.md

    【処理概要】
    - ユーザーID・パスワードによる認証を行い、成功時にアクセストークンを発行する

    【パラメータ】
    - form_data (OAuth2PasswordRequestForm) : ユーザーID・パスワード (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - token_response (TokenResponse) : トークン発行レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. ログイン処理の呼び出し
    2. 戻り値を返却
    """

    # 1. ログイン処理の呼び出し
    token_response = services.login(db, form_data.username, form_data.password)

    # 2. 戻り値を返却
    return token_response


@app.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_endpoint(
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    ログアウト

    設計書：設計書/main/認証・ユーザー管理/ログアウト_v0.2.0.md

    【処理概要】
    - トークン世代を進め、発行済みのアクセストークンを無効化する

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - なし

    【例外処理】
    - なし

    【処理フロー】
    1. ログアウト処理の呼び出し
    2. 戻り値を返却
    """

    # 1. ログアウト処理の呼び出し
    services.logout(db, current_user)

    # 2. 戻り値を返却（なし）
    return None


# ====================================================================================================
# パスワード変更・初期化
# - change_password_endpoint : パスワード変更
# - reset_password_endpoint : パスワード初期化

# 設計書：
# - 設計書/main/認証・ユーザー管理/パスワード変更_v0.2.0.md
# - 設計書/main/認証・ユーザー管理/パスワード初期化_v0.2.0.md
# ====================================================================================================


@app.patch("/users/me/password")
def change_password_endpoint(
    password_change_request: PasswordChangeRequest,
    current_user: User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    パスワード変更

    設計書：設計書/main/認証・ユーザー管理/パスワード変更_v0.2.0.md

    【処理概要】
    - ログイン中のユーザー本人のパスワードを変更する

    【パラメータ】
    - password_change_request (PasswordChangeRequest) : パスワード変更リクエスト (必須)
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - token_response (TokenResponse) : トークン発行レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. パスワード変更処理の呼び出し
    2. 戻り値を返却
    """

    # 1. パスワード変更処理の呼び出し
    token_response = services.change_password(
        db,
        current_user,
        password_change_request.current_password,
        password_change_request.new_password,
    )

    # 2. 戻り値を返却
    return token_response


@app.patch("/users/{user_id}/reset-password")
def reset_password_endpoint(
    user_id: str,
    password_reset_request: PasswordResetRequest,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> UserUpdateResponse:
    """
    パスワード初期化

    設計書：設計書/main/認証・ユーザー管理/パスワード初期化_v0.2.0.md

    【処理概要】
    - 管理者が、既存ユーザーのパスワードを初期化する

    【パラメータ】
    - user_id (str) : ユーザーID (必須)
    - password_reset_request (PasswordResetRequest) : パスワード初期化リクエスト (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - user_response (UserUpdateResponse) : ユーザー情報更新レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. パスワード初期化処理の呼び出し
    2. 戻り値を返却
    """

    # 1. パスワード初期化処理の呼び出し
    user_response = services.reset_password(db, user_id, password_reset_request.initial_password)

    # 2. 戻り値を返却
    return user_response


# ====================================================================================================
# ユーザー登録・編集
# - register_user_endpoint : ユーザー登録
# - update_user_endpoint : ユーザー編集

# 設計書：
# - 設計書/main/認証・ユーザー管理/ユーザー登録_v0.2.0.md
# - 設計書/main/認証・ユーザー管理/ユーザー編集_v0.2.0.md
# ====================================================================================================


@app.post("/users", status_code=status.HTTP_201_CREATED)
def register_user_endpoint(
    user_create_request: UserCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> UserCreateResponse:
    """
    ユーザー登録

    設計書：設計書/main/認証・ユーザー管理/ユーザー登録_v0.2.0.md

    【処理概要】
    - 管理者が、新しいユーザーを登録する

    【パラメータ】
    - user_create_request (UserCreateRequest) : ユーザー作成リクエスト (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - user_response (UserCreateResponse) : ユーザー作成レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. ユーザー登録処理の呼び出し
    2. 戻り値を返却
    """

    # 1. ユーザー登録処理の呼び出し
    user_response = services.register_user(
        db,
        user_create_request.user_id,
        user_create_request.name,
        user_create_request.department,
        user_create_request.role,
        user_create_request.initial_password,
    )

    # 2. 戻り値を返却
    return user_response


@app.put("/users/{user_id}")
def update_user_endpoint(
    user_id: str,
    user_update_request: UserUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> UserUpdateResponse:
    """
    ユーザー編集

    設計書：設計書/main/認証・ユーザー管理/ユーザー編集_v0.2.0.md

    【処理概要】
    - 管理者が、既存ユーザーの氏名・所属・ロールを変更する

    【パラメータ】
    - user_id (str) : ユーザーID (必須)
    - user_update_request (UserUpdateRequest) : ユーザー更新リクエスト (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - user_response (UserUpdateResponse) : ユーザー情報更新レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. ユーザー編集処理の呼び出し
    2. 戻り値を返却
    """

    # 1. ユーザー編集処理の呼び出し
    user_response = services.update_user_info(
        db,
        user_id,
        user_update_request.name,
        user_update_request.department,
        user_update_request.role,
    )

    # 2. 戻り値を返却
    return user_response


# ====================================================================================================
# ユーザー有効化状態変更
# - deactivate_user_endpoint : ユーザー無効化
# - activate_user_endpoint : ユーザー再有効化

# 設計書：
# - 設計書/main/認証・ユーザー管理/ユーザー無効化_v0.2.0.md
# - 設計書/main/認証・ユーザー管理/ユーザー再有効化_v0.2.0.md
# ====================================================================================================


@app.patch("/users/{user_id}/deactivate")
def deactivate_user_endpoint(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> UserUpdateResponse:
    """
    ユーザー無効化

    設計書：設計書/main/認証・ユーザー管理/ユーザー無効化_v0.2.0.md

    【処理概要】
    - 管理者が、既存ユーザーを無効化する

    【パラメータ】
    - user_id (str) : ユーザーID (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - user_response (UserUpdateResponse) : ユーザー情報更新レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. ユーザー無効化処理の呼び出し
    2. 戻り値を返却
    """

    # 1. ユーザー無効化処理の呼び出し
    user_response = services.deactivate_user(db, user_id)

    # 2. 戻り値を返却
    return user_response


@app.patch("/users/{user_id}/activate")
def activate_user_endpoint(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> UserUpdateResponse:
    """
    ユーザー再有効化

    設計書：設計書/main/認証・ユーザー管理/ユーザー再有効化_v0.2.0.md

    【処理概要】
    - 管理者が、無効化済みのユーザーを再度有効化する

    【パラメータ】
    - user_id (str) : ユーザーID (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - user_response (UserUpdateResponse) : ユーザー情報更新レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. ユーザー再有効化処理の呼び出し
    2. 戻り値を返却
    """

    # 1. ユーザー再有効化処理の呼び出し
    user_response = services.activate_user(db, user_id)

    # 2. 戻り値を返却
    return user_response


# ====================================================================================================
# ユーザー情報取得
# - get_users_endpoint : ユーザー一覧取得
# - get_user_endpoint : ユーザー詳細取得
# - get_my_info_endpoint : 自分の情報取得

# 設計書：
# - 設計書/main/認証・ユーザー管理/ユーザー一覧取得_v0.2.0.md
# - 設計書/main/認証・ユーザー管理/ユーザー詳細取得_v0.2.0.md
# - 設計書/main/認証・ユーザー管理/自分の情報取得_v0.3.0.md
# ====================================================================================================


@app.get("/users")
def get_users_endpoint(
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> list[UserGetResponse]:
    """
    ユーザー一覧取得

    設計書：設計書/main/認証・ユーザー管理/ユーザー一覧取得_v0.2.0.md

    【処理概要】
    - 管理者が、登録されている全ユーザーの情報を取得する

    【パラメータ】
    - db (Session) : データベース (必須)

    【戻り値】
    - user_list (list[UserGetResponse]) : ユーザー情報取得レスポンス一覧

    【例外処理】
    - なし

    【処理フロー】
    1. ユーザー一覧取得処理の呼び出し
    2. 戻り値を返却
    """

    # 1. ユーザー一覧取得処理の呼び出し
    user_list = services.get_users(db)

    # 2. 戻り値を返却
    return user_list


@app.get("/users/me")
def get_my_info_endpoint(
    current_user: User = Depends(auth.get_current_active_user),
) -> UserGetResponse:
    """
    自分の情報取得

    設計書：設計書/main/認証・ユーザー管理/自分の情報取得_v0.3.0.md

    【処理概要】
    - ログイン中のユーザー本人が、自分の情報を取得する

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)

    【戻り値】
    - user_response (UserGetResponse) : ユーザー情報取得レスポンス

    【例外処理】
    - なし

    【処理フロー】
    1. 自分の情報取得処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 自分の情報取得処理の呼び出し
    user_response = services.get_my_info(current_user)

    # 2. 戻り値を返却
    return user_response


@app.get("/users/{user_id}")
def get_user_endpoint(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> UserGetResponse:
    """
    ユーザー詳細取得

    設計書：設計書/main/認証・ユーザー管理/ユーザー詳細取得_v0.2.0.md

    【処理概要】
    - 管理者が、指定したユーザーの詳細情報を確認する

    【パラメータ】
    - user_id (str) : ユーザーID (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - user_response (UserGetResponse) : ユーザー情報取得レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. ユーザー詳細取得処理の呼び出し
    2. 戻り値を返却
    """

    # 1. ユーザー詳細取得処理の呼び出し
    user_response = services.get_user(db, user_id)

    # 2. 戻り値を返却
    return user_response


# ====================================================================================================
# 備品検索・一覧取得・詳細取得
# - search_equipment_endpoint : 備品検索・一覧取得
# - get_equipment_endpoint : 備品詳細取得

# 設計書：
# - 設計書/main/備品管理/備品検索一覧取得_v0.2.0.md
# - 設計書/main/備品管理/備品詳細取得_v0.2.0.md
# ====================================================================================================


@app.get("/equipment")
def search_equipment_endpoint(
    category: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    loan_status: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    current_user: User = Depends(auth.require_password_changed),
    db: Session = Depends(get_db),
) -> list[EquipmentResponse]:
    """
    備品検索・一覧取得

    設計書：設計書/main/備品管理/備品検索一覧取得_v0.2.0.md

    【処理概要】
    - 利用者が、分類・キーワード・貸出状況で備品を検索し、各備品の現在の貸出状況とともに一覧で確認する

    【パラメータ】
    - category (str | None) : 分類 (任意)
    - keyword (str | None) : キーワード (任意)
    - loan_status (str | None) : 貸出状況 (任意)
    - include_inactive (bool) : 無効化済み備品を含める (必須)
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - equipment_list (list[EquipmentResponse]) : 備品レスポンス一覧

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 備品検索・一覧取得処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 備品検索・一覧取得処理の呼び出し
    equipment_list = services.search_equipment(
        current_user, db, category, keyword, loan_status, include_inactive
    )

    # 2. 戻り値を返却
    return equipment_list


@app.get("/equipment/{equipment_id}")
def get_equipment_endpoint(
    equipment_id: int,
    current_user: User = Depends(auth.require_password_changed),
    db: Session = Depends(get_db),
) -> EquipmentResponse:
    """
    備品詳細取得

    設計書：設計書/main/備品管理/備品詳細取得_v0.2.0.md

    【処理概要】
    - 利用者が、指定した備品の詳細情報（現在の貸出状況を含む）を確認する

    【パラメータ】
    - equipment_id (int) : 備品ID (必須)
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - equipment_response (EquipmentResponse) : 備品レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 備品詳細取得処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 備品詳細取得処理の呼び出し
    equipment_response = services.get_equipment(current_user, db, equipment_id)

    # 2. 戻り値を返却
    return equipment_response


# ====================================================================================================
# 備品登録・編集
# - create_equipment_endpoint : 備品登録
# - update_equipment_endpoint : 備品編集

# 設計書：
# - 設計書/main/備品管理/備品登録_v0.2.0.md
# - 設計書/main/備品管理/備品編集_v0.2.0.md
# ====================================================================================================


@app.post("/equipment")
def create_equipment_endpoint(
    equipment_create_request: EquipmentCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> EquipmentResponse:
    """
    備品登録

    設計書：設計書/main/備品管理/備品登録_v0.2.0.md

    【処理概要】
    - 管理者が、新規備品を登録する

    【パラメータ】
    - equipment_create_request (EquipmentCreateRequest) : 備品登録リクエスト (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - equipment_response (EquipmentResponse) : 備品レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 備品登録処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 備品登録処理の呼び出し
    equipment_response = services.create_equipment(
        db,
        equipment_create_request.asset_number,
        equipment_create_request.name,
        equipment_create_request.category,
        equipment_create_request.description,
        equipment_create_request.location,
    )

    # 2. 戻り値を返却
    return equipment_response


@app.put("/equipment/{equipment_id}")
def update_equipment_endpoint(
    equipment_id: int,
    equipment_update_request: EquipmentUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> EquipmentResponse:
    """
    備品編集

    設計書：設計書/main/備品管理/備品編集_v0.2.0.md

    【処理概要】
    - 管理者が、既存備品の資産番号・備品名・分類・説明・保管場所を変更する

    【パラメータ】
    - equipment_id (int) : 備品ID (必須)
    - equipment_update_request (EquipmentUpdateRequest) : 備品編集リクエスト (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - equipment_response (EquipmentResponse) : 備品レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 備品編集処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 備品編集処理の呼び出し
    equipment_response = services.update_equipment(
        db,
        equipment_id,
        equipment_update_request.asset_number,
        equipment_update_request.name,
        equipment_update_request.category,
        equipment_update_request.description,
        equipment_update_request.location,
    )

    # 2. 戻り値を返却
    return equipment_response


# ====================================================================================================
# 備品有効化状態変更
# - deactivate_equipment_endpoint : 備品無効化
# - activate_equipment_endpoint : 備品再有効化

# 設計書：
# - 設計書/main/備品管理/備品無効化_v0.2.0.md
# - 設計書/main/備品管理/備品再有効化_v0.2.0.md
# ====================================================================================================


@app.patch("/equipment/{equipment_id}/deactivate")
def deactivate_equipment_endpoint(
    equipment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> EquipmentResponse:
    """
    備品無効化

    設計書：設計書/main/備品管理/備品無効化_v0.2.0.md

    【処理概要】
    - 管理者が、既存備品を無効化する

    【パラメータ】
    - equipment_id (int) : 備品ID (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - equipment_response (EquipmentResponse) : 備品レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 備品無効化処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 備品無効化処理の呼び出し
    equipment_response = services.deactivate_equipment(db, equipment_id)

    # 2. 戻り値を返却
    return equipment_response


@app.patch("/equipment/{equipment_id}/activate")
def activate_equipment_endpoint(
    equipment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> EquipmentResponse:
    """
    備品再有効化

    設計書：設計書/main/備品管理/備品再有効化_v0.2.0.md

    【処理概要】
    - 管理者が、無効化済みの備品を再有効化する

    【パラメータ】
    - equipment_id (int) : 備品ID (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - equipment_response (EquipmentResponse) : 備品レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 備品再有効化処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 備品再有効化処理の呼び出し
    equipment_response = services.activate_equipment(db, equipment_id)

    # 2. 戻り値を返却
    return equipment_response


# ====================================================================================================
# 備品予約状況確認
# - get_equipment_reservations_endpoint : 備品予約状況確認

# 設計書：設計書/main/備品管理/備品予約状況確認_v0.2.0.md
# ====================================================================================================


@app.get("/equipment/{equipment_id}/reservations", response_model_exclude_none=True)
def get_equipment_reservations_endpoint(
    equipment_id: int,
    current_user: User = Depends(auth.require_password_changed),
    db: Session = Depends(get_db),
) -> list[ReservationResponse]:
    """
    備品予約状況確認

    設計書：設計書/main/備品管理/備品予約状況確認_v0.2.0.md

    【処理概要】
    - 利用者が、指定した備品の承認済み・貸出中の予約期間を確認し、空き期間を把握する

    【パラメータ】
    - equipment_id (int) : 備品ID (必須)
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - reservation_list (list[ReservationResponse]) : 予約情報レスポンス一覧

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 備品予約状況確認処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 備品予約状況確認処理の呼び出し
    reservation_list = services.get_equipment_reservations(current_user, db, equipment_id)

    # 2. 戻り値を返却
    return reservation_list


# ====================================================================================================
# 備品CSV一括登録
# - bulk_import_equipment_endpoint : 備品CSV一括登録

# 設計書：設計書/main/備品管理/備品CSV一括登録_v0.2.0.md
# ====================================================================================================


@app.post("/equipment/bulk-import")
async def bulk_import_equipment_endpoint(
    file: UploadFile = File(),
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> EquipmentBulkImportResponse:
    """
    備品CSV一括登録

    設計書：設計書/main/備品管理/備品CSV一括登録_v0.2.0.md

    【処理概要】
    - 管理者が、CSVファイルから複数の備品を一括登録する

    【パラメータ】
    - file (UploadFile) : CSVファイル (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - bulk_import_response (EquipmentBulkImportResponse) : 備品CSV一括登録レスポンス

    【例外処理】
    - HTTPException(400) : 備品CSV一括登録処理が検証エラーを検出した場合（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. ファイル内容読み込み
    2. 備品CSV一括登録処理の呼び出し
    3. 戻り値を返却
    """

    # 1. ファイル内容読み込み
    file_content = await file.read()

    # 2. 備品CSV一括登録処理の呼び出し
    bulk_import_response = services.bulk_import_equipment(db, file_content)

    # 3. 戻り値を返却
    return bulk_import_response


# ====================================================================================================
# 貸出申請登録・取消
# - create_loan_request_endpoint : 貸出申請登録
# - cancel_loan_request_endpoint : 貸出申請取消

# 設計書：
# - 設計書/main/貸出申請・承認/貸出申請登録_v0.2.0.md
# - 設計書/main/貸出申請・承認/貸出申請取消_v0.2.0.md
# ====================================================================================================


@app.post("/loan-requests")
def create_loan_request_endpoint(
    loan_request_create_request: LoanRequestCreateRequest,
    current_user: User = Depends(auth.require_password_changed),
    db: Session = Depends(get_db),
) -> LoanRequestResponse:
    """
    貸出申請登録

    設計書：設計書/main/貸出申請・承認/貸出申請登録_v0.2.0.md

    【処理概要】
    - 利用者が、備品の貸出を申請する

    【パラメータ】
    - loan_request_create_request (LoanRequestCreateRequest) : 貸出申請登録リクエスト (必須)
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 貸出申請登録処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 貸出申請登録処理の呼び出し
    loan_request_response = services.create_loan_request(
        current_user,
        db,
        loan_request_create_request.equipment_id,
        loan_request_create_request.start_date,
        loan_request_create_request.due_date,
        loan_request_create_request.purpose,
    )

    # 2. 戻り値を返却
    return loan_request_response


@app.patch("/loan-requests/{loan_request_id}/cancel")
def cancel_loan_request_endpoint(
    loan_request_id: int,
    loan_request_cancel_request: LoanRequestCancelRequest,
    current_user: User = Depends(auth.require_password_changed),
    db: Session = Depends(get_db),
) -> LoanRequestResponse:
    """
    貸出申請取消

    設計書：設計書/main/貸出申請・承認/貸出申請取消_v0.2.0.md

    【処理概要】
    - 利用者が、自分が申請した貸出申請を取消す

    【パラメータ】
    - loan_request_id (int) : 貸出申請ID (必須)
    - loan_request_cancel_request (LoanRequestCancelRequest) : 貸出申請取消リクエスト (必須)
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 貸出申請取消処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 貸出申請取消処理の呼び出し
    loan_request_response = services.cancel_loan_request_by_applicant(
        current_user, db, loan_request_id, loan_request_cancel_request.reason
    )

    # 2. 戻り値を返却
    return loan_request_response


# ====================================================================================================
# 貸出申請一覧取得・詳細取得
# - get_loan_requests_endpoint : 貸出申請一覧取得
# - get_loan_request_endpoint : 貸出申請詳細取得

# 設計書：
# - 設計書/main/貸出申請・承認/貸出申請一覧取得_v0.3.0.md
# - 設計書/main/貸出申請・承認/貸出申請詳細取得_v0.2.0.md
# ====================================================================================================


@app.get("/loan-requests")
def get_loan_requests_endpoint(
    scope: Literal["mine", "all", "overdue"] = Query(default="mine"),
    status: str | None = Query(default=None),
    current_user: User = Depends(auth.require_password_changed),
    db: Session = Depends(get_db),
) -> list[LoanRequestResponse]:
    """
    貸出申請一覧取得

    設計書：設計書/main/貸出申請・承認/貸出申請一覧取得_v0.3.0.md

    【処理概要】
    - ログインユーザーが、貸出申請の一覧を確認する
    - 管理者は、全申請一覧・期限超過一覧も確認できる

    【パラメータ】
    - scope (Literal["mine", "all", "overdue"]) : 取得範囲 (必須)
    - status (str | None) : 状態 (任意)
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - loan_request_list (list[LoanRequestResponse]) : 貸出申請レスポンス一覧

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 貸出申請一覧取得処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 貸出申請一覧取得処理の呼び出し
    loan_request_list = services.get_loan_requests(current_user, db, scope, status)

    # 2. 戻り値を返却
    return loan_request_list


@app.get("/loan-requests/{loan_request_id}")
def get_loan_request_endpoint(
    loan_request_id: int,
    current_user: User = Depends(auth.require_password_changed),
    db: Session = Depends(get_db),
) -> LoanRequestResponse:
    """
    貸出申請詳細取得

    設計書：設計書/main/貸出申請・承認/貸出申請詳細取得_v0.2.0.md

    【処理概要】
    - ログインユーザーが、貸出申請の詳細を確認する
    - 管理者は、任意の申請の詳細を確認できる

    【パラメータ】
    - loan_request_id (int) : 貸出申請ID (必須)
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 貸出申請詳細取得処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 貸出申請詳細取得処理の呼び出し
    loan_request_response = services.get_loan_request(current_user, db, loan_request_id)

    # 2. 戻り値を返却
    return loan_request_response


# ====================================================================================================
# 貸出申請承認・却下・管理者取消
# - approve_loan_request_endpoint : 貸出申請承認
# - reject_loan_request_endpoint : 貸出申請却下
# - admin_cancel_loan_request_endpoint : 貸出申請管理者取消

# 設計書：
# - 設計書/main/貸出申請・承認/貸出申請承認_v0.2.0.md
# - 設計書/main/貸出申請・承認/貸出申請却下_v0.2.0.md
# - 設計書/main/貸出申請・承認/貸出申請管理者取消_v0.2.0.md
# ====================================================================================================


@app.patch("/loan-requests/{loan_request_id}/approve")
def approve_loan_request_endpoint(
    loan_request_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> LoanRequestResponse:
    """
    貸出申請承認

    設計書：設計書/main/貸出申請・承認/貸出申請承認_v0.2.0.md

    【処理概要】
    - 管理者が、申請中の貸出申請を承認する

    【パラメータ】
    - loan_request_id (int) : 貸出申請ID (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 貸出申請承認処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 貸出申請承認処理の呼び出し
    loan_request_response = services.approve_loan_request(current_admin, db, loan_request_id)

    # 2. 戻り値を返却
    return loan_request_response


@app.patch("/loan-requests/{loan_request_id}/reject")
def reject_loan_request_endpoint(
    loan_request_id: int,
    loan_request_reject_request: LoanRequestRejectRequest,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> LoanRequestResponse:
    """
    貸出申請却下

    設計書：設計書/main/貸出申請・承認/貸出申請却下_v0.2.0.md

    【処理概要】
    - 管理者が、申請中の貸出申請を却下する

    【パラメータ】
    - loan_request_id (int) : 貸出申請ID (必須)
    - loan_request_reject_request (LoanRequestRejectRequest) : 貸出申請却下リクエスト (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 貸出申請却下処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 貸出申請却下処理の呼び出し
    loan_request_response = services.reject_loan_request(
        current_admin, db, loan_request_id, loan_request_reject_request.reason
    )

    # 2. 戻り値を返却
    return loan_request_response


@app.patch("/loan-requests/{loan_request_id}/admin-cancel")
def admin_cancel_loan_request_endpoint(
    loan_request_id: int,
    loan_request_admin_cancel_request: LoanRequestAdminCancelRequest,
    db: Session = Depends(get_db),
    _: User = Depends(auth.require_password_changed),
    current_admin: User = Depends(auth.require_admin),
) -> LoanRequestResponse:
    """
    貸出申請管理者取消

    設計書：設計書/main/貸出申請・承認/貸出申請管理者取消_v0.2.0.md

    【処理概要】
    - 管理者が、承認済みの貸出申請を取消す

    【パラメータ】
    - loan_request_id (int) : 貸出申請ID (必須)
    - loan_request_admin_cancel_request (LoanRequestAdminCancelRequest) : 貸出申請管理者取消リクエスト (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - loan_request_response (LoanRequestResponse) : 貸出申請レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 貸出申請管理者取消処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 貸出申請管理者取消処理の呼び出し
    loan_request_response = services.admin_cancel_loan_request(
        current_admin, db, loan_request_id, loan_request_admin_cancel_request.reason
    )

    # 2. 戻り値を返却
    return loan_request_response


# ====================================================================================================
# 通知一覧取得・既読化
# - get_notifications_endpoint : 通知一覧取得
# - mark_notification_as_read_endpoint : 通知既読化

# 設計書：
# - 設計書/main/貸出申請・承認/通知一覧取得_v0.2.0.md
# - 設計書/main/貸出申請・承認/通知既読化_v0.2.0.md
# ====================================================================================================


@app.get("/notifications")
def get_notifications_endpoint(
    current_user: User = Depends(auth.require_password_changed),
    db: Session = Depends(get_db),
) -> list[NotificationResponse]:
    """
    通知一覧取得

    設計書：設計書/main/貸出申請・承認/通知一覧取得_v0.2.0.md

    【処理概要】
    - ログインユーザーが、自分宛の通知一覧を確認する

    【パラメータ】
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - notification_list (list[NotificationResponse]) : 通知レスポンス一覧

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 通知一覧取得処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 通知一覧取得処理の呼び出し
    notification_list = services.get_notifications(current_user, db)

    # 2. 戻り値を返却
    return notification_list


@app.patch("/notifications/{notification_id}/read")
def mark_notification_as_read_endpoint(
    notification_id: int,
    current_user: User = Depends(auth.require_password_changed),
    db: Session = Depends(get_db),
) -> NotificationResponse:
    """
    通知既読化

    設計書：設計書/main/貸出申請・承認/通知既読化_v0.2.0.md

    【処理概要】
    - ログインユーザーが、自分宛の通知を既読にする

    【パラメータ】
    - notification_id (int) : 通知ID (必須)
    - current_user (User) : ログインユーザー検証結果 (必須)
    - db (Session) : データベース (必須)

    【戻り値】
    - notification_response (NotificationResponse) : 通知レスポンス

    【例外処理】
    - なし（オーケストレーション層の例外処理に従う）

    【処理フロー】
    1. 通知既読化処理の呼び出し
    2. 戻り値を返却
    """

    # 1. 通知既読化処理の呼び出し
    notification_response = services.mark_notification_as_read_by_recipient(current_user, db, notification_id)

    # 2. 戻り値を返却
    return notification_response
