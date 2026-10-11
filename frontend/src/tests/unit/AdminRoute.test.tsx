import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { AdminRoute } from "../../components/AdminRoute";
import { useAuth } from "../../contexts/AuthContext";
import type { UserGetResponse } from "../../types/common";

// ==================================================
// 管理者限定ルートガード
// テスト対象ファイル：AdminRoute.tsx
// テスト対象クラス：-
// テスト対象メソッド：AdminRoute
// テスト仕様書：test_specification/unit_test_specification/フロントエンド共通基盤/管理者限定ルートガード_単体テスト仕様書.md
// ==================================================

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

const baseUser: UserGetResponse = {
  user_id: "u001",
  name: "テスト太郎",
  department: "総務部",
  role: "管理者",
  active_flag: true,
  password_change_required_flag: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderAdminRoute() {
  render(
    <MemoryRouter initialEntries={["/admin"]}>
      <Routes>
        <Route
          path="/admin"
          element={
            <AdminRoute>
              <div>管理者限定コンテンツ</div>
            </AdminRoute>
          }
        />
        <Route path="/login" element={<div>ログイン画面</div>} />
        <Route path="/change-password" element={<div>パスワード変更画面</div>} />
        <Route path="/" element={<div>ホーム画面</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

// ========== 単体テストNo.1 ==========
// ログイン状態確認中の場合、ローディング表示となり子要素が表示されないこと
it("test_AdminRoute_001_loading_shows_loading_indicator", () => {
  vi.mocked(useAuth).mockReturnValue({
    user: null,
    isLoading: true,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  });

  renderAdminRoute();

  expect(screen.queryByText("管理者限定コンテンツ")).not.toBeInTheDocument();
  expect(screen.queryByText("ログイン画面")).not.toBeInTheDocument();
});

// ========== 単体テストNo.2 ==========
// 未ログインの場合、ログイン画面へリダイレクトされること
it("test_AdminRoute_002_not_logged_in_redirects_to_login", () => {
  vi.mocked(useAuth).mockReturnValue({
    user: null,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  });

  renderAdminRoute();

  expect(screen.getByText("ログイン画面")).toBeInTheDocument();
});

// ========== 単体テストNo.3 ==========
// 初回パスワード変更が未完了の場合、パスワード変更画面へリダイレクトされること
it("test_AdminRoute_003_password_change_required_redirects_to_change_password", () => {
  vi.mocked(useAuth).mockReturnValue({
    user: { ...baseUser, password_change_required_flag: true },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  });

  renderAdminRoute();

  expect(screen.getByText("パスワード変更画面")).toBeInTheDocument();
});

// ========== 単体テストNo.4 ==========
// 管理者ロールでない場合、ホーム画面へリダイレクトされること
it("test_AdminRoute_004_non_admin_role_redirects_to_home", () => {
  vi.mocked(useAuth).mockReturnValue({
    user: { ...baseUser, role: "一般" },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  });

  renderAdminRoute();

  expect(screen.getByText("ホーム画面")).toBeInTheDocument();
});

// ========== 単体テストNo.5 ==========
// 管理者ロールでリダイレクト条件に該当しない場合、子要素が表示されること
it("test_AdminRoute_005_admin_role_renders_children", () => {
  vi.mocked(useAuth).mockReturnValue({
    user: baseUser,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  });

  renderAdminRoute();

  expect(screen.getByText("管理者限定コンテンツ")).toBeInTheDocument();
});
