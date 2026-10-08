/**
 * 備品一覧画面
 *
 * 【概要】
 * 分類・キーワード・貸出状況による備品の検索・一覧表示を行う画面
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiGet, ApiError } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingIndicator } from "../components/LoadingIndicator";
import type { EquipmentResponse, LoanStatus } from "../types/common";

interface EquipmentFilterState {
  category: string;
  keyword: string;
  loanStatus: LoanStatus | "";
}

const EMPTY_FILTER: EquipmentFilterState = {
  category: "",
  keyword: "",
  loanStatus: "",
};

function toErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function buildEquipmentListQuery(filter: EquipmentFilterState): string {
  const queryParams = new URLSearchParams();
  if (filter.category !== "") {
    queryParams.set("category", filter.category);
  }
  if (filter.keyword !== "") {
    queryParams.set("keyword", filter.keyword);
  }
  if (filter.loanStatus !== "") {
    queryParams.set("loan_status", filter.loanStatus);
  }
  const queryString = queryParams.toString();
  return queryString === "" ? "" : `?${queryString}`;
}

export function EquipmentListPage() {
  const [equipmentList, setEquipmentList] = useState<EquipmentResponse[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [appliedFilter, setAppliedFilter] = useState<EquipmentFilterState>(EMPTY_FILTER);
  const [filterForm, setFilterForm] = useState<EquipmentFilterState>(EMPTY_FILTER);

  const loadEquipmentList = useCallback(async (filter: EquipmentFilterState): Promise<void> => {
    setLoadError(null);
    try {
      const query = buildEquipmentListQuery(filter);
      const list = await apiGet<EquipmentResponse[]>(`/equipment${query}`);
      setEquipmentList(list);
    } catch (error) {
      setLoadError(toErrorMessage(error, "備品一覧の取得に失敗しました。"));
    }
  }, []);

  useEffect(() => {
    void loadEquipmentList(appliedFilter);
  }, [appliedFilter, loadEquipmentList]);

  function handleFilterSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setAppliedFilter(filterForm);
  }

  function handleFilterReset(): void {
    setFilterForm(EMPTY_FILTER);
    setAppliedFilter(EMPTY_FILTER);
  }

  return (
    <div>
      <h1>備品一覧</h1>

      <form onSubmit={handleFilterSubmit}>
        <label>
          分類
          <input
            type="text"
            value={filterForm.category}
            onChange={(event) => setFilterForm({ ...filterForm, category: event.target.value })}
            maxLength={50}
          />
        </label>
        <label>
          キーワード
          <input
            type="text"
            value={filterForm.keyword}
            onChange={(event) => setFilterForm({ ...filterForm, keyword: event.target.value })}
            maxLength={100}
          />
        </label>
        <label>
          貸出状況
          <select
            value={filterForm.loanStatus}
            onChange={(event) =>
              setFilterForm({ ...filterForm, loanStatus: event.target.value as LoanStatus | "" })
            }
          >
            <option value="">すべて</option>
            <option value="貸出可">貸出可</option>
            <option value="貸出中">貸出中</option>
          </select>
        </label>
        <button type="submit">検索</button>
        <button type="button" onClick={handleFilterReset}>
          条件クリア
        </button>
      </form>

      {loadError !== null && <ErrorMessage message={loadError} />}

      {equipmentList === null ? (
        loadError === null && <LoadingIndicator />
      ) : (
        <table>
          <thead>
            <tr>
              <th>資産番号</th>
              <th>備品名</th>
              <th>分類</th>
              <th>保管場所</th>
              <th>貸出状況</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {equipmentList.map((equipment) => (
              <tr key={equipment.equipment_id}>
                <td>{equipment.asset_number}</td>
                <td>{equipment.name}</td>
                <td>{equipment.category}</td>
                <td>{equipment.location}</td>
                <td>{equipment.loan_status}</td>
                <td>
                  <Link to={`/equipment/${equipment.equipment_id}`}>詳細</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
