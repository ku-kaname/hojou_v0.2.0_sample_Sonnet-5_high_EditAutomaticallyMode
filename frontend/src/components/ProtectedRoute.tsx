/**
 * 認証必須ルートガード
 *
 * 【概要】
 * ログイン済みでない場合はログイン画面へ、初回パスワード変更が未完了の場合はパスワード変更画面へリダイレクトする、ルーティング用の認証ガード
 */

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { LoadingIndicator } from "./LoadingIndicator";

const CHANGE_PASSWORD_PATH = "/change-password";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingIndicator />;
  }

  if (user === null) {
    return <Navigate to="/login" replace />;
  }

  if (user.password_change_required_flag && location.pathname !== CHANGE_PASSWORD_PATH) {
    return <Navigate to={CHANGE_PASSWORD_PATH} replace />;
  }

  return <>{children}</>;
}
