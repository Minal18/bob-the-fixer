from repo_config import DEFAULT_CONFIG, load_config


def test_load_config_returns_default_when_file_missing():
    assert load_config(None) == dict(DEFAULT_CONFIG)


def test_load_config_merges_overrides_onto_default():
    raw = "severity_threshold: error\n"
    config = load_config(raw)

    assert config["severity_threshold"] == "error"
    # untouched defaults still present
    assert config["review_focus"] == DEFAULT_CONFIG["review_focus"]
    assert config["ignore_paths"] == DEFAULT_CONFIG["ignore_paths"]


def test_load_config_returns_none_on_malformed_yaml():
    raw = "key: [unterminated"
    assert load_config(raw) is None


def test_load_config_returns_none_when_top_level_is_not_a_mapping():
    raw = "- a\n- b\n"
    assert load_config(raw) is None


def test_load_config_treats_empty_file_as_no_overrides():
    assert load_config("") == dict(DEFAULT_CONFIG)
