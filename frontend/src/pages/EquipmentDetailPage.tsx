/**
 * 備品詳細画面
 *
 * 【概要】
 * 指定した備品の詳細情報と、予約状況（承認済み・貸出中の期間一覧）を表示する画面
 *
 * 【備考】
 * 貸出申請（F05）は、本画面内に別バックログで追加する予定であり、本画面では実装しない。
 */

import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiGet, ApiError } from "../api/client";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingIndicator } from "../components/LoadingIndicator";
import type { EquipmentResponse, ReservationResponse } from "../types/common";

function toErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
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
    </div>
  );
}
