| 項目 | 内容 |
|---|---|
| HTTPメソッド | GET |
| エンドポイント | /loan-requests/export |
| 作成日 | 2026-10-12 |
| 最終更新日 | 2026-10-12 |

| 項番 | テスト項目 | 前提条件 | 入力値 | 想定結果 | エビデンス | 担当者 | 実施日 | 実施結果 | 再鑑者 | 再鑑日 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 正常系 - 条件を指定せず、全履歴をCSV形式（UTF-8、BOM付き）で出力できること | ・コンテナ起動済み<br>・初期管理者（admin）がパスワード変更済み、ログイン済み、アクセストークン取得済み<br>・貸出申請を1件以上登録済み | GET /loan-requests/export<br>Authorization: Bearer &lt;adminのtoken&gt; | HTTP 200<br>Content-Type: text/csv<br>先頭がUTF-8 BOM（﻿）で始まり、1行目がヘッダー（loan_request_id,equipment_id,...）、以降に登録済みの貸出申請がそれぞれ1行ずつ出力されること | | | | | | |
| 2 | 正常系 - 開始日範囲（start_date_from・start_date_to）を指定して絞り込めること | ・コンテナ起動済み<br>・初期管理者（admin）がパスワード変更済み、ログイン済み、アクセストークン取得済み<br>・指定する範囲内の開始日を持つ貸出申請1件・範囲外の開始日を持つ貸出申請1件を登録済み | GET /loan-requests/export?start_date_from=&lt;範囲内の日付&gt;&amp;start_date_to=&lt;範囲内の日付&gt;<br>Authorization: Bearer &lt;adminのtoken&gt; | HTTP 200<br>範囲内の開始日を持つ貸出申請のみが出力され、範囲外の開始日を持つ貸出申請は出力されないこと | | | | | | |
| 3 | 正常系 - 備品ID（equipment_id）を指定して絞り込めること | ・コンテナ起動済み<br>・初期管理者（admin）がパスワード変更済み、ログイン済み、アクセストークン取得済み<br>・指定する備品に対する貸出申請1件・異なる備品に対する貸出申請1件を登録済み | GET /loan-requests/export?equipment_id=&lt;備品ID&gt;<br>Authorization: Bearer &lt;adminのtoken&gt; | HTTP 200<br>指定した備品IDの貸出申請のみが出力され、異なる備品IDの貸出申請は出力されないこと | | | | | | |
| 4 | 正常系 - 申請者ID（applicant_user_id）を指定して絞り込めること | ・コンテナ起動済み<br>・初期管理者（admin）がパスワード変更済み、ログイン済み、アクセストークン取得済み<br>・指定する申請者による貸出申請1件・異なる申請者による貸出申請1件を登録済み | GET /loan-requests/export?applicant_user_id=&lt;申請者の内部ID&gt;<br>Authorization: Bearer &lt;adminのtoken&gt; | HTTP 200<br>指定した申請者IDの貸出申請のみが出力され、異なる申請者IDの貸出申請は出力されないこと | | | | | | |
| 5 | 正常系 - 条件に該当する履歴が0件の場合、ヘッダー行のみのCSVが返却されること | ・コンテナ起動済み<br>・初期管理者（admin）がパスワード変更済み、ログイン済み、アクセストークン取得済み | GET /loan-requests/export?equipment_id=999999<br>Authorization: Bearer &lt;adminのtoken&gt; | HTTP 200<br>ヘッダー行のみ（データ行が0件）のCSVが返却されること | | | | | | |
| 6 | 正常系 - 数式インジェクション対策：目的（purpose）が「=」で始まる場合、シングルクォートが付与されること | ・コンテナ起動済み<br>・初期管理者（admin）がパスワード変更済み、ログイン済み、アクセストークン取得済み<br>・目的が"=SUM(A1:A10)"の貸出申請を登録済み | GET /loan-requests/export<br>Authorization: Bearer &lt;adminのtoken&gt; | HTTP 200<br>対象行の目的列が"'=SUM(A1:A10)"（先頭にシングルクォート付与）として出力されること | | | | | | |
| 7 | 異常系 - 管理者権限のないユーザー（一般ユーザー）が呼び出した場合 | ・コンテナ起動済み<br>・一般ユーザーがパスワード変更済み、ログイン済み、アクセストークン取得済み | GET /loan-requests/export<br>Authorization: Bearer &lt;一般ユーザーのtoken&gt; | HTTP 403<br>{"detail": "この操作には管理者権限が必要です。"} | | | | | | |
| 8 | 異常系 - Authorizationヘッダーを指定せずに呼び出した場合 | ・コンテナ起動済み | GET /loan-requests/export（Authorizationヘッダーなし） | HTTP 401 | | | | | | |
| 9 | 異常系 - 初回パスワード変更が完了していない管理者が呼び出した場合 | ・コンテナ起動済み<br>・管理者ロールのユーザーを登録済み（初回パスワード変更未完了）、ログイン済み、アクセストークン取得済み | GET /loan-requests/export<br>Authorization: Bearer &lt;token&gt; | HTTP 403<br>{"detail": "初回パスワード変更が完了していません。パスワードを変更してください。"} | | | | | | |
| 10 | 異常系 - start_date_fromの形式が不正な場合 | ・コンテナ起動済み<br>・初期管理者（admin）がパスワード変更済み、ログイン済み、アクセストークン取得済み | GET /loan-requests/export?start_date_from=invalid-date<br>Authorization: Bearer &lt;adminのtoken&gt; | HTTP 422 | | | | | | |
