/**
 * 認証必須ルートガード
 *
 * 【概要】
 * ログイン済みでない場合はログイン画面へリダイレクトする、ルーティング用の認証ガード
 */

import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { LoadingIndicator } from "./LoadingIndicator";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingIndicator />;
  }

  if (user === null) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
