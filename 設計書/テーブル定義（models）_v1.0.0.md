# テーブル定義

- **工程**: 設計工程
- **作成者**: Claude Sonnet 5
- **作成日**: 2026-10-08
- **最終更新日**: 2026-10-08

---

## USER

| 項目 | 内容 |
|---|---|
| テーブル論理名 | ユーザー情報 |
| テーブル物理名 | USER |

### 説明

社員アカウント（一般・管理者）を管理する。要件定義書/機能要件「扱うデータ」のユーザーに対応する。

| 論理名 | 物理名 | 型 | 必須 | 最小値 | 最大値 | 最小桁 | 最大桁 | 主キー | 外部キー | 制約 | インデックス | 備考 |
|---|---|---|:---:|---:|---:|---:|---:|:---:|---|---|---|---|
| 内部ID | id | INTEGER | ○ | - | - | - | - | ○ | - | - | - | 自動採番（グローバル連番） |
| ユーザーID | user_id | VARCHAR | ○ | - | - | 3 | 32 | - | - | uq_user_user_id | idx_user_user_id | 半角英数字と`_`・`-`のみ。無効化後も再利用不可（アプリ側で一意性を保証） |
| 氏名 | name | VARCHAR | ○ | - | - | 1 | 50 | - | - | - | - | - |
| 所属 | department | VARCHAR | - | - | - | 0 | 50 | - | - | - | - | 空文字許容 |
| パスワードハッシュ | hashed_password | VARCHAR | ○ | - | - | 1 | 255 | - | - | - | - | Argon2idハッシュ文字列。平文は保存しない |
| ロール | role | VARCHAR | ○ | - | - | - | - | - | - | ck_user_role（'一般','管理者'のいずれか） | - | 既定値："一般" |
| 有効フラグ | active_flag | BOOLEAN | ○ | - | - | - | - | - | - | - | - | 既定値：true（無効化＝論理削除） |
| 初回パスワード変更要否フラグ | password_change_required_flag | BOOLEAN | ○ | - | - | - | - | - | - | - | - | 既定値：true（登録時・初期化時） |
| トークン世代 | token_generation | INTEGER | ○ | 0 | - | - | - | - | - | - | - | 既定値：0。失効操作のたびに+1 |
| 連続認証失敗回数 | login_failure_count | INTEGER | ○ | 0 | - | - | - | - | - | - | - | 既定値：0。ログイン成功時・ロック解除時に0へ戻す |
| ロック解除日時 | locked_until | DATETIME | - | - | - | - | - | - | - | - | - | 空欄許容。連続失敗5回で現在時刻+15分を設定 |
| 作成日時 | created_at | DATETIME | ○ | - | - | - | - | - | - | - | - | サーバー時刻 |
| 更新日時 | updated_at | DATETIME | ○ | - | - | - | - | - | - | - | - | サーバー時刻。更新しない限り作成日時と同じ値 |

### 補足

- 最後の有効な管理者（`role`="管理者" かつ `active_flag`=true の最後の1件）を無効化・ロール変更することはできない（アプリ側のオーケストレーション層で検証する。DB制約では表現しない）。

---

## EQUIPMENT

| 項目 | 内容 |
|---|---|
| テーブル論理名 | 備品情報 |
| テーブル物理名 | EQUIPMENT |

### 説明

貸出対象の備品を個体単位で管理する。要件定義書/機能要件「扱うデータ」の備品に対応する。

| 論理名 | 物理名 | 型 | 必須 | 最小値 | 最大値 | 最小桁 | 最大桁 | 主キー | 外部キー | 制約 | インデックス | 備考 |
|---|---|---|:---:|---:|---:|---:|---:|:---:|---|---|---|---|
| 内部ID | id | INTEGER | ○ | - | - | - | - | ○ | - | - | - | 自動採番 |
| 資産番号 | asset_number | VARCHAR | ○ | - | - | 1 | 32 | - | - | uq_equipment_asset_number | idx_equipment_asset_number | 半角英数字と`-`のみ。重複登録不可 |
| 備品名 | name | VARCHAR | ○ | - | - | 1 | 100 | - | - | - | - | - |
| 分類 | category | VARCHAR | ○ | - | - | 1 | 50 | - | - | - | idx_equipment_category | 自由入力（分類マスタは設けない） |
| 説明 | description | VARCHAR | - | - | - | 0 | 500 | - | - | - | - | 空文字許容 |
| 保管場所 | location | VARCHAR | - | - | - | 0 | 100 | - | - | - | - | 空文字許容 |
| 有効フラグ | active_flag | BOOLEAN | ○ | - | - | - | - | - | - | - | idx_equipment_active_flag | 既定値：true（無効化＝論理削除） |
| 作成日時 | created_at | DATETIME | ○ | - | - | - | - | - | - | - | - | サーバー時刻 |
| 更新日時 | updated_at | DATETIME | ○ | - | - | - | - | - | - | - | - | サーバー時刻。更新しない限り作成日時と同じ値 |

### 補足

- なし

---

## LOAN_REQUEST

| 項目 | 内容 |
|---|---|
| テーブル論理名 | 貸出申請情報 |
| テーブル物理名 | LOAN_REQUEST |

### 説明

貸出の申請から返却までの一連の状態（貸出履歴を兼ねる）を管理する。要件定義書/機能要件「扱うデータ」の貸出申請に対応する。

| 論理名 | 物理名 | 型 | 必須 | 最小値 | 最大値 | 最小桁 | 最大桁 | 主キー | 外部キー | 制約 | インデックス | 備考 |
|---|---|---|:---:|---:|---:|---:|---:|:---:|---|---|---|---|
| 内部ID | id | INTEGER | ○ | - | - | - | - | ○ | - | - | - | 自動採番 |
| 備品（内部ID） | equipment_id | INTEGER | ○ | - | - | - | - | - | `foreign_key.constraint_name`: fk_loan_request_equipment_id<br>参照先: EQUIPMENT.id<br>ON UPDATE: CASCADE / ON DELETE: RESTRICT<br>カーディナリティ: 多:1 | - | idx_loan_request_equipment_id | 物理削除を行わない運用のためON DELETEはRESTRICT（発生しない想定） |
| 申請者（ユーザー内部ID） | applicant_user_id | INTEGER | ○ | - | - | - | - | - | `foreign_key.constraint_name`: fk_loan_request_applicant_user_id<br>参照先: USER.id<br>ON UPDATE: CASCADE / ON DELETE: RESTRICT<br>カーディナリティ: 多:1 | - | idx_loan_request_applicant_user_id | - |
| 開始日 | start_date | DATE | ○ | - | - | - | - | - | - | - | - | 申請時点で今日以降 |
| 返却予定日 | due_date | DATE | ○ | - | - | - | - | - | - | - | - | 開始日以降 |
| 用途 | purpose | VARCHAR | ○ | - | - | 1 | 200 | - | - | - | - | - |
| 状態 | status | VARCHAR | ○ | - | - | - | - | - | - | ck_loan_request_status（'申請中','承認済み','貸出中','返却済み','却下','取消'のいずれか） | idx_loan_request_status | 既定値："申請中" |
| 却下・取消理由 | reject_cancel_reason | VARCHAR | - | - | - | 0 | 200 | - | - | - | - | 却下・管理者取消時は必須（アプリ側で検証）。空欄許容 |
| 承認・却下した管理者（ユーザー内部ID） | approved_rejected_by_user_id | INTEGER | - | - | - | - | - | - | `foreign_key.constraint_name`: fk_loan_request_approved_rejected_by<br>参照先: USER.id<br>ON UPDATE: CASCADE / ON DELETE: RESTRICT<br>カーディナリティ: 多:1 | - | - | 承認・却下時は必須（アプリ側で検証）。空欄許容 |
| 貸出処理した管理者（ユーザー内部ID） | lent_by_user_id | INTEGER | - | - | - | - | - | - | `foreign_key.constraint_name`: fk_loan_request_lent_by<br>参照先: USER.id<br>ON UPDATE: CASCADE / ON DELETE: RESTRICT<br>カーディナリティ: 多:1 | - | - | 貸出時は必須（アプリ側で検証）。空欄許容 |
| 返却処理した管理者（ユーザー内部ID） | returned_by_user_id | INTEGER | - | - | - | - | - | - | `foreign_key.constraint_name`: fk_loan_request_returned_by<br>参照先: USER.id<br>ON UPDATE: CASCADE / ON DELETE: RESTRICT<br>カーディナリティ: 多:1 | - | - | 返却時は必須（アプリ側で検証）。空欄許容 |
| 取消した者（ユーザー内部ID） | cancelled_by_user_id | INTEGER | - | - | - | - | - | - | `foreign_key.constraint_name`: fk_loan_request_cancelled_by<br>参照先: USER.id<br>ON UPDATE: CASCADE / ON DELETE: RESTRICT<br>カーディナリティ: 多:1 | - | - | 取消時は必須（アプリ側で検証）。自動取消（ノーショー）時は空欄 |
| 申請日時 | requested_at | DATETIME | ○ | - | - | - | - | - | - | - | - | サーバー時刻 |
| 承認却下日時 | approved_rejected_at | DATETIME | - | - | - | - | - | - | - | - | - | 空欄許容 |
| 貸出日時 | lent_at | DATETIME | - | - | - | - | - | - | - | - | - | 空欄許容 |
| 返却日時 | returned_at | DATETIME | - | - | - | - | - | - | - | - | - | 空欄許容 |
| 取消日時 | cancelled_at | DATETIME | - | - | - | - | - | - | - | - | - | 空欄許容 |
| 返却時状態メモ | return_note | VARCHAR | - | - | - | 0 | 200 | - | - | - | - | 空欄許容 |

### 補足

- 同一備品について、状態が「承認済み」「貸出中」の申請は期間重複を許可しない（アプリ側のオーケストレーション層で検証する。DB制約では表現しない。要件定義書/機能要件「業務ルール」参照）。
- 本テーブルが貸出履歴を兼ねるため、物理削除・状態の後退（返却済み→貸出中等）は行わない。

---

## NOTIFICATION

| 項目 | 内容 |
|---|---|
| テーブル論理名 | 通知情報 |
| テーブル物理名 | NOTIFICATION |

### 説明

アプリ内通知（承認・却下・取消・新規申請・返却期限）を管理する。要件定義書/機能要件「扱うデータ」の通知に対応する。

| 論理名 | 物理名 | 型 | 必須 | 最小値 | 最大値 | 最小桁 | 最大桁 | 主キー | 外部キー | 制約 | インデックス | 備考 |
|---|---|---|:---:|---:|---:|---:|---:|:---:|---|---|---|---|
| 内部ID | id | INTEGER | ○ | - | - | - | - | ○ | - | - | - | 自動採番 |
| 宛先（ユーザー内部ID） | recipient_user_id | INTEGER | ○ | - | - | - | - | - | `foreign_key.constraint_name`: fk_notification_recipient_user_id<br>参照先: USER.id<br>ON UPDATE: CASCADE / ON DELETE: RESTRICT<br>カーディナリティ: 多:1 | - | idx_notification_recipient_user_id | - |
| 種別 | notification_type | VARCHAR | ○ | - | - | - | - | - | - | ck_notification_type（'承認','却下','取消','新規申請','返却期限'のいずれか） | - | - |
| 関連申請（内部ID） | loan_request_id | INTEGER | ○ | - | - | - | - | - | `foreign_key.constraint_name`: fk_notification_loan_request_id<br>参照先: LOAN_REQUEST.id<br>ON UPDATE: CASCADE / ON DELETE: RESTRICT<br>カーディナリティ: 多:1 | - | idx_notification_loan_request_id | - |
| 既読フラグ | read_flag | BOOLEAN | ○ | - | - | - | - | - | - | - | idx_notification_read_flag | 既定値：false（未読） |
| 作成日時 | created_at | DATETIME | ○ | - | - | - | - | - | - | - | - | サーバー時刻 |

### 補足

- 返却期限の通知（返却予定日前日・期限超過中）は、日次バッチ処理により対象の貸出申請1件・1日につき1件生成する（同日に重複して生成しない。アプリ側のオーケストレーション層で重複確認を行う）。
