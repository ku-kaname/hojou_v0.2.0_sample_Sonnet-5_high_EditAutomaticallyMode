import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import { AuthProvider, useAuth } from "../../contexts/AuthContext";
import type { UserGetResponse } from "../../types/common";

vi.mock("../../api/client", () => ({
  apiGet: vi.fn(),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
  postForm: vi.fn(),
  setAccessToken: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

const ACCESS_TOKEN_STORAGE_KEY = "accessToken";

const mockUser: UserGetResponse = {
  user_id: "u001",
  name: "テスト太郎",
  department: "総務部",
  role: "一般",
  active_flag: true,
  password_change_required_flag: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderAuth() {
  return renderHook(() => useAuth(), { wrapper: AuthProvider });
}

describe("AuthContext", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.mocked(client.apiGet).mockReset();
    vi.mocked(client.apiPatch).mockReset();
    vi.mocked(client.apiPost).mockReset();
    vi.mocked(client.postForm).mockReset();
    vi.mocked(client.setAccessToken).mockReset();
    vi.mocked(client.setUnauthorizedHandler).mockReset();
  });

  // ==================================================
  // ログイン状態復元
  // テスト対象ファイル：AuthContext.tsx
  // テスト対象クラス：-
  // テスト対象メソッド：restoreSession
  // テスト仕様書：test_specification/unit_test_specification/フロントエンド共通基盤/ログイン状態復元_単体テスト仕様書.md
  // ==================================================

  // ========== 単体テストNo.1 ==========
  // 保存済みトークンがない場合、自分の情報取得を行わずローディングが終了すること
  it("test_restoreSession_001_no_stored_token_skips_fetch", async () => {
    const { result } = renderAuth();

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(client.apiGet).not.toHaveBeenCalled();
    expect(result.current.user).toBeNull();
  });

  // ========== 単体テストNo.2 ==========
  // 保存済みトークンが有効な場合、ユーザー情報を取得してログイン状態を復元すること
  it("test_restoreSession_002_valid_stored_token_restores_user", async () => {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "stored-token");
    vi.mocked(client.apiGet).mockResolvedValue(mockUser);

    const { result } = renderAuth();

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(client.setAccessToken).toHaveBeenCalledWith("stored-token");
    expect(result.current.user).toEqual(mockUser);
  });

  // ========== 単体テストNo.3 ==========
  // 保存済みトークンが無効な場合、ログイン状態をクリアすること
  it("test_restoreSession_003_invalid_stored_token_clears_session", async () => {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "stored-token");
    vi.mocked(client.apiGet).mockRejectedValue(new Error("unauthorized"));

    const { result } = renderAuth();

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull();
    expect(result.current.user).toBeNull();
  });

  // ==================================================
  // ログイン
  // テスト対象ファイル：AuthContext.tsx
  // テスト対象クラス：-
  // テスト対象メソッド：login
  // テスト仕様書：test_specification/unit_test_specification/フロントエンド共通基盤/ログイン_単体テスト仕様書.md
  // ==================================================

  // ========== 単体テストNo.1 ==========
  // ユーザーID・パスワードが正しい場合、トークンを保存してユーザー情報を返すこと
  it("test_login_001_valid_credentials_sets_user", async () => {
    vi.mocked(client.postForm).mockResolvedValue({
      access_token: "new-token",
      token_type: "bearer",
      password_change_required: false,
    });
    vi.mocked(client.apiGet).mockResolvedValue(mockUser);

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let loggedInUser: UserGetResponse | undefined;
    await act(async () => {
      loggedInUser = await result.current.login("u001", "Password123");
    });

    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe("new-token");
    expect(loggedInUser).toEqual(mockUser);
    expect(result.current.user).toEqual(mockUser);
  });

  // ========== 単体テストNo.2 ==========
  // ユーザーID・パスワードが正しくない場合、例外が発生しユーザー情報が設定されないこと
  it("test_login_002_invalid_credentials_throws_and_keeps_user_null", async () => {
    vi.mocked(client.postForm).mockRejectedValue(new Error("認証に失敗しました"));

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await expect(
      act(async () => {
        await result.current.login("u001", "WrongPassword");
      }),
    ).rejects.toThrow("認証に失敗しました");

    expect(result.current.user).toBeNull();
  });

  // ==================================================
  // パスワード変更
  // テスト対象ファイル：AuthContext.tsx
  // テスト対象クラス：-
  // テスト対象メソッド：changePassword
  // テスト仕様書：test_specification/unit_test_specification/フロントエンド共通基盤/パスワード変更_単体テスト仕様書.md
  // ==================================================

  // ========== 単体テストNo.1 ==========
  // 現在のパスワードが正しい場合、トークンを保存してユーザー情報を返すこと
  it("test_changePassword_001_valid_current_password_sets_user", async () => {
    vi.mocked(client.apiPatch).mockResolvedValue({
      access_token: "changed-token",
      token_type: "bearer",
      password_change_required: false,
    });
    vi.mocked(client.apiGet).mockResolvedValue(mockUser);

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let updatedUser: UserGetResponse | undefined;
    await act(async () => {
      updatedUser = await result.current.changePassword("OldPassword123", "NewPassword123");
    });

    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe("changed-token");
    expect(updatedUser).toEqual(mockUser);
  });

  // ========== 単体テストNo.2 ==========
  // 現在のパスワードが正しくない場合、例外が発生しユーザー情報が更新されないこと
  it("test_changePassword_002_invalid_current_password_throws", async () => {
    vi.mocked(client.apiGet).mockResolvedValue(mockUser);
    vi.mocked(client.postForm).mockResolvedValue({
      access_token: "token",
      token_type: "bearer",
      password_change_required: false,
    });
    const { result } = renderAuth();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.login("u001", "Password123");
    });

    vi.mocked(client.apiPatch).mockRejectedValue(new Error("現在のパスワードが正しくありません"));

    await expect(
      act(async () => {
        await result.current.changePassword("WrongPassword", "NewPassword123");
      }),
    ).rejects.toThrow("現在のパスワードが正しくありません");

    expect(result.current.user).toEqual(mockUser);
  });

  // ==================================================
  // ログアウト
  // テスト対象ファイル：AuthContext.tsx
  // テスト対象クラス：-
  // テスト対象メソッド：logout
  // テスト仕様書：test_specification/unit_test_specification/フロントエンド共通基盤/ログアウト_単体テスト仕様書.md
  // ==================================================

  // ========== 単体テストNo.1 ==========
  // ログアウト処理が成功した場合、ログイン状態をクリアすること
  it("test_logout_001_success_clears_session", async () => {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "stored-token");
    vi.mocked(client.apiGet).mockResolvedValue(mockUser);
    vi.mocked(client.apiPost).mockResolvedValue(undefined);

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.logout();
    });

    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull();
    expect(result.current.user).toBeNull();
  });

  // ========== 単体テストNo.2 ==========
  // ログアウト処理が失敗した場合でも、ログイン状態をクリアすること
  it("test_logout_002_failure_still_clears_session", async () => {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "stored-token");
    vi.mocked(client.apiGet).mockResolvedValue(mockUser);
    vi.mocked(client.apiPost).mockRejectedValue(new Error("network error"));

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let thrownError: unknown;
    await act(async () => {
      try {
        await result.current.logout();
      } catch (error) {
        thrownError = error;
      }
    });

    expect(thrownError).toBeInstanceOf(Error);
    expect((thrownError as Error).message).toBe("network error");
    expect(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull();
    expect(result.current.user).toBeNull();
  });
});
