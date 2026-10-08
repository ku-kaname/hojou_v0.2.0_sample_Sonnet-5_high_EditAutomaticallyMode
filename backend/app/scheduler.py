"""
日次バッチ共通処理

【概要】
返却期限通知・ノーショー自動取消等の日次バッチジョブを定期実行するスケジューラを提供する
"""

import logging
from contextlib import contextmanager

from apscheduler.schedulers.background import BackgroundScheduler

from app import services
from app.database import get_db

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Asia/Tokyo")

# ====================================================================================================
# スケジューラ起動・停止
# - start_scheduler : スケジューラ起動
# - shutdown_scheduler : スケジューラ停止

# 設計書：設計書/アーキテクチャ方針_v0.2.0.md
# ====================================================================================================


def start_scheduler() -> None:
    """
    スケジューラ起動

    設計書：設計書/アーキテクチャ方針_v0.2.0.md

    【処理概要】
    - 日次バッチジョブのスケジューラを起動する
    - 個々のジョブ登録は、対応する機能群の実装バックログで本処理に追記する

    【パラメータ】
    - なし

    【戻り値】
    - なし

    【例外処理】
    - なし

    【処理フロー】
    1. ノーショー自動取消バッチジョブの登録
    2. 返却期限通知バッチジョブの登録
    3. スケジューラの起動
    """

    # 1. ノーショー自動取消バッチジョブの登録
    scheduler.add_job(run_no_show_cancellation_batch, "cron", hour=6, minute=0, id="no_show_cancellation_batch")

    # 2. 返却期限通知バッチジョブの登録
    scheduler.add_job(run_due_date_notification_batch, "cron", hour=6, minute=0, id="due_date_notification_batch")

    # 3. スケジューラの起動
    scheduler.start()


def shutdown_scheduler() -> None:
    """
    スケジューラ停止

    設計書：設計書/アーキテクチャ方針_v0.2.0.md

    【処理概要】
    - 日次バッチジョブのスケジューラを停止する

    【パラメータ】
    - なし

    【戻り値】
    - なし

    【例外処理】
    - なし

    【処理フロー】
    1. スケジューラの停止
    """

    # 1. スケジューラの停止
    scheduler.shutdown()


# ====================================================================================================
# ノーショー自動取消バッチ
# - run_no_show_cancellation_batch : ノーショー自動取消バッチ実行

# 設計書：設計書/scheduler/貸出申請・承認/ノーショー自動取消バッチ_v0.2.0.md
# ====================================================================================================


def run_no_show_cancellation_batch() -> None:
    """
    ノーショー自動取消バッチ実行

    設計書：設計書/scheduler/貸出申請・承認/ノーショー自動取消バッチ_v0.2.0.md

    【処理概要】
    - 日次バッチにより、ノーショー状態となった貸出申請を自動的に取消す
    - 申請中のまま開始日を過ぎた申請、承認済みのまま返却予定日を過ぎた申請を、それぞれ取消す

    【パラメータ】
    - なし

    【戻り値】
    - なし

    【例外処理】
    - なし

    【処理フロー】
    1. データベースセッション取得
    2. 開始日超過ノーショー自動取消処理の呼び出し
    3. 返却予定日超過ノーショー自動取消処理の呼び出し
    4. 処理結果のログ出力
    """

    # 1. データベースセッション取得
    get_db_context = contextmanager(get_db)
    with get_db_context() as db:
        # 2. 開始日超過ノーショー自動取消処理の呼び出し
        start_date_cancelled_count = services.cancel_no_show_loan_requests_by_start_date(db)

        # 3. 返却予定日超過ノーショー自動取消処理の呼び出し
        due_date_cancelled_count = services.cancel_no_show_loan_requests_by_due_date(db)

    # 4. 処理結果のログ出力
    logger.info(
        "ノーショー自動取消バッチ実行完了：開始日超過取消件数=%d、返却予定日超過取消件数=%d",
        start_date_cancelled_count,
        due_date_cancelled_count,
    )


# ====================================================================================================
# 返却期限通知バッチ
# - run_due_date_notification_batch : 返却期限通知バッチ実行

# 設計書：設計書/scheduler/貸出・返却・履歴/返却期限通知バッチ_v0.2.0.md
# ====================================================================================================


def run_due_date_notification_batch() -> None:
    """
    返却期限通知バッチ実行

    設計書：設計書/scheduler/貸出・返却・履歴/返却期限通知バッチ_v0.2.0.md

    【処理概要】
    - 日次バッチにより、返却期限が近い・過ぎている貸出中の貸出申請の申請者に返却期限通知を行う
    - 返却予定日が翌日の申請、返却予定日を過ぎている申請の双方に対し、それぞれ通知する

    【パラメータ】
    - なし

    【戻り値】
    - なし

    【例外処理】
    - なし

    【処理フロー】
    1. データベースセッション取得
    2. 返却期限通知（前日）処理の呼び出し
    3. 返却期限通知（期限超過中）処理の呼び出し
    4. 処理結果のログ出力
    """

    # 1. データベースセッション取得
    get_db_context = contextmanager(get_db)
    with get_db_context() as db:
        # 2. 返却期限通知（前日）処理の呼び出し
        tomorrow_notified_count = services.notify_due_date_tomorrow(db)

        # 3. 返却期限通知（期限超過中）処理の呼び出し
        overdue_notified_count = services.notify_due_date_overdue(db)

    # 4. 処理結果のログ出力
    logger.info(
        "返却期限通知バッチ実行完了：前日通知件数=%d、期限超過中通知件数=%d",
        tomorrow_notified_count,
        overdue_notified_count,
    )
