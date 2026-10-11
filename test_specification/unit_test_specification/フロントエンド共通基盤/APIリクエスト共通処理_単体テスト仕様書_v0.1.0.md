| 項目 | 内容 |
|---|---|
| ファイル名 | client.ts |
| クラス名 | - |
| メソッド名 | request（apiGet・apiPost・postForm経由で検証） |
| 作成日 | 2026-10-11 |
| 最終更新日 | 2026-10-11 |

| 項番 | 大項目 | 中項目 | 小項目 | 詳細 | 観点 | 対応設計書 | 対応箇所 | テスト内容 | 想定結果 | エビデンス | 担当者 | 実施日 | 実施結果 | 確認者 | 確認日 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 正常系 | 認証ヘッダー付与 | トークン設定済み | `setAccessToken`で設定したトークンが`Authorization`ヘッダーに付与されること | 正常性 | - | client.ts: request | `setAccessToken("token1")`を呼んだ後、`apiGet`を呼び出す（`fetch`をモック） | `fetch`の呼び出し引数に`Authorization: "Bearer token1"`ヘッダーが含まれること | | | | | | |
| 2 | 正常系 | 認証ヘッダー付与 | トークン未設定 | トークンが未設定の場合は`Authorization`ヘッダーが付与されないこと | 正常性 | - | client.ts: request | `setAccessToken(null)`の状態で`apiGet`を呼び出す | `fetch`の呼び出し引数に`Authorization`ヘッダーが含まれないこと | | | | | | |
| 3 | 異常系 | 認証エラー処理 | 401応答 | レスポンスが401の場合に401エラー時共通処理が呼ばれること | 正常性 | - | client.ts: request | `fetch`が`status: 401`を返すようモックし、`setUnauthorizedHandler`でハンドラを登録した状態で`apiGet`を呼び出す | 登録したハンドラが呼ばれること | | | | | | |
| 4 | 正常系 | 認証エラー処理 | 200応答 | レスポンスが401以外の場合は401エラー時共通処理が呼ばれないこと | 正常性 | - | client.ts: request | `fetch`が`status: 200`を返すようモックし、ハンドラを登録した状態で`apiGet`を呼び出す | 登録したハンドラが呼ばれないこと | | | | | | |
| 5 | 異常系 | エラー処理 | detailが文字列 | レスポンスが2xx以外かつ`detail`が文字列の場合、`ApiError`の`message`が`detail`になること | 正常性 | - | client.ts: request | `fetch`が`status: 400`、JSONボディ`{detail: "不正な入力です"}`を返すようモックして`apiGet`を呼び出す | `ApiError`がthrowされ、`status`が`400`、`message`が`"不正な入力です"`であること | | | | | | |
| 6 | 異常系 | エラー処理 | detailが非文字列 | `detail`が文字列以外（検証エラー配列等）の場合、`message`が`statusText`になり`detail`に生値が設定されること | 正常性 | - | client.ts: request | `fetch`が`status: 422`、`statusText: "Unprocessable Entity"`、JSONボディ`{detail: [...]}`を返すようモックして`apiGet`を呼び出す | `ApiError`の`message`が`"Unprocessable Entity"`、`detail`がそのまま配列であること | | | | | | |
| 7 | 異常系 | エラー処理 | レスポンスボディなし | レスポンスのJSON解析に失敗する場合も`statusText`で`ApiError`が発生すること | 正常性 | - | client.ts: request | `fetch`が`status: 500`で`response.json()`が例外を発生する応答を返すようモックして`apiGet`を呼び出す | `ApiError`の`message`が`statusText`であること | | | | | | |
| 8 | 正常系 | レスポンス処理 | 204応答 | ステータス204の場合は`undefined`を返すこと | 正常性 | - | client.ts: request | `fetch`が`status: 204`を返すようモックして`apiGet`を呼び出す | 戻り値が`undefined`であること | | | | | | |
| 9 | 正常系 | レスポンス処理 | 200応答 | ステータス200の場合はレスポンスボディをJSONとして返すこと | 正常性 | - | client.ts: request | `fetch`が`status: 200`・JSONボディを返すようモックして`apiGet`を呼び出す | 戻り値がJSONパース結果と一致すること | | | | | | |
| 10 | 正常系 | リクエストボディ | POSTでbody指定 | `apiPost`にbodyを渡した場合、JSON文字列化され`Content-Type`ヘッダーが設定されること | 正常性 | - | client.ts: request | `apiPost("/path", {a: 1})`を呼び出す | `fetch`の呼び出しが`method: "POST"`、`body: '{"a":1}'`、`Content-Type: "application/json"`であること | | | | | | |
| 11 | 正常系 | リクエストボディ | POSTでbody省略 | `apiPost`でbodyを省略した場合、bodyも`Content-Type`も設定されないこと | 正常性 | - | client.ts: request | `apiPost("/path")`を呼び出す | `fetch`の呼び出し引数に`body`・`Content-Type`が含まれないこと | | | | | | |
| 12 | 正常系 | フォームエンコード | postForm | フォーム項目が`application/x-www-form-urlencoded`形式に変換されること | 正常性 | - | client.ts: postForm | `postForm("/token", {username: "u1", password: "p1"})`を呼び出す | `fetch`のbodyが`"username=u1&password=p1"`相当の`URLSearchParams`であること | | | | | | |
