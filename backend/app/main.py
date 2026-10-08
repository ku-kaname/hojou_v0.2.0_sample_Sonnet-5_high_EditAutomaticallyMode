"""
アプリ起動構成

【概要】
FastAPIアプリケーションの生成、CORS設定、ヘルスチェックエンドポイントを提供する
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import engine
from app.scheduler import shutdown_scheduler, start_scheduler

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
    - アプリ起動時に日次バッチのスケジューラを起動し、終了時に停止する

    【パラメータ】
    - app (FastAPI) : FastAPIアプリケーション (必須)

    【戻り値】
    - なし

    【例外処理】
    - なし

    【処理フロー】
    1. スケジューラの起動
    2. アプリ終了までの待機
    3. スケジューラの停止
    """

    # 1. スケジューラの起動
    start_scheduler()

    # 2. アプリ終了までの待機
    yield

    # 3. スケジューラの停止
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
