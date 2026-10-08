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
