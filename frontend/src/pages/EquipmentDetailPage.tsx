/**
 * 備品詳細画面
 *
 * 【概要】
 * 指定した備品の詳細情報、予約状況（承認済み・貸出中の期間一覧）の表示、および貸出申請（F05）を行う画面
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { apiGet, apiPost, ApiError } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingIndicator } from "../components/LoadingIndicator";
import type { EquipmentResponse, LoanRequestCreateRequest, ReservationResponse } from "../types/common";

function toErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

interface LoanRequestFormState {
  startDate: string;
  dueDate: string;
  purpose: string;
}

const EMPTY_LOAN_REQUEST_FORM: LoanRequestFormState = {
  startDate: "",
  dueDate: "",
  purpose: "",
};

function getTodayDateString(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function EquipmentReservationTable({
  reservationList,
}: {
  reservationList: ReservationResponse[];
}) {
  const showApplicantColumn = reservationList.some(
    (reservation) => reservation.applicant_name != null,
  );

  return (
    <table>
      <thead>
        <tr>
          <th>開始日</th>
          <th>返却予定日</th>
          <th>状態</th>
          {showApplicantColumn && <th>申請者</th>}
        </tr>
      </thead>
      <tbody>
        {reservationList.map((reservation) => (
          <tr key={reservation.loan_request_id}>
            <td>{reservation.start_date}</td>
            <td>{reservation.due_date}</td>
            <td>{reservation.status}</td>
            {showApplicantColumn && <td>{reservation.applicant_name}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function EquipmentDetailPage() {
  const { equipmentId } = useParams<{ equipmentId: string }>();
  const [equipment, setEquipment] = useState<EquipmentResponse | null>(null);
  const [reservationList, setReservationList] = useState<ReservationResponse[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loanRequestForm, setLoanRequestForm] = useState<LoanRequestFormState>(EMPTY_LOAN_REQUEST_FORM);
  const [isSubmittingLoanRequest, setIsSubmittingLoanRequest] = useState(false);
  const [loanRequestActionError, setLoanRequestActionError] = useState<string | null>(null);
  const [loanRequestSuccessMessage, setLoanRequestSuccessMessage] = useState<string | null>(null);

  const loadEquipmentDetail = useCallback(async (): Promise<void> => {
    setLoadError(null);
    try {
      const [equipmentResponse, reservationResponseList] = await Promise.all([
        apiGet<EquipmentResponse>(`/equipment/${equipmentId}`),
        apiGet<ReservationResponse[]>(`/equipment/${equipmentId}/reservations`),
      ]);
      setEquipment(equipmentResponse);
      setReservationList(reservationResponseList);
    } catch (error) {
      setLoadError(toErrorMessage(error, "備品詳細の取得に失敗しました。"));
    }
  }, [equipmentId]);

  useEffect(() => {
    void loadEquipmentDetail();
  }, [loadEquipmentDetail]);

  async function handleLoanRequestSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (equipmentId === undefined) {
      return;
    }
    setLoanRequestActionError(null);
    setLoanRequestSuccessMessage(null);
    setIsSubmittingLoanRequest(true);
    try {
      const loanRequestCreateRequest: LoanRequestCreateRequest = {
        equipment_id: Number(equipmentId),
        start_date: loanRequestForm.startDate,
        due_date: loanRequestForm.dueDate,
        purpose: loanRequestForm.purpose,
      };
      await apiPost("/loan-requests", loanRequestCreateRequest);
      setLoanRequestForm(EMPTY_LOAN_REQUEST_FORM);
      setLoanRequestSuccessMessage("貸出を申請しました。申請の状況は「自分の申請一覧」から確認できます。");
      await loadEquipmentDetail();
    } catch (error) {
      setLoanRequestActionError(toErrorMessage(error, "貸出申請に失敗しました。"));
    } finally {
      setIsSubmittingLoanRequest(false);
    }
  }

  if (loadError !== null) {
    return (
      <div>
        <ErrorMessage message={loadError} />
        <button type="button" onClick={() => void loadEquipmentDetail()}>
          再試行
        </button>
      </div>
    );
  }

  if (equipment === null || reservationList === null) {
    return <LoadingIndicator />;
  }

  return (
    <div>
      <h1>備品詳細</h1>
      <dl>
        <dt>資産番号</dt>
        <dd>{equipment.asset_number}</dd>
        <dt>備品名</dt>
        <dd>{equipment.name}</dd>
        <dt>分類</dt>
        <dd>{equipment.category}</dd>
        <dt>説明</dt>
        <dd>{equipment.description}</dd>
        <dt>保管場所</dt>
        <dd>{equipment.location}</dd>
        <dt>貸出状況</dt>
        <dd>{equipment.loan_status}</dd>
        {equipment.due_date !== null && (
          <>
            <dt>返却予定日</dt>
            <dd>{equipment.due_date}</dd>
          </>
        )}
      </dl>

      <h2>予約状況</h2>
      {reservationList.length === 0 ? (
        <p>予約はありません。</p>
      ) : (
        <EquipmentReservationTable reservationList={reservationList} />
      )}

      <h2>貸出申請</h2>
      {equipment.active_flag ? (
        <form onSubmit={(event) => void handleLoanRequestSubmit(event)}>
          {loanRequestActionError !== null && <ErrorMessage message={loanRequestActionError} />}
          {loanRequestSuccessMessage !== null && <p role="status">{loanRequestSuccessMessage}</p>}
          <label>
            開始日
            <input
              type="date"
              value={loanRequestForm.startDate}
              onChange={(event) =>
                setLoanRequestForm({ ...loanRequestForm, startDate: event.target.value })
              }
              min={getTodayDateString()}
              required
            />
          </label>
          <label>
            返却予定日
            <input
              type="date"
              value={loanRequestForm.dueDate}
              onChange={(event) =>
                setLoanRequestForm({ ...loanRequestForm, dueDate: event.target.value })
              }
              min={loanRequestForm.startDate || getTodayDateString()}
              required
            />
          </label>
          <label>
            用途
            <input
              type="text"
              value={loanRequestForm.purpose}
              onChange={(event) =>
                setLoanRequestForm({ ...loanRequestForm, purpose: event.target.value })
              }
              minLength={1}
              maxLength={200}
              required
            />
          </label>
          <button type="submit" disabled={isSubmittingLoanRequest}>
            申請
          </button>
        </form>
      ) : (
        <p>この備品は現在無効化されているため、貸出を申請できません。</p>
      )}
    </div>
  );
}
