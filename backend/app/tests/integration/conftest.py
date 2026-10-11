"""
結合テスト共通設定

【概要】
結合テストの実行に必要な、使い捨てPostgreSQLコンテナの起動・DBスキーマ構築（Alembicマイグレーション）・
FastAPI TestClientの生成・テストケース間のデータ分離を行う。
本ファイルは、以降の全ての結合テストバックログ（認証・ユーザー管理／備品管理／貸出申請・承認／
貸出・返却・履歴／機能横断）から共通で使用する。
"""

import os
import subprocess
import time
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# ====================================================================================================
# 結合テスト専用の使い捨てPostgreSQLコンテナ起動・環境変数設定
#
# 本プロジェクトの docker-compose.yml や .env（本番／開発用の秘密情報）は一切参照せず、
# 結合テストの実行のたびに自己生成したテスト専用の認証情報・使い捨てのPostgreSQLコンテナを用意する。
#
# app.database / app.main は、モジュールのインポート時に環境変数（DATABASE_URL等）を読み込むため、
# これらのモジュールを初めてインポートするより前に、本ブロックで環境変数を確定させる
# （conftest.pyのモジュールレベルで実行することで、テストファイルの収集（collection）時点の
# インポートより先に実行されることを保証する）。
# ====================================================================================================

_CONTAINER_NAME = f"hojou-it-common-pg-{uuid.uuid4().hex[:12]}"
_POSTGRES_USER = "integration_test_user"
_POSTGRES_PASSWORD = "integration-test-password"
_POSTGRES_DB = "integration_test_db"

_BACKEND_DIR = os.path.dirname(  # backend/app/tests/integration/conftest.py から backend/ まで4階層上
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _start_postgres_container() -> int:
    """使い捨てのPostgreSQLコンテナを起動し、Dockerが割り当てたホスト側ポート番号を返す"""
    subprocess.run(
        [
            "docker", "run", "-d",
            "--name", _CONTAINER_NAME,
            "-e", f"POSTGRES_USER={_POSTGRES_USER}",
            "-e", f"POSTGRES_PASSWORD={_POSTGRES_PASSWORD}",
            "-e", f"POSTGRES_DB={_POSTGRES_DB}",
            "-p", "127.0.0.1::5432",
            "postgres:16",
        ],
        check=True, capture_output=True, text=True,
    )
    port_result = subprocess.run(
        ["docker", "port", _CONTAINER_NAME, "5432/tcp"],
        check=True, capture_output=True, text=True,
    )
    # 出力例："0.0.0.0:54321"（1行、または複数行の場合は最後の行を使用）
    last_line = port_result.stdout.strip().splitlines()[-1]
    return int(last_line.rsplit(":", 1)[-1])


def _wait_for_postgres_ready(timeout_seconds: int = 60) -> None:
    """コンテナ内のpg_isreadyが成功するまで待機する（起動完了待ち）"""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", _CONTAINER_NAME, "pg_isready", "-U", _POSTGRES_USER, "-d", _POSTGRES_DB],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise TimeoutError("結合テスト用PostgreSQLコンテナの起動待機がタイムアウトしました")


def _stop_postgres_container() -> None:
    """使い捨てPostgreSQLコンテナを停止・削除する"""
    subprocess.run(["docker", "rm", "-f", _CONTAINER_NAME], capture_output=True, text=True)


_host_port = _start_postgres_container()
_wait_for_postgres_ready()

os.environ["DATABASE_URL"] = (
    f"postgresql+psycopg://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}@127.0.0.1:{_host_port}/{_POSTGRES_DB}"
)
os.environ["JWT_SECRET_KEY"] = "integration-test-secret-key-32-bytes-or-more"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost"
os.environ["INITIAL_ADMIN_USER_ID"] = "admin"
os.environ["INITIAL_ADMIN_NAME"] = "管理者"
os.environ["INITIAL_ADMIN_PASSWORD"] = "integration-test-admin-password"

# ====================================================================================================
# DBスキーマ構築（Alembicマイグレーション実行）
#
# backend/app/database.py は Base.metadata.create_all() を一切使用せず、スキーマ構築は
# Alembicマイグレーションのみで行う方針のため、結合テスト用DBにも同じ手段でスキーマを構築する。
# ====================================================================================================

subprocess.run(
    ["alembic", "upgrade", "head"],
    cwd=_BACKEND_DIR,
    env=os.environ.copy(),
    check=True, capture_output=True, text=True,
)

# 環境変数が確定した後に、初めてアプリ本体をインポートする
from app import services  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def postgres_container_stopped() -> Generator[None, None, None]:
    """
    PostgreSQLコンテナを一時的に停止し、DB接続不可状態を再現する（テスト関数内でのみ使用）

    テスト終了後は、以降のテストに影響を与えないよう必ずコンテナを再起動し、
    起動完了（pg_isready成功）まで待機する。
    """
    subprocess.run(["docker", "stop", _CONTAINER_NAME], check=True, capture_output=True, text=True)
    try:
        yield
    finally:
        subprocess.run(["docker", "start", _CONTAINER_NAME], check=True, capture_output=True, text=True)
        _wait_for_postgres_ready()


@pytest.fixture(scope="session", autouse=True)
def _teardown_postgres_container() -> Generator[None, None, None]:
    """テストセッション終了後、使い捨てPostgreSQLコンテナを削除する"""
    yield
    _stop_postgres_container()


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient

    アプリのlifespan（スケジューラ起動・初期管理者アカウント作成）を実際に経由して起動・終了する。
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_database(client: TestClient) -> Generator[None, None, None]:
    """
    各テストケースの実行前に、全テーブルを初期化（TRUNCATE）し、初期管理者ユーザーを再作成する
    （テストケース間のデータ分離。テーブル名はテーブル定義（models.py）の大文字物理名のため、
    Postgres上での大文字小文字を区別させるためダブルクォートで囲む）
    """
    db = SessionLocal()
    try:
        db.execute(
            text('TRUNCATE TABLE "NOTIFICATION", "LOAN_REQUEST", "EQUIPMENT", "USER" RESTART IDENTITY CASCADE')
        )
        db.commit()
        services.create_initial_admin(db)
        db.commit()
    finally:
        db.close()
    yield
