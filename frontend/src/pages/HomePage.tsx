/**
 * ホーム（ダッシュボード）画面
 *
 * 【概要】
 * ログインユーザー宛の通知一覧の確認・既読化（F08）を行う画面
 *
 * 【備考】
 * 自分の貸出中・期限超過件数、（管理者）承認待ち・期限超過件数の表示（F13）は、
 * 別バックログ「実装（貸出・返却・履歴）」で本画面へ追加する予定であり、本画面では実装しない。
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet, apiPatch, ApiError } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingIndicator } from "../components/LoadingIndicator";
import { useAuth } from "../contexts/AuthContext";
import type { NotificationResponse, NotificationType } from "../types/common";

function toErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

const NOTIFICATION_TYPE_LABEL: Record<NotificationType, string> = {
  承認: "貸出申請が承認されました。",
  却下: "貸出申請が却下されました。",
  取消: "貸出申請が取消されました。",
  新規申請: "新しい貸出申請があります。",
  返却期限: "返却予定日が近づいています（または過ぎています）。",
};

export function HomePage() {
  const { user } = useAuth();
  const [notificationList, setNotificationList] = useState<NotificationResponse[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadNotificationList = useCallback(async (): Promise<void> => {
    setLoadError(null);
    try {
      const list = await apiGet<NotificationResponse[]>("/notifications");
      setNotificationList(list);
    } catch (error) {
      setLoadError(toErrorMessage(error, "通知一覧の取得に失敗しました。"));
    }
  }, []);

  useEffect(() => {
    void loadNotificationList();
  }, [loadNotificationList]);

  async function handleMarkAsRead(notificationId: number): Promise<void> {
    setActionError(null);
    try {
      await apiPatch(`/notifications/${notificationId}/read`);
      await loadNotificationList();
    } catch (error) {
      setActionError(toErrorMessage(error, "通知の既読化に失敗しました。"));
    }
  }

  return (
    <div>
      <h1>ホーム</h1>
      <p>{user?.name}さん、お疲れ様です。</p>
      <p>
        <Link to="/loan-requests/mine">自分の申請一覧</Link>
        {user?.role === "管理者" && <Link to="/loan-requests/manage">申請管理</Link>}
      </p>

      <h2>通知</h2>
      {actionError !== null && <ErrorMessage message={actionError} />}
      {loadError !== null ? (
        <div>
          <ErrorMessage message={loadError} />
          <button type="button" onClick={() => void loadNotificationList()}>
            再試行
          </button>
        </div>
      ) : notificationList === null ? (
        <LoadingIndicator />
      ) : notificationList.length === 0 ? (
        <p>通知はありません。</p>
      ) : (
        <ul>
          {notificationList.map((notification) => (
            <li key={notification.notification_id}>
              {!notification.read_flag && <strong>【未読】</strong>}
              {NOTIFICATION_TYPE_LABEL[notification.notification_type]}（{notification.created_at}）
              {!notification.read_flag && (
                <button
                  type="button"
                  onClick={() => void handleMarkAsRead(notification.notification_id)}
                >
                  既読にする
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
