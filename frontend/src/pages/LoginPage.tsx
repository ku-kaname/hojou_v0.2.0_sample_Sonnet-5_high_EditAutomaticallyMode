/**
 * ログイン画面
 *
 * 【概要】
 * ユーザーID・パスワードでログインし、認証成功後は初回パスワード変更要否に応じて遷移する画面
 */

import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { useAuth } from "../contexts/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const currentUser = await login(userId, password);
      navigate(currentUser.password_change_required_flag ? "/change-password" : "/", {
        replace: true,
      });
    } catch (loginError) {
      setError(loginError instanceof ApiError ? loginError.message : "ログインに失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div>
      <h1>ログイン</h1>
      {error !== null && <ErrorMessage message={error} />}
      <form onSubmit={(event) => void handleSubmit(event)}>
        <label>
          ユーザーID
          <input
            type="text"
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
            minLength={1}
            maxLength={32}
            required
            autoFocus
          />
        </label>
        <label>
          パスワード
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={1}
            maxLength={32}
            required
          />
        </label>
        <button type="submit" disabled={isSubmitting}>
          ログイン
        </button>
      </form>
    </div>
  );
}
