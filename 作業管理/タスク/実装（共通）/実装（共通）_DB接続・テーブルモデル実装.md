# DB接続・テーブルモデル実装

## スコープ

- `設計書/テーブル定義（models）_v0.2.0.md`に基づき、`backend/app/models.py`（USER・EQUIPMENT・LOAN_REQUEST・NOTIFICATIONの全テーブルモデル）を実装する。
- `backend/app/database.py`（DBエンジン・セッション生成・`get_db`依存性注入関数）を実装する。
- テーブルモデル確定後、Alembicの初期マイグレーションを生成する。

## 着手条件

- 実行環境整備（Alembic設定ファイルの配置）が完了していること。

## アプローチ（案）

- SQLAlchemy（同期Session）を用いる。
- 全テーブルを一括で実装する（テーブル間外部キー参照があり分割できないため、本タスクでまとめて行う）。

## 修正対象資材

### 修正対象

- `backend/app/models.py`（新規）
- `backend/app/database.py`（新規）
- `backend/migrations/`（新規：初期マイグレーション）

### 影響資材

- なし

## 引継ぎ資料

[引継ぎ資料/タスク毎/実装（共通）_DB接続・テーブルモデル実装_引継書.md](../../../引継ぎ資料/タスク毎/実装（共通）_DB接続・テーブルモデル実装_引継書.md)
