from pathlib import Path
from storage.dedup import DedupStore

def test_dedup_store(tmp_path: Path):
    store_file = tmp_path / "seen_ids.json"
    store = DedupStore(store_path=store_file)

    assert not store.is_seen("tt_123456")
    store.mark_seen("tt_123456")
    assert store.is_seen("tt_123456")
    assert store.count() == 1

    # Save to disk
    store.save()
    assert store_file.exists()

    # Load again in a new instance
    store2 = DedupStore(store_path=store_file)
    assert store2.is_seen("tt_123456")
    assert not store2.is_seen("fb_999999")
    assert store2.count() == 1
