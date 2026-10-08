/**
 * 自分の申請一覧画面
 *
 * 【概要】
 * ログインユーザーが自分の貸出申請の状態・履歴を確認し（F07）、取消を行う（F06）画面
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { apiGet, apiPatch, ApiError } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingIndicator } from "../components/LoadingIndicator";
import type {
  EquipmentResponse,
  LoanRequestCancelRequest,
  LoanRequestResponse,
  LoanRequestStatus,
} from "../types/common";

function toErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

const CANCELLABLE_STATUS_LIST: LoanRequestStatus[] = ["申請中", "承認済み"];

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

export function LoanRequestMinePage() {
  const [loanRequestList, setLoanRequestList] = useState<LoanRequestResponse[] | null>(null);
  const [equipmentMap, setEquipmentMap] = useState<Map<number, EquipmentResponse>>(new Map());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<LoanRequestResponse | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadLoanRequestList = useCallback(async (): Promise<void> => {
    setLoadError(null);
    try {
      const list = await apiGet<LoanRequestResponse[]>("/loan-requests?scope=mine");
      setLoanRequestList(list);
      setEquipmentMap(await loadEquipmentMapForLoanRequests(list));
    } catch (error) {
      setLoadError(toErrorMessage(error, "自分の申請一覧の取得に失敗しました。"));
    }
  }, []);

  useEffect(() => {
    void loadLoanRequestList();
  }, [loadLoanRequestList]);

  function openCancelPanel(loanRequest: LoanRequestResponse): void {
    setCancelTarget(loanRequest);
    setCancelReason("");
    setActionError(null);
  }

  function closeCancelPanel(): void {
    setCancelTarget(null);
  }

  async function handleCancelSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (cancelTarget === null) {
      return;
    }
    setActionError(null);
    setIsSubmitting(true);
    try {
      const loanRequestCancelRequest: LoanRequestCancelRequest = {
        reason: cancelReason === "" ? null : cancelReason,
      };
      await apiPatch(`/loan-requests/${cancelTarget.loan_request_id}/cancel`, loanRequestCancelRequest);
      closeCancelPanel();
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
      <h1>自分の申請一覧</h1>
      {loadError !== null && <ErrorMessage message={loadError} />}

      {loanRequestList.length === 0 ? (
        <p>申請はありません。</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>資産番号</th>
              <th>備品名</th>
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
                  <td>{loanRequest.start_date}</td>
                  <td>{loanRequest.due_date}</td>
                  <td>{loanRequest.purpose}</td>
                  <td>{loanRequest.status}</td>
                  <td>{loanRequest.reject_cancel_reason ?? "-"}</td>
                  <td>
                    {CANCELLABLE_STATUS_LIST.includes(loanRequest.status) && (
                      <button type="button" onClick={() => openCancelPanel(loanRequest)}>
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

      {cancelTarget !== null && (
        <form onSubmit={(event) => void handleCancelSubmit(event)}>
          <h2>
            貸出申請取消（
            {equipmentMap.get(cancelTarget.equipment_id)?.name ?? cancelTarget.equipment_id}）
          </h2>
          {actionError !== null && <ErrorMessage message={actionError} />}
          <label>
            取消理由（任意）
            <input
              type="text"
              value={cancelReason}
              onChange={(event) => setCancelReason(event.target.value)}
              maxLength={200}
            />
          </label>
          <button type="submit" disabled={isSubmitting}>
            取消す
          </button>
          <button type="button" onClick={closeCancelPanel}>
            キャンセル
          </button>
        </form>
      )}
    </div>
  );
}
