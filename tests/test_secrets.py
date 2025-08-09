from workflow import secrets


def test_secret_roundtrip():
    secrets.set_secret("api_key", "123")
    assert secrets.get_secret("api_key") == "123"
    assert secrets.get_secret("missing") is None
