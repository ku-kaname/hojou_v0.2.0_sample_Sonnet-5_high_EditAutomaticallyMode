from fastapi.testclient import TestClient

# ==================================================
# ヘルスチェック
# テスト対象ファイル：main.py
# テスト対象クラス：-
# テスト対象メソッド：health_check
# テスト仕様書：test_specification/integration_test_specification/共通/ヘルスチェック_結合テスト仕様書_v0.2.0.md
# ==================================================


# ========== 結合テストNo.1 ==========
# 正常系 - DB接続正常時に疎通確認結果を返却
def test_health_check_001_db_connected_returns_ok(client: TestClient) -> None:
    response = client.get("/health-check")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ========== 結合テストNo.2 ==========
# 異常系 - DB接続不可時に疎通確認結果を返却
def test_health_check_002_db_disconnected_returns_error(
    client: TestClient, postgres_container_stopped: None
) -> None:
    response = client.get("/health-check")

    assert response.status_code == 503
    assert response.json() == {"status": "error"}
