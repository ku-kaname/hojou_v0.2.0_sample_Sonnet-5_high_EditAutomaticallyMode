/**
 * 期限超過一覧（管理者）画面
 *
 * 【概要】
 * 管理者が、返却予定日を過ぎた貸出中の申請一覧を確認する画面（F13）
 */

import { useCallback, useEffect, useState } from "react";
import { apiGet, ApiError } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingIndicator } from "../components/LoadingIndicator";
import type { EquipmentResponse, LoanRequestResponse } from "../types/common";

function toErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

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

export function OverdueLoanRequestsPage() {
  const [loanRequestList, setLoanRequestList] = useState<LoanRequestResponse[] | null>(null);
  const [equipmentMap, setEquipmentMap] = useState<Map<number, EquipmentResponse>>(new Map());
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadOverdueLoanRequestList = useCallback(async (): Promise<void> => {
    setLoadError(null);
    try {
      const list = await apiGet<LoanRequestResponse[]>("/loan-requests?scope=overdue");
      setLoanRequestList(list);
      setEquipmentMap(await loadEquipmentMapForLoanRequests(list));
    } catch (error) {
      setLoadError(toErrorMessage(error, "期限超過一覧の取得に失敗しました。"));
    }
  }, []);

  useEffect(() => {
    void loadOverdueLoanRequestList();
  }, [loadOverdueLoanRequestList]);

  if (loanRequestList === null) {
    if (loadError !== null) {
      return (
        <div>
          <ErrorMessage message={loadError} />
          <button type="button" onClick={() => void loadOverdueLoanRequestList()}>
            再試行
          </button>
        </div>
      );
    }
    return <LoadingIndicator />;
  }

  return (
    <div>
      <h1>期限超過一覧</h1>
      {loadError !== null && <ErrorMessage message={loadError} />}

      {loanRequestList.length === 0 ? (
        <p>期限超過中の貸出はありません。</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>資産番号</th>
              <th>備品名</th>
              <th>借用者（内部ID）</th>
              <th>開始日</th>
              <th>返却予定日</th>
              <th>用途</th>
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
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
