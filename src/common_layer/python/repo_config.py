"""Loads the per-repo .bob-the-fixer.yml config. Fails safe on malformed input:
returns None so the caller skips the review rather than reviewing with a broken config.
A missing file (raw_yaml=None) gets the default config instead, so a repo works out of
the box before anyone writes a config file.
"""
import yaml

CONFIG_PATH = ".bob-the-fixer.yml"

DEFAULT_CONFIG = {
    "review_focus": ["bugs", "security"],
    "ignore_paths": [],
    "custom_instructions": "",
    "severity_threshold": "warning",
}


def load_config(raw_yaml: str | None) -> dict | None:
    if raw_yaml is None:
        return dict(DEFAULT_CONFIG)
    try:
        parsed = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, dict):
        return None
    return {**DEFAULT_CONFIG, **parsed}
