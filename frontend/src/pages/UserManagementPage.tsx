/**
 * ユーザー管理画面
 *
 * 【概要】
 * ユーザーの一覧表示、新規登録、編集、無効化・再有効化、パスワード初期化を行う管理者用画面
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { apiGet, apiPatch, apiPost, apiPut, ApiError } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingIndicator } from "../components/LoadingIndicator";
import type { Role, UserGetResponse } from "../types/common";

type Panel =
  | { type: "list" }
  | { type: "create" }
  | { type: "edit"; user: UserGetResponse }
  | { type: "reset-password"; user: UserGetResponse };

interface UserFormState {
  userId: string;
  name: string;
  department: string;
  role: Role;
  initialPassword: string;
}

const EMPTY_FORM: UserFormState = {
  userId: "",
  name: "",
  department: "",
  role: "一般",
  initialPassword: "",
};

function toErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function UserManagementPage() {
  const [users, setUsers] = useState<UserGetResponse[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>({ type: "list" });
  const [form, setForm] = useState<UserFormState>(EMPTY_FORM);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadUsers = useCallback(async (): Promise<void> => {
    setLoadError(null);
    try {
      const userList = await apiGet<UserGetResponse[]>("/users");
      setUsers(userList);
    } catch (error) {
      setLoadError(toErrorMessage(error, "ユーザー一覧の取得に失敗しました。"));
    }
  }, []);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  function openCreatePanel(): void {
    setForm(EMPTY_FORM);
    setActionError(null);
    setPanel({ type: "create" });
  }

  function openEditPanel(user: UserGetResponse): void {
    setForm({
      userId: user.user_id,
      name: user.name,
      department: user.department,
      role: user.role,
      initialPassword: "",
    });
    setActionError(null);
    setPanel({ type: "edit", user });
  }

  function openResetPasswordPanel(user: UserGetResponse): void {
    setForm({ ...EMPTY_FORM, userId: user.user_id });
    setActionError(null);
    setPanel({ type: "reset-password", user });
  }

  function closePanel(): void {
    setPanel({ type: "list" });
    setActionError(null);
  }

  async function handleCreateSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setActionError(null);
    setIsSubmitting(true);
    try {
      await apiPost("/users", {
        user_id: form.userId,
        name: form.name,
        department: form.department,
        role: form.role,
        initial_password: form.initialPassword,
      });
      await loadUsers();
      closePanel();
    } catch (error) {
      setActionError(toErrorMessage(error, "ユーザー登録に失敗しました。"));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleEditSubmit(
    event: FormEvent<HTMLFormElement>,
    userId: string,
  ): Promise<void> {
    event.preventDefault();
    setActionError(null);
    setIsSubmitting(true);
    try {
      await apiPut(`/users/${userId}`, {
        name: form.name,
        department: form.department,
        role: form.role,
      });
      await loadUsers();
      closePanel();
    } catch (error) {
      setActionError(toErrorMessage(error, "ユーザー編集に失敗しました。"));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleResetPasswordSubmit(
    event: FormEvent<HTMLFormElement>,
    userId: string,
  ): Promise<void> {
    event.preventDefault();
    setActionError(null);
    setIsSubmitting(true);
    try {
      await apiPatch(`/users/${userId}/reset-password`, { initial_password: form.initialPassword });
      await loadUsers();
      closePanel();
    } catch (error) {
      setActionError(toErrorMessage(error, "パスワード初期化に失敗しました。"));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleToggleActive(user: UserGetResponse): Promise<void> {
    setActionError(null);
    const action = user.active_flag ? "deactivate" : "activate";
    try {
      await apiPatch(`/users/${user.user_id}/${action}`);
      await loadUsers();
    } catch (error) {
      setActionError(toErrorMessage(error, "ユーザー状態の更新に失敗しました。"));
    }
  }

  if (users === null) {
    if (loadError !== null) {
      return (
        <div>
          <ErrorMessage message={loadError} />
          <button type="button" onClick={() => void loadUsers()}>
            再試行
          </button>
        </div>
      );
    }
    return <LoadingIndicator />;
  }

  return (
    <div>
      <h1>ユーザー管理</h1>
      {loadError !== null && <ErrorMessage message={loadError} />}

      {panel.type === "list" && (
        <>
          <button type="button" onClick={openCreatePanel}>
            新規登録
          </button>
          <table>
            <thead>
              <tr>
                <th>ユーザーID</th>
                <th>氏名</th>
                <th>所属</th>
                <th>ロール</th>
                <th>状態</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.user_id}>
                  <td>{user.user_id}</td>
                  <td>{user.name}</td>
                  <td>{user.department}</td>
                  <td>{user.role}</td>
                  <td>{user.active_flag ? "有効" : "無効"}</td>
                  <td>
                    <button type="button" onClick={() => openEditPanel(user)}>
                      編集
                    </button>
                    <button type="button" onClick={() => openResetPasswordPanel(user)}>
                      パスワード初期化
                    </button>
                    <button type="button" onClick={() => void handleToggleActive(user)}>
                      {user.active_flag ? "無効化" : "再有効化"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {panel.type === "create" && (
        <form onSubmit={(event) => void handleCreateSubmit(event)}>
          <h2>ユーザー新規登録</h2>
          {actionError !== null && <ErrorMessage message={actionError} />}
          <label>
            ユーザーID
            <input
              type="text"
              value={form.userId}
              onChange={(event) => setForm({ ...form, userId: event.target.value })}
              minLength={3}
              maxLength={32}
              pattern="^[A-Za-z0-9_-]+$"
              required
            />
          </label>
          <label>
            氏名
            <input
              type="text"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              minLength={1}
              maxLength={50}
              required
            />
          </label>
          <label>
            所属
            <input
              type="text"
              value={form.department}
              onChange={(event) => setForm({ ...form, department: event.target.value })}
              maxLength={50}
            />
          </label>
          <label>
            ロール
            <select
              value={form.role}
              onChange={(event) => setForm({ ...form, role: event.target.value as Role })}
            >
              <option value="一般">一般</option>
              <option value="管理者">管理者</option>
            </select>
          </label>
          <label>
            初期パスワード
            <input
              type="password"
              value={form.initialPassword}
              onChange={(event) => setForm({ ...form, initialPassword: event.target.value })}
              minLength={8}
              maxLength={32}
              required
            />
          </label>
          <button type="submit" disabled={isSubmitting}>
            登録
          </button>
          <button type="button" onClick={closePanel}>
            キャンセル
          </button>
        </form>
      )}

      {panel.type === "edit" && (
        <form onSubmit={(event) => void handleEditSubmit(event, panel.user.user_id)}>
          <h2>ユーザー編集（{panel.user.user_id}）</h2>
          {actionError !== null && <ErrorMessage message={actionError} />}
          <label>
            氏名
            <input
              type="text"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              minLength={1}
              maxLength={50}
              required
            />
          </label>
          <label>
            所属
            <input
              type="text"
              value={form.department}
              onChange={(event) => setForm({ ...form, department: event.target.value })}
              maxLength={50}
            />
          </label>
          <label>
            ロール
            <select
              value={form.role}
              onChange={(event) => setForm({ ...form, role: event.target.value as Role })}
            >
              <option value="一般">一般</option>
              <option value="管理者">管理者</option>
            </select>
          </label>
          <button type="submit" disabled={isSubmitting}>
            保存
          </button>
          <button type="button" onClick={closePanel}>
            キャンセル
          </button>
        </form>
      )}

      {panel.type === "reset-password" && (
        <form onSubmit={(event) => void handleResetPasswordSubmit(event, panel.user.user_id)}>
          <h2>パスワード初期化（{panel.user.user_id}）</h2>
          {actionError !== null && <ErrorMessage message={actionError} />}
          <label>
            新しい初期パスワード
            <input
              type="password"
              value={form.initialPassword}
              onChange={(event) => setForm({ ...form, initialPassword: event.target.value })}
              minLength={8}
              maxLength={32}
              required
            />
          </label>
          <button type="submit" disabled={isSubmitting}>
            初期化
          </button>
          <button type="button" onClick={closePanel}>
            キャンセル
          </button>
        </form>
      )}
    </div>
  );
}
