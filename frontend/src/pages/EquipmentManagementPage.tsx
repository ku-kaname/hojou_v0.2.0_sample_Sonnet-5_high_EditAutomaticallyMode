/**
 * 備品管理画面
 *
 * 【概要】
 * 備品の一覧表示、新規登録、編集、無効化・再有効化、CSV一括登録を行う管理者用画面
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { apiGet, apiPatch, apiPost, apiPut, ApiError, postFormData } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingIndicator } from "../components/LoadingIndicator";
import type {
  EquipmentBulkImportErrorResponse,
  EquipmentBulkImportResponse,
  EquipmentResponse,
} from "../types/common";

type Panel =
  | { type: "list" }
  | { type: "create" }
  | { type: "edit"; equipment: EquipmentResponse }
  | { type: "bulk-import" };

interface EquipmentFormState {
  assetNumber: string;
  name: string;
  category: string;
  description: string;
  location: string;
}

const EMPTY_FORM: EquipmentFormState = {
  assetNumber: "",
  name: "",
  category: "",
  description: "",
  location: "",
};

function toErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function isBulkImportErrorResponse(detail: unknown): detail is EquipmentBulkImportErrorResponse {
  return (
    typeof detail === "object" &&
    detail !== null &&
    "error_list" in detail &&
    Array.isArray((detail as { error_list: unknown }).error_list)
  );
}

export function EquipmentManagementPage() {
  const [equipmentList, setEquipmentList] = useState<EquipmentResponse[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>({ type: "list" });
  const [form, setForm] = useState<EquipmentFormState>(EMPTY_FORM);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadEquipmentList = useCallback(async (): Promise<void> => {
    setLoadError(null);
    try {
      const list = await apiGet<EquipmentResponse[]>("/equipment?include_inactive=true");
      setEquipmentList(list);
    } catch (error) {
      setLoadError(toErrorMessage(error, "備品一覧の取得に失敗しました。"));
    }
  }, []);

  useEffect(() => {
    void loadEquipmentList();
  }, [loadEquipmentList]);

  function openCreatePanel(): void {
    setForm(EMPTY_FORM);
    setActionError(null);
    setPanel({ type: "create" });
  }

  function openEditPanel(equipment: EquipmentResponse): void {
    setForm({
      assetNumber: equipment.asset_number,
      name: equipment.name,
      category: equipment.category,
      description: equipment.description,
      location: equipment.location,
    });
    setActionError(null);
    setPanel({ type: "edit", equipment });
  }

  function openBulkImportPanel(): void {
    setActionError(null);
    setPanel({ type: "bulk-import" });
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
      await apiPost("/equipment", {
        asset_number: form.assetNumber,
        name: form.name,
        category: form.category,
        description: form.description,
        location: form.location,
      });
      await loadEquipmentList();
      closePanel();
    } catch (error) {
      setActionError(toErrorMessage(error, "備品登録に失敗しました。"));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleEditSubmit(
    event: FormEvent<HTMLFormElement>,
    equipmentId: number,
  ): Promise<void> {
    event.preventDefault();
    setActionError(null);
    setIsSubmitting(true);
    try {
      await apiPut(`/equipment/${equipmentId}`, {
        asset_number: form.assetNumber,
        name: form.name,
        category: form.category,
        description: form.description,
        location: form.location,
      });
      await loadEquipmentList();
      closePanel();
    } catch (error) {
      setActionError(toErrorMessage(error, "備品編集に失敗しました。"));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleToggleActive(equipment: EquipmentResponse): Promise<void> {
    setActionError(null);
    const action = equipment.active_flag ? "deactivate" : "activate";
    try {
      await apiPatch(`/equipment/${equipment.equipment_id}/${action}`);
      await loadEquipmentList();
    } catch (error) {
      setActionError(toErrorMessage(error, "備品状態の更新に失敗しました。"));
    }
  }

  if (equipmentList === null) {
    if (loadError !== null) {
      return (
        <div>
          <ErrorMessage message={loadError} />
          <button type="button" onClick={() => void loadEquipmentList()}>
            再試行
          </button>
        </div>
      );
    }
    return <LoadingIndicator />;
  }

  return (
    <div>
      <h1>備品管理</h1>
      {loadError !== null && <ErrorMessage message={loadError} />}

      {panel.type === "list" && (
        <>
          <button type="button" onClick={openCreatePanel}>
            新規登録
          </button>
          <button type="button" onClick={openBulkImportPanel}>
            CSV一括登録
          </button>
          <table>
            <thead>
              <tr>
                <th>資産番号</th>
                <th>備品名</th>
                <th>分類</th>
                <th>保管場所</th>
                <th>貸出状況</th>
                <th>状態</th>
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
                  <td>{equipment.active_flag ? "有効" : "無効"}</td>
                  <td>
                    <button type="button" onClick={() => openEditPanel(equipment)}>
                      編集
                    </button>
                    <button type="button" onClick={() => void handleToggleActive(equipment)}>
                      {equipment.active_flag ? "無効化" : "再有効化"}
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
          <h2>備品新規登録</h2>
          {actionError !== null && <ErrorMessage message={actionError} />}
          <EquipmentFormFields form={form} onChange={setForm} />
          <button type="submit" disabled={isSubmitting}>
            登録
          </button>
          <button type="button" onClick={closePanel}>
            キャンセル
          </button>
        </form>
      )}

      {panel.type === "edit" && (
        <form onSubmit={(event) => void handleEditSubmit(event, panel.equipment.equipment_id)}>
          <h2>備品編集（{panel.equipment.asset_number}）</h2>
          {actionError !== null && <ErrorMessage message={actionError} />}
          <EquipmentFormFields form={form} onChange={setForm} />
          <button type="submit" disabled={isSubmitting}>
            保存
          </button>
          <button type="button" onClick={closePanel}>
            キャンセル
          </button>
        </form>
      )}

      {panel.type === "bulk-import" && (
        <EquipmentBulkImportPanel onClose={closePanel} onImported={() => void loadEquipmentList()} />
      )}
    </div>
  );
}

function EquipmentFormFields({
  form,
  onChange,
}: {
  form: EquipmentFormState;
  onChange: (form: EquipmentFormState) => void;
}) {
  return (
    <>
      <label>
        資産番号
        <input
          type="text"
          value={form.assetNumber}
          onChange={(event) => onChange({ ...form, assetNumber: event.target.value })}
          minLength={1}
          maxLength={32}
          pattern="^[A-Za-z0-9-]+$"
          required
        />
      </label>
      <label>
        備品名
        <input
          type="text"
          value={form.name}
          onChange={(event) => onChange({ ...form, name: event.target.value })}
          minLength={1}
          maxLength={100}
          required
        />
      </label>
      <label>
        分類
        <input
          type="text"
          value={form.category}
          onChange={(event) => onChange({ ...form, category: event.target.value })}
          minLength={1}
          maxLength={50}
          required
        />
      </label>
      <label>
        説明
        <input
          type="text"
          value={form.description}
          onChange={(event) => onChange({ ...form, description: event.target.value })}
          maxLength={500}
        />
      </label>
      <label>
        保管場所
        <input
          type="text"
          value={form.location}
          onChange={(event) => onChange({ ...form, location: event.target.value })}
          maxLength={100}
        />
      </label>
    </>
  );
}

function EquipmentBulkImportPanel({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [errorList, setErrorList] = useState<EquipmentBulkImportErrorResponse["error_list"] | null>(
    null,
  );
  const [result, setResult] = useState<EquipmentBulkImportResponse | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (file === null) {
      return;
    }
    setActionError(null);
    setErrorList(null);
    setResult(null);
    setIsSubmitting(true);
    try {
      const response = await postFormData<EquipmentBulkImportResponse>(
        "/equipment/bulk-import",
        "file",
        file,
      );
      setResult(response);
      onImported();
    } catch (error) {
      if (error instanceof ApiError && isBulkImportErrorResponse(error.detail)) {
        setErrorList(error.detail.error_list);
      } else {
        setActionError(toErrorMessage(error, "CSV一括登録に失敗しました。"));
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div>
      <h2>CSV一括登録</h2>
      <p>
        UTF-8形式、ヘッダー行あり、列は資産番号・備品名・分類・説明・保管場所の順のCSVファイルを選択してください（最大5MB・最大1,000行）。
      </p>
      {actionError !== null && <ErrorMessage message={actionError} />}
      {errorList !== null && (
        <div role="alert">
          <p>以下のエラーがあったため、1件も登録されませんでした。</p>
          <ul>
            {errorList.map((error, index) => (
              <li key={index}>
                {error.row_number !== null ? `${error.row_number}行目: ` : ""}
                {error.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {result !== null && <p role="status">{result.registered_count}件の備品を登録しました。</p>}
      <form onSubmit={(event) => void handleSubmit(event)}>
        <label>
          CSVファイル
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            required
          />
        </label>
        <button type="submit" disabled={isSubmitting || file === null}>
          登録
        </button>
        <button type="button" onClick={onClose}>
          閉じる
        </button>
      </form>
    </div>
  );
}
