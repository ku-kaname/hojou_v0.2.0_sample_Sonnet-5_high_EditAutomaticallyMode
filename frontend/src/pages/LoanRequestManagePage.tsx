/**
 * 申請管理（管理者）画面
 *
 * 【概要】
 * 管理者が、全申請の一覧を確認し、申請中の承認・却下（F09）、承認済みの取消（F12）を行う画面
 *
 * 【備考】
 * 貸出処理・返却処理（F10・F11）は、別バックログ「実装（貸出・返却・履歴）」で本画面へ追加する予定であり、
 * 本画面では実装しない。
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { apiGet, apiPatch, ApiError } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingIndicator } from "../components/LoadingIndicator";
import type {
  EquipmentResponse,
  LoanRequestAdminCancelRequest,
  LoanRequestRejectRequest,
  LoanRequestResponse,
} from "../types/common";

function toErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

const STATUS_FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "すべて" },
  { value: "申請中", label: "申請中" },
  { value: "承認済み", label: "承認済み" },
  { value: "貸出中", label: "貸出中" },
  { value: "返却済み", label: "返却済み" },
  { value: "却下", label: "却下" },
  { value: "取消", label: "取消" },
];

type Panel =
  | { type: "none" }
  | { type: "reject"; loanRequest: LoanRequestResponse }
  | { type: "admin-cancel"; loanRequest: LoanRequestResponse };

/**
 * 申請一覧の備品情報取得
 *
 * 【処理概要】
 * - 申請一覧に含まれる備品IDごとに備品詳細を取得し、備品ID→備品情報のマップを作成する
 *
 * 【パラメータ】
 * - loanRequestList (LoanRequestResponse[]) : 貸出申請一覧 (必須)
 *
 * 【戻り値】
 * - equipmentMap (Map<number, EquipmentResponse>) : 備品ID→備品情報のマップ
 */
async function loadEquipmentMapForLoanRequests(
  loanRequestList: LoanRequestResponse[],
): Promise<Map<number, EquipmentResponse>> {
  const equipmentIdList = [...new Set(loanRequestList.map((loanRequest) => loanRequest.equipment_id))];
  const equipmentList = await Promise.all(
    equipmentIdList.map((equipmentId) => apiGet<EquipmentResponse>(`/equipment/${equipmentId}`)),
  );
  return new Map(equipmentList.map((equipment) => [equipment.equipment_id, equipment]));
}

export function LoanRequestManagePage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [loanRequestList, setLoanRequestList] = useState<LoanRequestResponse[] | null>(null);
  const [equipmentMap, setEquipmentMap] = useState<Map<number, EquipmentResponse>>(new Map());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>({ type: "none" });
  const [reasonInput, setReasonInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadLoanRequestList = useCallback(async (): Promise<void> => {
    setLoadError(null);
    try {
      const query = statusFilter === "" ? "" : `&status=${encodeURIComponent(statusFilter)}`;
      const list = await apiGet<LoanRequestResponse[]>(`/loan-requests?scope=all${query}`);
      setLoanRequestList(list);
      setEquipmentMap(await loadEquipmentMapForLoanRequests(list));
    } catch (error) {
      setLoadError(toErrorMessage(error, "申請一覧の取得に失敗しました。"));
    }
  }, [statusFilter]);

  useEffect(() => {
    void loadLoanRequestList();
  }, [loadLoanRequestList]);

  function openRejectPanel(loanRequest: LoanRequestResponse): void {
    setPanel({ type: "reject", loanRequest });
    setReasonInput("");
    setActionError(null);
  }

  function openAdminCancelPanel(loanRequest: LoanRequestResponse): void {
    setPanel({ type: "admin-cancel", loanRequest });
    setReasonInput("");
    setActionError(null);
  }

  function closePanel(): void {
    setPanel({ type: "none" });
  }

  async function handleApprove(loanRequestId: number): Promise<void> {
    setActionError(null);
    try {
      await apiPatch(`/loan-requests/${loanRequestId}/approve`);
      await loadLoanRequestList();
    } catch (error) {
      setActionError(toErrorMessage(error, "貸出申請の承認に失敗しました。"));
    }
  }

  async function handleRejectSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (panel.type !== "reject") {
      return;
    }
    setActionError(null);
    setIsSubmitting(true);
    try {
      const loanRequestRejectRequest: LoanRequestRejectRequest = { reason: reasonInput };
      await apiPatch(`/loan-requests/${panel.loanRequest.loan_request_id}/reject`, loanRequestRejectRequest);
      closePanel();
      await loadLoanRequestList();
    } catch (error) {
      setActionError(toErrorMessage(error, "貸出申請の却下に失敗しました。"));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleAdminCancelSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (panel.type !== "admin-cancel") {
      return;
    }
    setActionError(null);
    setIsSubmitting(true);
    try {
      const loanRequestAdminCancelRequest: LoanRequestAdminCancelRequest = { reason: reasonInput };
      await apiPatch(
        `/loan-requests/${panel.loanRequest.loan_request_id}/admin-cancel`,
        loanRequestAdminCancelRequest,
      );
      closePanel();
      await loadLoanRequestList();
    } catch (error) {
      setActionError(toErrorMessage(error, "貸出申請の取消に失敗しました。"));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (loanRequestList === null) {
    if (loadError !== null) {
      return (
        <div>
          <ErrorMessage message={loadError} />
          <button type="button" onClick={() => void loadLoanRequestList()}>
            再試行
          </button>
        </div>
      );
    }
    return <LoadingIndicator />;
  }

  return (
    <div>
      <h1>申請管理</h1>
      <p>貸出処理・返却処理は、別バックログで本画面に追加する予定です。</p>
      {loadError !== null && <ErrorMessage message={loadError} />}
      {actionError !== null && <ErrorMessage message={actionError} />}

      <label>
        状態で絞り込み
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          {STATUS_FILTER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      {loanRequestList.length === 0 ? (
        <p>該当する申請はありません。</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>資産番号</th>
              <th>備品名</th>
              <th>申請者（内部ID）</th>
              <th>開始日</th>
              <th>返却予定日</th>
              <th>用途</th>
              <th>状態</th>
              <th>却下・取消理由</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {loanRequestList.map((loanRequest) => {
              const equipment = equipmentMap.get(loanRequest.equipment_id);
              return (
                <tr key={loanRequest.loan_request_id}>
                  <td>{equipment?.asset_number ?? loanRequest.equipment_id}</td>
                  <td>{equipment?.name ?? "-"}</td>
                  <td>{loanRequest.applicant_user_id}</td>
                  <td>{loanRequest.start_date}</td>
                  <td>{loanRequest.due_date}</td>
                  <td>{loanRequest.purpose}</td>
                  <td>{loanRequest.status}</td>
                  <td>{loanRequest.reject_cancel_reason ?? "-"}</td>
                  <td>
                    {loanRequest.status === "申請中" && (
                      <>
                        <button type="button" onClick={() => void handleApprove(loanRequest.loan_request_id)}>
                          承認
                        </button>
                        <button type="button" onClick={() => openRejectPanel(loanRequest)}>
                          却下
                        </button>
                      </>
                    )}
                    {loanRequest.status === "承認済み" && (
                      <button type="button" onClick={() => openAdminCancelPanel(loanRequest)}>
                        取消
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {panel.type === "reject" && (
        <form onSubmit={(event) => void handleRejectSubmit(event)}>
          <h2>貸出申請却下（申請ID: {panel.loanRequest.loan_request_id}）</h2>
          <label>
            却下理由
            <input
              type="text"
              value={reasonInput}
              onChange={(event) => setReasonInput(event.target.value)}
              minLength={1}
              maxLength={200}
              required
            />
          </label>
          <button type="submit" disabled={isSubmitting}>
            却下する
          </button>
          <button type="button" onClick={closePanel}>
            キャンセル
          </button>
        </form>
      )}

      {panel.type === "admin-cancel" && (
        <form onSubmit={(event) => void handleAdminCancelSubmit(event)}>
          <h2>貸出申請取消（申請ID: {panel.loanRequest.loan_request_id}）</h2>
          <label>
            取消理由
            <input
              type="text"
              value={reasonInput}
              onChange={(event) => setReasonInput(event.target.value)}
              minLength={1}
              maxLength={200}
              required
            />
          </label>
          <button type="submit" disabled={isSubmitting}>
            取消す
          </button>
          <button type="button" onClick={closePanel}>
            キャンセル
          </button>
        </form>
      )}
    </div>
  );
}
