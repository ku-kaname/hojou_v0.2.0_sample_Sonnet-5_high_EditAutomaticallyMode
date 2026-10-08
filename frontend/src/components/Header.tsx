/**
 * ヘッダー
 *
 * 【概要】
 * アプリ名、ログイン中のユーザー氏名、ログアウト操作を表示する共通部品
 */

import { useAuth } from "../contexts/AuthContext";

export function Header() {
  const { user, logout } = useAuth();

  return (
    <header>
      <p>備品貸出管理システム</p>
      {user !== null && (
        <p>
          {user.name}さん
          <button type="button" onClick={() => void logout()}>
            ログアウト
          </button>
        </p>
      )}
    </header>
  );
}
