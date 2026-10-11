import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { ProtectedRoute } from "../../components/ProtectedRoute";
import { useAuth } from "../../contexts/AuthContext";
import type { UserGetResponse } from "../../types/common";

// ==================================================
// 認証必須ルートガード
// テスト対象ファイル：ProtectedRoute.tsx
// テスト対象クラス：-
// テスト対象メソッド：ProtectedRoute
// テスト仕様書：test_specification/unit_test_specification/フロントエンド共通基盤/認証必須ルートガード_単体テスト仕様書.md
// ==================================================

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

const baseUser: UserGetResponse = {
  user_id: "u001",
  name: "テスト太郎",
  department: "総務部",
  role: "一般",
  active_flag: true,
  password_change_required_flag: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderProtectedRoute(initialPath: string) {
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/protected"
          element={
            <ProtectedRoute>
              <div>保護対象コンテンツ</div>
            </ProtectedRoute>
          }
        />
        <Route
          path="/change-password"
          element={
            <ProtectedRoute>
              <div>パスワード変更フォーム</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<div>ログイン画面</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

// ========== 単体テストNo.1 ==========
// ログイン状態確認中の場合、ローディング表示となり子要素が表示されないこと
it("test_ProtectedRoute_001_loading_shows_loading_indicator", () => {
  vi.mocked(useAuth).mockReturnValue({
    user: null,
    isLoading: true,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  });

  renderProtectedRoute("/protected");

  expect(screen.queryByText("保護対象コンテンツ")).not.toBeInTheDocument();
  expect(screen.queryByText("ログイン画面")).not.toBeInTheDocument();
});

// ========== 単体テストNo.2 ==========
// 未ログインの場合、ログイン画面へリダイレクトされること
it("test_ProtectedRoute_002_not_logged_in_redirects_to_login", () => {
  vi.mocked(useAuth).mockReturnValue({
    user: null,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  });

  renderProtectedRoute("/protected");

  expect(screen.getByText("ログイン画面")).toBeInTheDocument();
});

// ========== 単体テストNo.3 ==========
// 初回パスワード変更が未完了かつ現在パスがパスワード変更画面でない場合、パスワード変更画面へリダイレクトされること
it("test_ProtectedRoute_003_password_change_required_redirects_when_not_on_change_password_page", () => {
  vi.mocked(useAuth).mockReturnValue({
    user: { ...baseUser, password_change_required_flag: true },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  });

  renderProtectedRoute("/protected");

  expect(screen.getByText("パスワード変更フォーム")).toBeInTheDocument();
});

// ========== 単体テストNo.4 ==========
// 初回パスワード変更が未完了でも現在パスがパスワード変更画面の場合、リダイレクトされず子要素が表示されること
it("test_ProtectedRoute_004_password_change_required_on_change_password_page_renders_children", () => {
  vi.mocked(useAuth).mockReturnValue({
    user: { ...baseUser, password_change_required_flag: true },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  });

  renderProtectedRoute("/change-password");

  expect(screen.getByText("パスワード変更フォーム")).toBeInTheDocument();
});

// ========== 単体テストNo.5 ==========
// 初回パスワード変更が完了済みの場合、子要素が表示されること
it("test_ProtectedRoute_005_password_change_not_required_renders_children", () => {
  vi.mocked(useAuth).mockReturnValue({
    user: baseUser,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  });

  renderProtectedRoute("/protected");

  expect(screen.getByText("保護対象コンテンツ")).toBeInTheDocument();
});
