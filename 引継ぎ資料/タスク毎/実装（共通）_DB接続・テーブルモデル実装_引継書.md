# DB接続・テーブルモデル実装

- **状態**: 完了
- **開始日**: 2026-10-08
- **完了日**: 2026-10-08

---

## 目的・背景

`設計書/テーブル定義（models）_v0.2.0.md`に基づき、`backend/app/models.py`（USER・EQUIPMENT・LOAN_REQUEST・NOTIFICATIONの全テーブルモデル）・`backend/app/database.py`（DBエンジン・セッション生成・`get_db`依存性注入関数）を実装し、Alembicの初期マイグレーションを生成する。

---

## 進捗ログ

### 2026-10-08
**◆対応者：Claude Sonnet 5**

- `backend/app/database.py`：`DATABASE_URL`環境変数からエンジンを生成し、`SessionLocal`（セッションファクトリ）・`Base`（テーブルモデル共通基底クラス）・`get_db`（リクエスト単位でセッションを生成し処理後に解放する依存性注入関数）を実装した。
- `backend/app/models.py`：設計書のテーブル定義に基づき、`User`・`Equipment`・`LoanRequest`・`Notification`の4モデルを実装した。カラムの必須・桁数・制約（一意制約・CHECK制約）・外部キー（ON UPDATE CASCADE / ON DELETE RESTRICT）・インデックスは、設計書に明記された制約名・インデックス名をそのまま`__table_args__`に反映した。「空文字許容」の項目（`department`・`description`・`location`・`reject_cancel_reason`・`return_note`）はNOT NULL＋既定値空文字とし、「空欄許容」の項目（外部キー任意列・日時任意列）はNULL許容とした。テーブル間に外部キー参照があり分割できないため、4モデルを本タスクでまとめて実装した。
- `backend/app/__init__.py`を新規作成し、`app`をパッケージとして成立させた（`backend/pyproject.toml`にもホイールパッケージ対象として`app`を追記）。
- Alembic初期マイグレーション：開発環境でDockerデーモンが起動していなかったため、PostgreSQLコンテナに接続した上でのautogenerateは実行できなかった。代わりに、一時的にSQLiteを対象としてautogenerateを実行してテーブル・制約・インデックスの生成内容を確認した上で、日時列の既定値をPostgreSQL向け（`sa.text("now()")`）に修正するなど、PostgreSQL向けの内容に手動で調整した`backend/migrations/versions/0001_initial_schema.py`を作成した。`backend/migrations/env.py`（`DATABASE_URL`環境変数を読み込み、`app.models`のテーブルモデルを`target_metadata`として使用）・`backend/migrations/script.py.mako`（Alembic標準テンプレート）も新規作成した。
- 作成したマイグレーションは、一時的なSQLite DBに対して`alembic upgrade head`→`alembic downgrade base`を実行し、エラーなく適用・取り消しできることを確認した。
- `ruff check`・`mypy`で`backend/app/database.py`・`backend/app/models.py`・`backend/migrations/`に問題がないことを確認した（検証用に作成した一時venv・Dockerコンテナ・SQLiteファイルは全て作業後に削除済み）。

---

## 作業ログ

- 開始: 2026-10-08 18:14:39 / 終了: 2026-10-08 18:23:07

---

## 現在の進捗まとめ

- `backend/app/database.py`・`backend/app/models.py`・Alembic初期マイグレーション一式を作成した。
- PostgreSQLコンテナに接続した状態でのautogenerate実行による最終確認は、Docker未起動のため本タスク内では行えていない。次回Docker Compose起動時（結合テスト工程等）に、`docker compose up -d db`→`alembic upgrade head`で実際のPostgreSQLへの適用を確認することを推奨する。

## 次にやること

- なし（本タスクは完了）。次タスクは認証認可共通処理実装。
