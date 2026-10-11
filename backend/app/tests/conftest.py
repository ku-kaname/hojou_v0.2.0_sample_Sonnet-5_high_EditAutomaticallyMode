"""
単体テスト共通設定

【概要】
`app`配下のモジュールは読み込み時に環境変数（DB接続・JWT設定等）を参照するため、
テスト対象モジュールのインポートより前に、単体テスト用の仮の環境変数を設定する
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-test-32-bytes-or-more")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost")
os.environ.setdefault("INITIAL_ADMIN_USER_ID", "admin")
os.environ.setdefault("INITIAL_ADMIN_NAME", "管理者")
os.environ.setdefault("INITIAL_ADMIN_PASSWORD", "test-password")
