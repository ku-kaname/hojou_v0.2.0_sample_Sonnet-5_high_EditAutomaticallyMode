import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  apiGet,
  apiGetBlob,
  apiPost,
  postForm,
  setAccessToken,
  setUnauthorizedHandler,
} from "../../api/client";

// ==================================================
// APIリクエスト共通処理
// テスト対象ファイル：client.ts
// テスト対象クラス：-
// テスト対象メソッド：request（apiGet・apiPost・postForm経由で検証）
// テスト仕様書：test_specification/unit_test_specification/フロントエンド共通基盤/APIリクエスト共通処理_単体テスト仕様書.md
// ==================================================

// レスポンスのうちrequestが参照する項目のみを持つ簡易モックを作成する
function createMockResponse(options: {
  status: number;
  statusText?: string;
  jsonBody?: unknown;
  jsonRejects?: boolean;
}) {
  return {
    status: options.status,
    ok: options.status >= 200 && options.status < 300,
    statusText: options.statusText ?? "",
    json: () =>
      options.jsonRejects
        ? Promise.reject(new Error("invalid json"))
        : Promise.resolve(options.jsonBody),
  };
}

describe("request（apiGet/apiPost/postForm経由）", () => {
  beforeEach(() => {
    setAccessToken(null);
    setUnauthorizedHandler(() => {});
    vi.stubGlobal("fetch", vi.fn());
  });

  // ========== 単体テストNo.1 ==========
  // setAccessTokenで設定したトークンがAuthorizationヘッダーに付与されること
  it("test_request_001_sets_authorization_header_when_token_present", async () => {
    setAccessToken("token1");
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ status: 200, jsonBody: {} }) as Response,
    );

    await apiGet("/health-check");

    const requestInit = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const headers = requestInit.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer token1");
  });

  // ========== 単体テストNo.2 ==========
  // トークンが未設定の場合はAuthorizationヘッダーが付与されないこと
  it("test_request_002_omits_authorization_header_when_token_absent", async () => {
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ status: 200, jsonBody: {} }) as Response,
    );

    await apiGet("/health-check");

    const requestInit = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const headers = requestInit.headers as Headers;
    expect(headers.has("Authorization")).toBe(false);
  });

  // ========== 単体テストNo.3 ==========
  // レスポンスが401の場合に401エラー時共通処理が呼ばれること
  it("test_request_003_calls_unauthorized_handler_on_401", async () => {
    const unauthorizedHandler = vi.fn();
    setUnauthorizedHandler(unauthorizedHandler);
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ status: 401, jsonBody: {} }) as Response,
    );

    await expect(apiGet("/users/me")).rejects.toThrow();

    expect(unauthorizedHandler).toHaveBeenCalledOnce();
  });

  // ========== 単体テストNo.4 ==========
  // レスポンスが401以外の場合は401エラー時共通処理が呼ばれないこと
  it("test_request_004_does_not_call_unauthorized_handler_on_200", async () => {
    const unauthorizedHandler = vi.fn();
    setUnauthorizedHandler(unauthorizedHandler);
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ status: 200, jsonBody: {} }) as Response,
    );

    await apiGet("/users/me");

    expect(unauthorizedHandler).not.toHaveBeenCalled();
  });

  // ========== 単体テストNo.5 ==========
  // レスポンスが2xx以外かつdetailが文字列の場合、ApiErrorのmessageがdetailになること
  it("test_request_005_error_message_uses_string_detail", async () => {
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ status: 400, jsonBody: { detail: "不正な入力です" } }) as Response,
    );

    const error = await apiGet("/users/me").catch((caught: unknown) => caught);

    expect(error).toMatchObject({ status: 400, message: "不正な入力です" });
  });

  // ========== 単体テストNo.6 ==========
  // detailが文字列以外の場合、messageがstatusTextになりdetailに生値が設定されること
  it("test_request_006_error_message_falls_back_to_status_text_for_non_string_detail", async () => {
    const validationErrors = [{ field: "name", message: "必須です" }];
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({
        status: 422,
        statusText: "Unprocessable Entity",
        jsonBody: { detail: validationErrors },
      }) as Response,
    );

    const error = await apiGet("/users/me").catch((caught: unknown) => caught);

    expect(error).toMatchObject({ message: "Unprocessable Entity", detail: validationErrors });
  });

  // ========== 単体テストNo.7 ==========
  // レスポンスのJSON解析に失敗する場合もstatusTextでApiErrorが発生すること
  it("test_request_007_error_message_falls_back_to_status_text_when_body_unreadable", async () => {
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({
        status: 500,
        statusText: "Internal Server Error",
        jsonRejects: true,
      }) as Response,
    );

    const error = await apiGet("/users/me").catch((caught: unknown) => caught);

    expect(error).toMatchObject({ message: "Internal Server Error" });
  });

  // ========== 単体テストNo.8 ==========
  // ステータス204の場合はundefinedを返すこと
  it("test_request_008_returns_undefined_on_204", async () => {
    vi.mocked(fetch).mockResolvedValue(createMockResponse({ status: 204 }) as Response);

    const result = await apiGet("/logout");

    expect(result).toBeUndefined();
  });

  // ========== 単体テストNo.9 ==========
  // ステータス200の場合はレスポンスボディをJSONとして返すこと
  it("test_request_009_returns_json_body_on_200", async () => {
    const responseBody = { user_id: "u001" };
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ status: 200, jsonBody: responseBody }) as Response,
    );

    const result = await apiGet("/users/me");

    expect(result).toEqual(responseBody);
  });

  // ========== 単体テストNo.10 ==========
  // apiPostにbodyを渡した場合、JSON文字列化されContent-Typeヘッダーが設定されること
  it("test_request_010_post_with_body_sets_json_content_type", async () => {
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ status: 200, jsonBody: {} }) as Response,
    );

    await apiPost("/path", { a: 1 });

    const requestInit = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(requestInit.method).toBe("POST");
    expect(requestInit.body).toBe('{"a":1}');
    expect((requestInit.headers as Headers).get("Content-Type")).toBe("application/json");
  });

  // ========== 単体テストNo.11 ==========
  // apiPostでbodyを省略した場合、bodyもContent-Typeも設定されないこと
  it("test_request_011_post_without_body_omits_body_and_content_type", async () => {
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ status: 200, jsonBody: {} }) as Response,
    );

    await apiPost("/path");

    const requestInit = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(requestInit.body).toBeUndefined();
    expect((requestInit.headers as Headers).get("Content-Type")).toBeNull();
  });

  // ========== 単体テストNo.12 ==========
  // フォーム項目がapplication/x-www-form-urlencoded形式に変換されること
  it("test_request_012_post_form_encodes_fields", async () => {
    vi.mocked(fetch).mockResolvedValue(
      createMockResponse({ status: 200, jsonBody: {} }) as Response,
    );

    await postForm("/token", { username: "u1", password: "p1" });

    const requestInit = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect((requestInit.body as URLSearchParams).toString()).toBe("username=u1&password=p1");
  });
});

// ==================================================
// ファイルダウンロードリクエスト
// テスト対象ファイル：client.ts
// テスト対象クラス：-
// テスト対象メソッド：apiGetBlob
// テスト仕様書：test_specification/unit_test_specification/フロントエンド共通基盤/ファイルダウンロードリクエスト_単体テスト仕様書.md
// ==================================================

describe("apiGetBlob", () => {
  beforeEach(() => {
    setAccessToken(null);
    vi.stubGlobal("fetch", vi.fn());
  });

  // ========== 単体テストNo.1 ==========
  // Content-Dispositionヘッダーからファイル名を抽出すること
  it("test_apiGetBlob_001_extracts_filename_from_content_disposition", async () => {
    vi.mocked(fetch).mockResolvedValue({
      status: 200,
      ok: true,
      headers: {
        get: (name: string) =>
          name === "Content-Disposition" ? 'attachment; filename="export.csv"' : null,
      },
      blob: () => Promise.resolve(new Blob(["data"])),
    } as unknown as Response);

    const result = await apiGetBlob("/path", "fallback.csv");

    expect(result.fileName).toBe("export.csv");
  });

  // ========== 単体テストNo.2 ==========
  // ヘッダーが取得できない場合はフォールバックのファイル名を使用すること
  it("test_apiGetBlob_002_uses_fallback_filename_when_header_absent", async () => {
    vi.mocked(fetch).mockResolvedValue({
      status: 200,
      ok: true,
      headers: { get: () => null },
      blob: () => Promise.resolve(new Blob(["data"])),
    } as unknown as Response);

    const result = await apiGetBlob("/path", "fallback.csv");

    expect(result.fileName).toBe("fallback.csv");
  });

  // ========== 単体テストNo.3 ==========
  // レスポンスが2xx以外の場合にApiErrorが発生すること
  it("test_apiGetBlob_003_throws_api_error_on_non_2xx", async () => {
    vi.mocked(fetch).mockResolvedValue({
      status: 404,
      ok: false,
      statusText: "Not Found",
      headers: { get: () => null },
      json: () => Promise.resolve({}),
    } as unknown as Response);

    await expect(apiGetBlob("/path", "fallback.csv")).rejects.toThrow();
  });

  // ========== 単体テストNo.4 ==========
  // レスポンスボディがBlobとして返却されること
  it("test_apiGetBlob_004_returns_blob_body", async () => {
    const expectedBlob = new Blob(["data"]);
    vi.mocked(fetch).mockResolvedValue({
      status: 200,
      ok: true,
      headers: { get: () => null },
      blob: () => Promise.resolve(expectedBlob),
    } as unknown as Response);

    const result = await apiGetBlob("/path", "fallback.csv");

    expect(result.blob).toBe(expectedBlob);
  });
});
