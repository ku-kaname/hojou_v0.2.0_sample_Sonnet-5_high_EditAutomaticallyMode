/**
 * 貸出履歴（管理者）画面
 *
 * 【概要】
 * 管理者が、全履歴を状態で絞り込んで閲覧し、期間・備品・借用者で絞り込んでCSV出力する画面（F17）
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { apiGet, apiGetBlob, ApiError } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingIndicator } from "../components/LoadingIndicator";
import type { EquipmentResponse, LoanRequestResponse } from "../types/common";

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

interface ExportForm {
  startDateFrom: string;
  startDateTo: string;
  equipmentId: string;
  applicantUserId: string;
}

const EMPTY_EXPORT_FORM: ExportForm = {
  startDateFrom: "",
  startDateTo: "",
  equipmentId: "",
  applicantUserId: "",
};

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

/**
 * CSV出力クエリ文字列の組み立て
 *
 * 【処理概要】
 * - CSV出力フォームの入力値のうち、入力済みの項目のみをクエリパラメータへ変換する
 *
 * 【パラメータ】
 * - exportForm (ExportForm) : CSV出力フォーム入力値 (必須)
 *
 * 【戻り値】
 * - query (string) : クエリ文字列（先頭の`?`を含む。絞り込みなしの場合は空文字）
 */
function buildExportQuery(exportForm: ExportForm): string {
  const paramList: string[] = [];
  if (exportForm.startDateFrom !== "") {
    paramList.push(`start_date_from=${encodeURIComponent(exportForm.startDateFrom)}`);
  }
  if (exportForm.startDateTo !== "") {
    paramList.push(`start_date_to=${encodeURIComponent(exportForm.startDateTo)}`);
  }
  if (exportForm.equipmentId !== "") {
    paramList.push(`equipment_id=${encodeURIComponent(exportForm.equipmentId)}`);
  }
  if (exportForm.applicantUserId !== "") {
    paramList.push(`applicant_user_id=${encodeURIComponent(exportForm.applicantUserId)}`);
  }
  return paramList.length === 0 ? "" : `?${paramList.join("&")}`;
}

export function LoanHistoryPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [loanRequestList, setLoanRequestList] = useState<LoanRequestResponse[] | null>(null);
  const [equipmentMap, setEquipmentMap] = useState<Map<number, EquipmentResponse>>(new Map());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [exportForm, setExportForm] = useState<ExportForm>(EMPTY_EXPORT_FORM);
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const loadLoanRequestList = useCallback(async (): Promise<void> => {
    setLoadError(null);
    try {
      const query = statusFilter === "" ? "" : `&status=${encodeURIComponent(statusFilter)}`;
      const list = await apiGet<LoanRequestResponse[]>(`/loan-requests?scope=all${query}`);
      setLoanRequestList(list);
      setEquipmentMap(await loadEquipmentMapForLoanRequests(list));
    } catch (error) {
      setLoadError(toErrorMessage(error, "履歴の取得に失敗しました。"));
    }
  }, [statusFilter]);

  useEffect(() => {
    void loadLoanRequestList();
  }, [loadLoanRequestList]);

  async function handleExportSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setExportError(null);
    setIsExporting(true);
    try {
      const query = buildExportQuery(exportForm);
      const { blob, fileName } = await apiGetBlob(`/loan-requests/export${query}`, "loan_requests_export.csv");
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = fileName;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      setExportError(toErrorMessage(error, "CSV出力に失敗しました。"));
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div>
      <h1>貸出履歴</h1>

      <h2>履歴一覧</h2>
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

      {loanRequestList === null ? (
        loadError !== null ? (
          <div>
            <ErrorMessage message={loadError} />
            <button type="button" onClick={() => void loadLoanRequestList()}>
              再試行
            </button>
          </div>
        ) : (
          <LoadingIndicator />
        )
      ) : loanRequestList.length === 0 ? (
        <p>該当する履歴はありません。</p>
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
              <th>状態</th>
              <th>返却日時</th>
              <th>状態メモ</th>
              <th>却下・取消理由</th>
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
                  <td>{loanRequest.returned_at ?? "-"}</td>
                  <td>{loanRequest.return_note ?? "-"}</td>
                  <td>{loanRequest.reject_cancel_reason ?? "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <h2>CSV出力</h2>
      <form onSubmit={(event) => void handleExportSubmit(event)}>
        {exportError !== null && <ErrorMessage message={exportError} />}
        <label>
          開始日（下限）
          <input
            type="date"
            value={exportForm.startDateFrom}
            onChange={(event) => setExportForm({ ...exportForm, startDateFrom: event.target.value })}
          />
        </label>
        <label>
          開始日（上限）
          <input
            type="date"
            value={exportForm.startDateTo}
            onChange={(event) => setExportForm({ ...exportForm, startDateTo: event.target.value })}
          />
        </label>
        <label>
          備品（内部ID）
          <input
            type="number"
            value={exportForm.equipmentId}
            onChange={(event) => setExportForm({ ...exportForm, equipmentId: event.target.value })}
            min={1}
          />
        </label>
        <label>
          借用者（内部ID）
          <input
            type="number"
            value={exportForm.applicantUserId}
            onChange={(event) => setExportForm({ ...exportForm, applicantUserId: event.target.value })}
            min={1}
          />
        </label>
        <button type="submit" disabled={isExporting}>
          CSV出力
        </button>
      </form>
    </div>
  );
}
