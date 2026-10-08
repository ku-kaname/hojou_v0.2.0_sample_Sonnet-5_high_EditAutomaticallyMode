/**
 * APIクライアント基盤
 *
 * 【概要】
 * バックエンドAPIへの共通リクエスト処理（ベースURL・認証トークン付与・401エラー時の共通処理）を提供する
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

let accessToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

/**
 * APIエラー
 *
 * 【概要】
 * APIレスポンスが異常（2xx以外）であった場合に発生させる例外
 *
 * 【属性】
 * - status (number): HTTPステータスコード
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// ====================================================================================================
// 認証トークン・401エラー時共通処理の登録
// - setAccessToken : 認証トークン設定
// - setUnauthorizedHandler : 401エラー時共通処理登録
// ====================================================================================================

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function setUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler;
}

// ====================================================================================================
// APIリクエスト
// - apiGet / apiPost / apiPatch / apiPut / apiDelete : JSON形式でのリクエスト
// - postForm : フォームエンコード形式でのリクエスト（OAuth2のトークン発行等）
// ====================================================================================================

/**
 * リクエスト共通処理
 *
 * 【処理概要】
 * - ベースURLの付与、認証トークン（Bearer）の付与を行い、バックエンドAPIへリクエストする
 * - レスポンスが401の場合は401エラー時共通処理を呼び出す
 * - レスポンスが2xx以外の場合はApiErrorを発生させる
 *
 * 【パラメータ】
 * - path (string) : APIパス（例：`/health-check`） (必須)
 * - init (RequestInit) : fetchオプション (必須)
 *
 * 【戻り値】
 * - response (T) : レスポンスボディ（JSON）
 *
 * 【例外処理】
 * - ApiError : レスポンスが2xx以外の場合
 *
 * 【処理フロー】
 * 1. リクエストヘッダーの設定
 * 2. リクエストの送信
 * 3. 401エラー時共通処理の呼び出し
 * 4. 例外処理
 * 5. 戻り値を返却
 */
async function request<T>(path: string, init: RequestInit): Promise<T> {
  // 1. リクエストヘッダーの設定
  const headers = new Headers(init.headers);
  if (accessToken !== null) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  // 2. リクエストの送信
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  // 3. 401エラー時共通処理の呼び出し
  if (response.status === 401) {
    unauthorizedHandler?.();
  }

  // 4. 例外処理：レスポンスが2xx以外
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "string"
        ? body.detail
        : response.statusText;
    throw new ApiError(response.status, detail);
  }

  // 5. 戻り値を返却
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

/**
 * フォームエンコードリクエスト
 *
 * 【処理概要】
 * - リクエストボディを`application/x-www-form-urlencoded`形式に変換してリクエストする（OAuth2PasswordRequestFormを受け取るエンドポイント向け）
 *
 * 【パラメータ】
 * - path (string) : APIパス (必須)
 * - fields (Record<string, string>) : フォーム項目 (必須)
 *
 * 【戻り値】
 * - response (T) : レスポンスボディ（JSON）
 *
 * 【例外処理】
 * - ApiError : レスポンスが2xx以外の場合
 *
 * 【処理フロー】
 * 1. フォームデータへの変換
 * 2. リクエストの送信
 */
export function postForm<T>(path: string, fields: Record<string, string>): Promise<T> {
  // 1. フォームデータへの変換
  const formBody = new URLSearchParams(fields);

  // 2. リクエストの送信
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: formBody,
  });
}
