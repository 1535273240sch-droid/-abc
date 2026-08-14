import pytest

from app.core.credential_crypto import CredentialCryptoError, open_dict, seal_dict


class TestCredentialCrypto:
    def test_roundtrip(self):
        token = seal_dict("strong-master-key-here", {"api_key": "k", "api_secret": "s", "passphrase": "p"})
        out = open_dict("strong-master-key-here", token)
        assert out == {"api_key": "k", "api_secret": "s", "passphrase": "p"}

    def test_wrong_key(self):
        token = seal_dict("strong-master-key-here", {"api_key": "k", "api_secret": "s"})
        with pytest.raises(CredentialCryptoError):
            open_dict("wrong-key", token)

    def test_tampered_token(self):
        token = seal_dict("strong-master-key-here", {"api_key": "k", "api_secret": "s"})
        raw = token[:-4] + ("a" if token[-4] != "a" else "b") + token[-3:]
        with pytest.raises(CredentialCryptoError):
            open_dict("strong-master-key-here", raw)

    def test_short_key(self):
        with pytest.raises(CredentialCryptoError):
            seal_dict("short", {"api_key": "k"})

    def test_unicode(self):
        token = seal_dict("strong-master-key-here", {"api_key": "键", "api_secret": "秘"})
        out = open_dict("strong-master-key-here", token)
        assert out == {"api_key": "键", "api_secret": "秘"}
