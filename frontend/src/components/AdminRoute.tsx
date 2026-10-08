/**
 * 管理者限定ルートガード
 *
 * 【概要】
 * ログイン済みでない場合はログイン画面へ、初回パスワード変更が未完了の場合はパスワード変更画面へ、管理者ロールでない場合はホーム画面へリダイレクトする、ルーティング用の認証ガード
 */

import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { LoadingIndicator } from "./LoadingIndicator";

export function AdminRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingIndicator />;
  }

  if (user === null) {
    return <Navigate to="/login" replace />;
  }

  if (user.password_change_required_flag) {
    return <Navigate to="/change-password" replace />;
  }

  if (user.role !== "管理者") {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
