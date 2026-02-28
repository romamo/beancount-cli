from beancount_cli.config import CliConfig


def test_beancount_file_env_var_is_respected(monkeypatch, tmp_path):
    ledger = tmp_path / "ledger.beancount"
    ledger.write_text('option "title" "Test"\n', encoding="utf-8")

    monkeypatch.delenv("FILE", raising=False)
    monkeypatch.delenv("BEANCOUNT_PATH", raising=False)
    monkeypatch.setenv("BEANCOUNT_FILE", str(ledger))

    config = CliConfig()
    assert config.beancount_file == ledger
    assert config.get_resolved_ledger() == ledger


def test_beancount_path_env_var_is_respected(monkeypatch, tmp_path):
    ledger_dir = tmp_path / "ledgerdir"
    ledger_dir.mkdir()
    main_file = ledger_dir / "main.beancount"
    main_file.write_text('option "title" "Test"\n', encoding="utf-8")

    monkeypatch.delenv("FILE", raising=False)
    monkeypatch.delenv("BEANCOUNT_FILE", raising=False)
    monkeypatch.setenv("BEANCOUNT_PATH", str(ledger_dir))

    config = CliConfig()
    assert config.beancount_path == ledger_dir
    assert config.get_resolved_ledger() == main_file
