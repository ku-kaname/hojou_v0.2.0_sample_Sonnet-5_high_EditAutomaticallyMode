/**
 * 共通型定義
 *
 * 【概要】
 * 複数の画面・API呼び出しから共通して参照する型（ユーザー情報・トークン応答等）を定義する
 */

export type Role = "一般" | "管理者";

export interface UserGetResponse {
  user_id: string;
  name: string;
  department: string;
  role: Role;
  active_flag: boolean;
  password_change_required_flag: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  password_change_required: boolean;
}
