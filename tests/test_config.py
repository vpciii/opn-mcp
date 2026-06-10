"""Pin the configuration contract.

Task 1 characterized the old contract to prove the extraction to
_settings() behavior-preserving. Task 2 (SC-2, ADR 0005) deliberately
changed the verify_ssl default to true and added ca_bundle; the pins
below reflect the new contract.
"""

import server


def test_defaults(clean_env):
    s = server._settings()
    assert s.host == "192.168.1.1"
    assert s.api_key == ""
    assert s.api_secret == ""
    assert s.verify_ssl is True  # secure default since ADR 0005 (SC-2)
    assert s.ca_bundle is None
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


def test_verify_ssl_disabled_only_by_explicit_false(clean_env):
    # Fail-safe parsing (R-2): anything except the literal "false"
    # verifies, so a typo can't silently disable verification.
    for raw, expected in (
        ("true", True),
        ("TRUE", True),
        ("false", False),
        ("FALSE", False),
        (" false ", False),
        ("1", True),
        ("yes", True),
        ("no", True),
        ("", True),
    ):
        clean_env.setenv("OPNSENSE_VERIFY_SSL", raw)
        assert server._settings().verify_ssl is expected, raw
