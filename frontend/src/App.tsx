/**
 * ルーティング定義
 *
 * 【概要】
 * 認証コンテキストの提供、およびロール別ガードを用いたルーティングの骨格を提供する
 * 画面単位のルート（S01〜S11）は、各対応する機能群の実装バックログで本ファイルへ追記する
 */

import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AdminRoute } from "./components/AdminRoute";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthProvider } from "./contexts/AuthContext";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { EquipmentDetailPage } from "./pages/EquipmentDetailPage";
import { EquipmentListPage } from "./pages/EquipmentListPage";
import { EquipmentManagementPage } from "./pages/EquipmentManagementPage";
import { HomePage } from "./pages/HomePage";
import { LoanRequestManagePage } from "./pages/LoanRequestManagePage";
import { LoanRequestMinePage } from "./pages/LoanRequestMinePage";
import { LoginPage } from "./pages/LoginPage";
import { UserManagementPage } from "./pages/UserManagementPage";

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route
            path="/login"
            element={
              <Layout>
                <LoginPage />
              </Layout>
            }
          />
          <Route
            path="/change-password"
            element={
              <ProtectedRoute>
                <Layout>
                  <ChangePasswordPage />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout>
                  <HomePage />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/users"
            element={
              <AdminRoute>
                <Layout>
                  <UserManagementPage />
                </Layout>
              </AdminRoute>
            }
          />
          <Route
            path="/equipment"
            element={
              <ProtectedRoute>
                <Layout>
                  <EquipmentListPage />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/equipment/:equipmentId"
            element={
              <ProtectedRoute>
                <Layout>
                  <EquipmentDetailPage />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/equipment-management"
            element={
              <AdminRoute>
                <Layout>
                  <EquipmentManagementPage />
                </Layout>
              </AdminRoute>
            }
          />
          <Route
            path="/loan-requests/mine"
            element={
              <ProtectedRoute>
                <Layout>
                  <LoanRequestMinePage />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/loan-requests/manage"
            element={
              <AdminRoute>
                <Layout>
                  <LoanRequestManagePage />
                </Layout>
              </AdminRoute>
            }
          />
          {/* 他画面のルートは、各対応する機能群の実装バックログで本ファイルへ追記する */}
          <Route path="*" element={<p>準備中です。</p>} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
