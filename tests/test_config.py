import pytest

from recall.config import load_config


def test_load_config_reads_env():
    cfg = load_config({"DEEPSEEK_API_KEY": "sk-test"})
    assert cfg.api_key == "sk-test"
    assert cfg.base_url == "https://api.deepseek.com"
    assert cfg.model == "deepseek-chat"
    assert cfg.max_cost_usd_per_source == 2.0


def test_load_config_overrides():
    cfg = load_config({"DEEPSEEK_API_KEY": "k", "RECALL_MODEL": "deepseek-reasoner"})
    assert cfg.model == "deepseek-reasoner"


def test_missing_key_raises_without_leaking_env():
    with pytest.raises(RuntimeError) as exc:
        load_config({})
    assert "DEEPSEEK_API_KEY" in str(exc.value)
