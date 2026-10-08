/**
 * エラー表示
 *
 * 【概要】
 * API呼び出し等で発生したエラー内容を表示する共通表示部品
 */

export function ErrorMessage({ message }: { message: string }) {
  return <p role="alert">{message}</p>;
}
