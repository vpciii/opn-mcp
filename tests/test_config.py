"""Pin the configuration contract (task 1: behavior-preserving extraction).

These tests pin the env names, defaults, and parsing that the old
module-level constants implemented, so the extraction to _settings()
is provably behavior-preserving. The verify_ssl default characterized
here is the *current* contract; task 2 (SC-2) changes it deliberately.
"""

import server


def test_defaults_match_old_module_constants(clean_env):
    s = server._settings()
    assert s.host == "192.168.1.1"
    assert s.api_key == ""
    assert s.api_secret == ""
    assert s.verify_ssl is False
    assert s.base_url == "https://192.168.1.1/api"


def test_env_values_are_read_per_call(clean_env):
    clean_env.setenv("OPNSENSE_HOST", "fw.example.test")
    clean_env.setenv("OPNSENSE_API_KEY", "k")
    clean_env.setenv("OPNSENSE_API_SECRET", "s")
    clean_env.setenv("OPNSENSE_VERIFY_SSL", "true")
    s = server._settings()
    assert s.host == "fw.example.test"
    assert (s.api_key, s.api_secret) == ("k", "s")
    assert s.verify_ssl is True
    assert s.base_url == "https://fw.example.test/api"

    # settings are not cached at import: a changed env is seen
    clean_env.setenv("OPNSENSE_HOST", "other.example.test")
    assert server._settings().host == "other.example.test"


def test_verify_ssl_parsing_is_case_insensitive_true_only(clean_env):
    for raw, expected in (
        ("true", True),
        ("TRUE", True),
        ("True", True),
        ("false", False),
        ("1", False),  # old contract: only the literal "true" enables
        ("yes", False),
        ("", False),
    ):
        clean_env.setenv("OPNSENSE_VERIFY_SSL", raw)
        assert server._settings().verify_ssl is expected, raw
