# 備品貸出管理システム

社内の備品貸出を管理するWebアプリケーション。

## 構成

- `frontend/` : TypeScript / React / Vite によるフロントエンド
- `backend/` : Python / FastAPI によるバックエンド
- `docker-compose.yml` : DB（PostgreSQL）・バックエンド・フロントエンドの3コンテナ構成

技術スタックの詳細は `要件定義書/技術スタック_v1.0.0.md` を参照。

## セットアップ

1. `.env.example` をコピーして `.env` を作成し、値を環境に応じて設定する。

   ```
   cp .env.example .env
   ```

2. Docker Composeでコンテナを起動する。

   ```
   docker compose up --build
   ```

3. 起動後のアクセス先

   - フロントエンド : http://localhost
   - バックエンドAPI : http://localhost:8000
   - ヘルスチェック : http://localhost:8000/health-check

## 開発時の操作

### バックエンド（`backend/`）

- 依存インストール : `pip install -e ".[dev]"`
- Lint : `ruff check .`
- 型チェック : `mypy .`
- テスト : `pytest`
- マイグレーション適用 : `alembic upgrade head`

### フロントエンド（`frontend/`）

- 依存インストール : `npm install`
- 開発サーバー起動 : `npm run dev`
- Lint : `npm run lint`
- 型チェック : `npm run typecheck`
- テスト : `npm run test`

## 使用方法

### 初回ログイン

- 初回の管理者アカウントは、起動時に`.env`の`INITIAL_ADMIN_USER_ID`・`INITIAL_ADMIN_NAME`・`INITIAL_ADMIN_PASSWORD`で指定した値で自動作成される（自己登録の画面はない）。
- フロントエンド（`http://localhost`）のログイン画面で、上記のユーザーIDとパスワードでログインする。
- 初回ログイン後は、必要に応じてパスワード変更画面（ヘッダーから遷移）で自分のパスワードを変更する。
- 以降の社員アカウントは、管理者がユーザー管理画面（後述）で登録する。

### ロールと画面

ロールは「一般」「管理者」の2種類。管理者は一般利用者向けの画面もすべて利用できる。

| 画面 | 対応ファイル | 利用できるロール | できること |
|---|---|---|---|
| ログイン | `LoginPage.tsx` | 全員 | ユーザーID・パスワードでログイン |
| パスワード変更 | `ChangePasswordPage.tsx` | 全員 | 自分のパスワードを変更 |
| 備品一覧 | `EquipmentListPage.tsx` | 全員 | 備品を分類・キーワード・状態で検索し、現在の貸出状況を確認 |
| 備品詳細 | `EquipmentDetailPage.tsx` | 全員 | 備品ごとの承認済み・貸出中の期間（予約状況）を確認し、貸出を申請 |
| 自分の申請・貸出状況 | `LoanRequestMinePage.tsx` | 全員 | 自分の申請の状態・履歴を確認し、申請中・承認済みの申請を取り消す |
| ホーム（通知） | `HomePage.tsx` | 全員 | アプリ内通知（承認・却下・取消、返却期限）を確認（管理者は新規申請件数も表示） |
| 貸出申請の承認・却下・貸出処理 | `LoanRequestManagePage.tsx` | 管理者 | 申請中の申請を承認・却下し、承認済みの申請について貸出処理（備品を渡した記録）・返却処理・管理者取消を行う |
| 期限超過一覧 | `OverdueLoanRequestsPage.tsx` | 管理者 | 返却予定日を過ぎた貸出の一覧を確認 |
| 貸出履歴 | `LoanHistoryPage.tsx` | 管理者 | 全社員の貸出履歴を検索・閲覧し、CSV出力 |
| 備品管理 | `EquipmentManagementPage.tsx` | 管理者 | 備品の登録・編集・無効化（論理削除）・再有効化、CSVファイルからの一括登録 |
| ユーザー管理 | `UserManagementPage.tsx` | 管理者 | 社員アカウントの登録・編集・無効化・再有効化、ロール設定、パスワード初期化 |

各画面・機能の詳細な業務ルール（例：二重貸出防止、ノーショー自動取消、最後の管理者は無効化できない等）は`要件定義書/`配下、設計の詳細は`設計書/`配下を参照。

### 日次バッチ処理

- バックエンド起動時に組み込みスケジューラが日次バッチ（ノーショー自動取消・返却期限通知）を起動する。手動での追加操作は不要。
