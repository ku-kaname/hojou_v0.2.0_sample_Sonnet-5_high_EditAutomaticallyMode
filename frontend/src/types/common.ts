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

export type LoanStatus = "貸出可" | "貸出中";

export type ReservationStatus = "承認済み" | "貸出中";

export interface EquipmentResponse {
  equipment_id: number;
  asset_number: string;
  name: string;
  category: string;
  description: string;
  location: string;
  active_flag: boolean;
  loan_status: LoanStatus;
  due_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface EquipmentCreateRequest {
  asset_number: string;
  name: string;
  category: string;
  description: string;
  location: string;
}

export type EquipmentUpdateRequest = EquipmentCreateRequest;

export interface ReservationResponse {
  loan_request_id: number;
  start_date: string;
  due_date: string;
  status: ReservationStatus;
  applicant_name?: string | null;
}

export interface EquipmentBulkImportErrorDetail {
  row_number: number | null;
  message: string;
}

export interface EquipmentBulkImportErrorResponse {
  error_list: EquipmentBulkImportErrorDetail[];
}

export interface EquipmentBulkImportResponse {
  registered_count: number;
  equipment_list: EquipmentResponse[];
}

export type LoanRequestStatus = "申請中" | "承認済み" | "貸出中" | "返却済み" | "却下" | "取消";

export interface LoanRequestResponse {
  loan_request_id: number;
  equipment_id: number;
  start_date: string;
  due_date: string;
  purpose: string;
  applicant_user_id: number;
  status: LoanRequestStatus;
  reject_cancel_reason: string | null;
  approved_rejected_by_user_id: number | null;
  lent_by_user_id: number | null;
  returned_by_user_id: number | null;
  cancelled_by_user_id: number | null;
  requested_at: string;
  approved_rejected_at: string | null;
  lent_at: string | null;
  returned_at: string | null;
  cancelled_at: string | null;
  return_note: string | null;
}

export interface LoanRequestCreateRequest {
  equipment_id: number;
  start_date: string;
  due_date: string;
  purpose: string;
}

export interface LoanRequestCancelRequest {
  reason?: string | null;
}

export interface LoanRequestRejectRequest {
  reason: string;
}

export type LoanRequestAdminCancelRequest = LoanRequestRejectRequest;

export type NotificationType = "承認" | "却下" | "取消" | "新規申請" | "返却期限";

export interface NotificationResponse {
  notification_id: number;
  notification_type: NotificationType;
  loan_request_id: number;
  read_flag: boolean;
  created_at: string;
}
