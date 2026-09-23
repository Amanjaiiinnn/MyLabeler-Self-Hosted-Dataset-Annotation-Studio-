import json

from core.trash import MANIFEST, Trash


def _files(root, *names):
    out = []
    for n in names:
        p = root / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(n, encoding="utf-8")
        out.append(p)
    return out


def test_send_moves_files_and_writes_manifest(tmp_path):
    a, b = _files(tmp_path, "images/a.jpg", "labels/a.txt")
    batch = Trash(tmp_path).send([a, b], reason="test")

    assert batch.count == 2
    assert not a.exists() and not b.exists()
    assert (batch.directory / "images" / "a.jpg").exists()
    manifest = json.loads((batch.directory / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["reason"] == "test"
    assert len(manifest["entries"]) == 2


def test_send_skips_missing_paths(tmp_path):
    batch = Trash(tmp_path).send([tmp_path / "ghost.jpg", None])
    assert batch.count == 0
    assert not (tmp_path / ".trash").exists()


def test_restore_round_trip(tmp_path):
    a, b = _files(tmp_path, "images/a.jpg", "labels/a.txt")
    trash = Trash(tmp_path)
    trash.send([a, b])

    assert trash.undo_last() == 2
    assert a.read_text(encoding="utf-8") == "images/a.jpg"
    assert b.exists()
    assert trash.batches() == []


def test_restore_never_overwrites(tmp_path):
    [a] = _files(tmp_path, "a.txt")
    trash = Trash(tmp_path)
    trash.send([a])
    a.write_text("new file", encoding="utf-8")        # something took its place
    assert trash.undo_last() == 0
    assert a.read_text(encoding="utf-8") == "new file"


def test_undo_restores_newest_batch_only(tmp_path):
    first, second = _files(tmp_path, "first.txt", "second.txt")
    trash = Trash(tmp_path)
    trash.send([first])
    trash.send([second])

    assert trash.undo_last() == 1
    assert second.exists() and not first.exists()
    assert len(trash.batches()) == 1


def test_rapid_sends_never_share_a_batch(tmp_path):
    # Regression: on Windows back-to-back sends got the same timestamp, merged
    # into one folder, and undo then permanently deleted the earlier file.
    files = _files(tmp_path, *[f"f{i}.txt" for i in range(30)])
    trash = Trash(tmp_path)
    ids = [trash.send([f]).batch_id for f in files]
    assert len(set(ids)) == 30

    for expected in reversed(files):
        assert trash.undo_last() == 1
        assert expected.exists()
    assert all(f.exists() for f in files)


def test_batch_when_ignores_collision_suffix(tmp_path):
    from core.trash import TrashBatch
    assert TrashBatch("20260923_101500_123456_002", tmp_path).when == "2026-09-23 10:15:00"


def test_undo_with_empty_trash(tmp_path):
    assert Trash(tmp_path).undo_last() == 0


def test_empty_purges_everything(tmp_path):
    trash = Trash(tmp_path)
    trash.send(_files(tmp_path, "a.txt"))
    trash.send(_files(tmp_path, "b.txt"))
    assert trash.size_bytes() > 0

    assert trash.empty() == 2
    assert trash.batches() == [] and trash.size_bytes() == 0
