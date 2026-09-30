"""Loads the per-repo .bob-the-fixer.yml config. Fails safe on malformed input:
returns None so the caller skips the review rather than reviewing with a broken config.
A missing file (raw_yaml=None) gets the baseline config instead, so a repo works out of
the box before anyone writes a config file.
"""
import os

import yaml

CONFIG_PATH = ".bob-the-fixer.yml"
_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "default_config.yml")

with open(_DEFAULT_CONFIG_PATH) as f:
    DEFAULT_CONFIG = yaml.safe_load(f)


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
