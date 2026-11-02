import rag


def test_package_imports():
    assert rag.__version__


def test_ask_without_a_configured_llm_explains_what_to_set(monkeypatch, capsys):
    from rag import cli

    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)

    assert cli.main(["ask", "anything"]) == 1
    err = capsys.readouterr().err
    assert "LLM_PROVIDER" in err and "API key" in err and ".env.example" in err


def test_ask_with_an_empty_index_says_to_ingest(monkeypatch, capsys, tmp_path):
    from rag import cli

    monkeypatch.setenv("LLM_MODEL", "some-model")
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "empty"))
    monkeypatch.setattr("rag.embeddings.SentenceTransformerEmbedder", lambda name: type("E", (), {"embed": lambda self, texts: [[0.0] * 4 for _ in texts]})())

    assert cli.main(["ask", "anything"]) == 1
    assert "ingested" in capsys.readouterr().err
