"""
DB接続管理

【概要】
データベースエンジン・セッションファクトリの生成、およびセッションの依存性注入を行う
"""

import os
from collections.abc import Generator

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    テーブルモデル共通基底クラス

    【概要】
    全テーブルモデル（`app/models.py`）の基底クラス
    """


def get_db() -> Generator[Session, None, None]:
    """
    DBセッション取得

    【処理概要】
    - リクエスト単位のDBセッションを生成し、処理完了後に解放する依存性注入関数

    【パラメータ】
    - なし

    【戻り値】
    - db (Session) : DBセッション

    【例外処理】
    - なし（呼び出し元の処理でHTTPExceptionが発生した場合はコミットの上、例外を再送出する。
      その他の例外が発生した場合はロールバックの上、例外を再送出する）

    【処理フロー】
    1. DBセッションを生成
    2. 呼び出し元へセッションを渡す
    3. 呼び出し元の処理が正常終了した場合、コミットする
    4. 呼び出し元の処理でHTTPExceptionが発生した場合、業務上正常な応答のためコミットした上で例外を再送出する
    5. 呼び出し元の処理でその他の例外が発生した場合、ロールバックした上で例外を再送出する
    6. セッションを解放する
    """

    # 1. DBセッションを生成
    db = SessionLocal()

    try:
        # 2. 呼び出し元へセッションを渡す
        yield db
        # 3. 呼び出し元の処理が正常終了した場合、コミットする
        db.commit()
    except HTTPException:
        # 4. 呼び出し元の処理でHTTPExceptionが発生した場合、業務上正常な応答のためコミットした上で例外を再送出する
        db.commit()
        raise
    except Exception:
        # 5. 呼び出し元の処理でその他の例外が発生した場合、ロールバックした上で例外を再送出する
        db.rollback()
        raise
    finally:
        # 6. セッションを解放する
        db.close()
