import pickle


def test_persistence_snapshot_is_checksummed(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.db.memory import InMemoryStore

    monkeypatch.setattr(settings, "storage_enabled", True)
    path = tmp_path / "quant-store.pkl"
    monkeypatch.setattr(settings, "storage_path", str(path))

    first = InMemoryStore()
    first.save()
    with path.open("rb") as handle:
        envelope = pickle.load(handle)
    assert envelope["format"] == "quant-snapshot-v1"
    assert envelope["sha256"]
    assert isinstance(envelope["payload"], bytes)

    restored = InMemoryStore()
    assert "BTCUSDT" in restored.symbols
    assert restored.persistence_error is None

    envelope["payload"] = envelope["payload"] + b"tampered"
    with path.open("wb") as handle:
        pickle.dump(envelope, handle)
    corrupted = InMemoryStore()
    assert "checksum mismatch" in (corrupted.persistence_error or "")
