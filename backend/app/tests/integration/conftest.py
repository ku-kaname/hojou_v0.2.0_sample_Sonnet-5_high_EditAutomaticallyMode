"""
結合テスト共通設定

【概要】
結合テストの実行に必要な、使い捨てPostgreSQLコンテナの起動・DBスキーマ構築（Alembicマイグレーション）・
FastAPI TestClientの生成・テストケース間のデータ分離を行う。
本ファイルは、以降の全ての結合テストバックログ（認証・ユーザー管理／備品管理／貸出申請・承認／
貸出・返却・履歴／機能横断）から共通で使用する。
"""

import os
import socket
import subprocess
import time
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

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
    """
    PostgreSQLの起動完了を待機する

    コンテナ内のpg_isreadyの成功（DBサーバー自体の起動完了）に加え、
    ホスト側ポート（127.0.0.1:_host_port）への実際のTCP接続成功も確認する。
    pg_isreadyはコンテナ内部から確認するため、コンテナ再起動（docker stop/start）後に
    ホスト側のポートフォワーディングの復旧が内部のDB起動より遅れるケースを検知できない
    （ホスト側の接続確認なしでは、以降のテストがDB接続タイムアウトで失敗し続ける）。
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", _CONTAINER_NAME, "pg_isready", "-U", _POSTGRES_USER, "-d", _POSTGRES_DB],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and _is_host_port_reachable():
            return
        time.sleep(1)
    raise TimeoutError("結合テスト用PostgreSQLコンテナの起動待機がタイムアウトしました")


def _is_host_port_reachable() -> bool:
    """ホスト側ポート（127.0.0.1:_host_port）へのTCP接続が確立できるかを確認する"""
    try:
        with socket.create_connection(("127.0.0.1", _host_port), timeout=1):
            return True
    except OSError:
        return False


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
from app import main, services  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


def _find_unused_port() -> int:
    """現在どのプロセスも待ち受けていないホスト側ポート番号を1つ取得する"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as temp_socket:
        temp_socket.bind(("127.0.0.1", 0))
        return temp_socket.getsockname()[1]


@pytest.fixture
def db_connection_unreachable(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """
    DB接続不可状態を再現する（テスト関数内でのみ使用）

    結合テスト全体で共有している使い捨てPostgreSQLコンテナ自体は停止・再起動しない
    （本環境（Windows + Docker Desktop）では、コンテナ再起動後にホスト側ポートフォワーディングが
    復旧せず、以降の全テストに悪影響を及ぼす事象を確認したため）。
    代わりに、ヘルスチェック処理が参照するengine（app.main.engine）を、何も待ち受けていない
    未使用ポートを指す一時engineに差し替えることで、DB接続失敗を再現する。
    一時engineには明示的なconnect_timeoutを設定する（本環境では、未使用ポートへの接続は
    タイムアウト未設定の場合に長時間ブロックされることを確認済みのため）。
    """
    unreachable_port = _find_unused_port()
    temporary_engine = create_engine(
        f"postgresql+psycopg://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}@127.0.0.1:{unreachable_port}/{_POSTGRES_DB}",
        connect_args={"connect_timeout": 3},
    )
    monkeypatch.setattr(main, "engine", temporary_engine)
    try:
        yield
    finally:
        temporary_engine.dispose()


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
