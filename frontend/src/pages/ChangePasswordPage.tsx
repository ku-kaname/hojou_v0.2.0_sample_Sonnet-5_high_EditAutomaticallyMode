/**
 * パスワード変更画面
 *
 * 【概要】
 * ログイン中のユーザー自身のパスワードを変更する画面（初回ログイン時の変更を含む）
 */

import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { useAuth } from "../contexts/AuthContext";

export function ChangePasswordPage() {
  const { changePassword } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await changePassword(currentPassword, newPassword);
      navigate("/", { replace: true });
    } catch (changeError) {
      setError(
        changeError instanceof ApiError ? changeError.message : "パスワード変更に失敗しました。",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div>
      <h1>パスワード変更</h1>
      {error !== null && <ErrorMessage message={error} />}
      <form onSubmit={(event) => void handleSubmit(event)}>
        <label>
          現在のパスワード
          <input
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            minLength={8}
            maxLength={32}
            required
            autoFocus
          />
        </label>
        <label>
          新しいパスワード
          <input
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            minLength={8}
            maxLength={32}
            required
          />
        </label>
        <button type="submit" disabled={isSubmitting}>
          変更
        </button>
      </form>
    </div>
  );
}
