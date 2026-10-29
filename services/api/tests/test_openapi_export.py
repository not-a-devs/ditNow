import json

from app.export_openapi import main, schema_text


def test_export_has_only_implemented_routes_and_is_deterministic():
    first = schema_text()
    assert first == schema_text()
    schema = json.loads(first)
    assert set(schema["paths"]) == {
        "/health",
        "/api/v1/health",
        "/api/v1/ai/campus/search",
        "/api/v1/ai/ask",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/public-campus",
        "/api/v1/public-campus/{record_id}",
    }
    assert "author_id" not in first
    assert set(schema["components"]["securitySchemes"]) == {"HTTPBearer"}


def test_missing_and_stale_snapshot_fail(tmp_path):
    path = tmp_path / "openapi.json"
    assert main(["--check", "--output", str(path)]) == 1
    assert main(["--output", str(path)]) == 0
    assert main(["--check", "--output", str(path)]) == 0
    path.write_text("{}", encoding="utf-8")
    assert main(["--check", "--output", str(path)]) == 1
