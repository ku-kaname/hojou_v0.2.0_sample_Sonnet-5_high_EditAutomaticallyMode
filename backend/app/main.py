"""
アプリ起動構成

【概要】
FastAPIアプリケーションの生成、CORS設定、ヘルスチェックエンドポイントを提供する
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, status
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
    PasswordChangeRequest,
    PasswordResetRequest,
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
# - 設計書/main/認証・ユーザー管理/自分の情報取得_v0.2.0.md
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
    current_user: User = Depends(auth.require_password_changed),
) -> UserGetResponse:
    """
    自分の情報取得

    設計書：設計書/main/認証・ユーザー管理/自分の情報取得_v0.2.0.md

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
