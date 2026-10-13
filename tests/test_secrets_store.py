from insight_engine.ops.secrets_store import SecretsStore


def test_secret_roundtrip_encrypted(tmp_settings) -> None:
    store = SecretsStore(tmp_settings)
    store.set_secret("llm.api_key.deepseek", "sk-test-secret-value")
    assert store.has_secret("llm.api_key.deepseek")
    assert store.get_secret("llm.api_key.deepseek") == "sk-test-secret-value"

    # Ciphertext in DB must not equal plaintext
    from insight_engine.db.connection import get_connection

    with get_connection(tmp_settings.db_path) as conn:
        blob = conn.execute(
            "SELECT ciphertext FROM app_secrets WHERE secret_key = ?",
            ("llm.api_key.deepseek",),
        ).fetchone()["ciphertext"]
    assert b"sk-test-secret-value" not in bytes(blob)

    store.save_llm_settings(
        provider="deepseek",
        api_key="sk-new",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
    )
    loaded = store.load_llm_settings("deepseek")
    assert loaded["api_key"] == "sk-new"
    assert loaded["model"] == "deepseek-chat"
    assert store.get_pref("llm.provider") == "deepseek"

    store.delete_secret(store.llm_secret_key("deepseek"))
    assert not store.has_secret(store.llm_secret_key("deepseek"))
