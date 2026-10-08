/**
 * ヘッダー
 *
 * 【概要】
 * アプリ名、ログイン中のユーザー氏名、ログアウト操作を表示する共通部品
 */

import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export function Header() {
  const { user, logout } = useAuth();

  return (
    <header>
      <p>備品貸出管理システム</p>
      {user !== null && (
        <p>
          {user.name}さん
          <Link to="/equipment">備品一覧</Link>
          {user.role === "管理者" && <Link to="/equipment-management">備品管理</Link>}
          {user.role === "管理者" && <Link to="/users">ユーザー管理</Link>}
          <button type="button" onClick={() => void logout()}>
            ログアウト
          </button>
        </p>
      )}
    </header>
  );
}
