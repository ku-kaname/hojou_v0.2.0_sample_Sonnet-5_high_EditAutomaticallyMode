/**
 * 認証状態管理
 *
 * 【概要】
 * ログイン状態（ユーザー情報）の保持、ログイン状態復元、ログイン・ログアウト処理を提供する
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  apiGet,
  apiPatch,
  apiPost,
  postForm,
  setAccessToken,
  setUnauthorizedHandler,
} from "../api/client";
import type { TokenResponse, UserGetResponse } from "../types/common";

const ACCESS_TOKEN_STORAGE_KEY = "accessToken";

interface AuthContextValue {
  user: UserGetResponse | null;
  isLoading: boolean;
  login: (userId: string, password: string) => Promise<UserGetResponse>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<UserGetResponse>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserGetResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const clearSession = useCallback((): void => {
    window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
    setAccessToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(clearSession);
  }, [clearSession]);

  /**
   * 認証トークンの反映
   *
   * 【処理概要】
   * - 発行されたアクセストークンを保存し、最新のユーザー情報を取得してログイン状態へ反映する
   *
   * 【パラメータ】
   * - accessToken (string) : アクセストークン (必須)
   *
   * 【戻り値】
   * - user (UserGetResponse) : ユーザー情報
   *
   * 【例外処理】
   * - ApiError : ユーザー情報取得に失敗した場合
   *
   * 【処理フロー】
   * 1. 認証トークンの保存
   * 2. 自分の情報取得
   * 3. 戻り値を返却
   */
  const applyAccessToken = useCallback(async (accessToken: string): Promise<UserGetResponse> => {
    // 1. 認証トークンの保存
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, accessToken);
    setAccessToken(accessToken);

    // 2. 自分の情報取得
    const currentUser = await apiGet<UserGetResponse>("/users/me");
    setUser(currentUser);

    // 3. 戻り値を返却
    return currentUser;
  }, []);

  useEffect(() => {
    const storedToken = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
    if (storedToken === null) {
      setIsLoading(false);
      return;
    }

    /**
     * ログイン状態復元
     *
     * 【処理概要】
     * - 保存済みの認証トークンが有効であれば、ユーザー情報を取得してログイン状態を復元する
     * - 無効であればログイン状態をクリアする
     *
     * 【パラメータ】
     * - なし
     *
     * 【戻り値】
     * - なし
     *
     * 【例外処理】
     * - なし（ユーザー情報取得に失敗した場合はログイン状態をクリアする）
     *
     * 【処理フロー】
     * 1. 認証トークンの設定
     * 2. 自分の情報取得
     * 3. 例外処理
     */
    async function restoreSession(): Promise<void> {
      // 1. 認証トークンの設定
      setAccessToken(storedToken);

      // 2. 自分の情報取得
      try {
        const currentUser = await apiGet<UserGetResponse>("/users/me");
        setUser(currentUser);
      } catch {
        // 3. 例外処理：ログイン状態をクリア
        clearSession();
      } finally {
        setIsLoading(false);
      }
    }

    void restoreSession();
  }, [clearSession]);

  /**
   * ログイン
   *
   * 【処理概要】
   * - ユーザーID・パスワードでトークン発行を行い、認証トークンを保存した上で自分の情報を取得する
   *
   * 【パラメータ】
   * - userId (string) : ユーザーID (必須)
   * - password (string) : パスワード (必須)
   *
   * 【戻り値】
   * - user (UserGetResponse) : ユーザー情報
   *
   * 【例外処理】
   * - ApiError : ユーザーID・パスワードが正しくない場合等
   *
   * 【処理フロー】
   * 1. トークン発行
   * 2. 認証トークンの反映
   * 3. 戻り値を返却
   */
  const login = useCallback(
    async (userId: string, password: string): Promise<UserGetResponse> => {
      // 1. トークン発行
      const tokenResponse = await postForm<TokenResponse>("/token", {
        username: userId,
        password,
      });

      // 2. 認証トークンの反映
      const currentUser = await applyAccessToken(tokenResponse.access_token);

      // 3. 戻り値を返却
      return currentUser;
    },
    [applyAccessToken],
  );

  /**
   * パスワード変更
   *
   * 【処理概要】
   * - 現在のパスワード・新しいパスワードでパスワード変更を行い、発行された認証トークンを保存した上で自分の情報を取得する
   *
   * 【パラメータ】
   * - currentPassword (string) : 現在のパスワード (必須)
   * - newPassword (string) : 新しいパスワード (必須)
   *
   * 【戻り値】
   * - user (UserGetResponse) : ユーザー情報
   *
   * 【例外処理】
   * - ApiError : 現在のパスワードが正しくない場合等
   *
   * 【処理フロー】
   * 1. パスワード変更
   * 2. 認証トークンの反映
   * 3. 戻り値を返却
   */
  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string): Promise<UserGetResponse> => {
      // 1. パスワード変更
      const tokenResponse = await apiPatch<TokenResponse>("/users/me/password", {
        current_password: currentPassword,
        new_password: newPassword,
      });

      // 2. 認証トークンの反映
      const currentUser = await applyAccessToken(tokenResponse.access_token);

      // 3. 戻り値を返却
      return currentUser;
    },
    [applyAccessToken],
  );

  /**
   * ログアウト
   *
   * 【処理概要】
   * - ログアウト処理を呼び出し、成否に関わらずログイン状態をクリアする
   *
   * 【パラメータ】
   * - なし
   *
   * 【戻り値】
   * - なし
   *
   * 【例外処理】
   * - なし
   *
   * 【処理フロー】
   * 1. ログアウト処理の呼び出し
   * 2. ログイン状態のクリア
   */
  const logout = useCallback(async (): Promise<void> => {
    // 1. ログアウト処理の呼び出し
    try {
      await apiPost("/logout");
    } finally {
      // 2. ログイン状態のクリア
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, login, logout, changePassword }),
    [user, isLoading, login, logout, changePassword],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuthはAuthProviderの配下で使用してください");
  }
  return context;
}
