from halo_cli.openapi_sync import generate_api_index, generate_error_code_table


def test_generate_api_index(tmp_path):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test", "version": "1"},
        "paths": {
            "/a": {"get": {"operationId": "getA", "tags": ["t"]}},
            "/b": {"post": {"operationId": "postB"}},
        },
    }
    from halo_cli.openapi_sync import OpenAPISpec

    specs = [OpenAPISpec(name="test", url="/v3/api-docs", document=spec)]
    out = generate_api_index(specs, output_file=tmp_path / "API_INDEX.md")
    text = out.read_text(encoding="utf-8")
    assert "| `GET` | `/a`" in text
    assert "| `POST` | `/b`" in text


def test_generate_error_code_table(tmp_path):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test", "version": "1"},
        "paths": {},
        "components": {
            "responses": {"400": {}, "500": {}},
            "schemas": {"ProblemDetail": {}, "ErrorResponse": {}, "Ok": {}},
        },
    }
    from halo_cli.openapi_sync import OpenAPISpec

    specs = [OpenAPISpec(name="test", url="/v3/api-docs", document=spec)]
    out = generate_error_code_table(specs, output_file=tmp_path / "ERROR_CODES.md")
    text = out.read_text(encoding="utf-8")
    assert "`400`" in text
    assert "`500`" in text
    assert "ProblemDetail" in text or "ErrorResponse" in text
