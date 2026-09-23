import pytest

from core import labelops as ops
from core.annotation import BBox, read_label_file
from core.dataset_source import DatasetSource
from core.trash import Trash


def _stems(pairs):
    return sorted(p.stem for p in pairs)


def _class_ids(path):
    return [b.class_id for b in read_label_file(path).boxes]


# ------------------------------------------------------------------- audit

def test_audit_finds_every_problem(flat_dataset):
    rep = ops.audit(DatasetSource(flat_dataset))

    assert rep.total_images == 6
    assert rep.total_labels == 6          # 5 paired + 1 orphan
    assert rep.total_boxes == 5
    assert _stems(rep.images_without_labels) == ["nolabel"]
    assert _stems(rep.labels_without_images) == ["orphan"]
    assert _stems(rep.empty_labels) == ["empty"]
    assert [p.stem for p, _ in rep.malformed_labels] == ["broken"]
    assert [(p.stem, n) for p, n in rep.out_of_range_boxes] == [("outside", 1)]
    assert _stems(rep.multiclass_images) == ["good_b"]
    assert rep.class_counts == {0: 3, 1: 2}
    assert rep.images_per_class == {0: 3, 1: 2}
    assert rep.problem_count == 5


def test_audit_reports_progress(flat_dataset):
    calls = []
    ops.audit(DatasetSource(flat_dataset), progress=lambda d, t: calls.append((d, t)))
    assert calls[-1] == (6, 6)


def test_audit_check_images_flags_corrupt_file(flat_dataset):
    (flat_dataset / "images" / "good_a.jpg").write_bytes(b"not really a jpeg")
    rep = ops.audit(DatasetSource(flat_dataset), check_images=True)
    assert _stems(rep.unreadable_images) == ["good_a"]


def test_summary_rows_cover_every_problem_bucket(flat_dataset):
    rep = ops.audit(DatasetSource(flat_dataset))
    assert sum(count for _, count, _ in rep.summary_rows()) == rep.problem_count


# ------------------------------------------------------------------- fixes

def test_fix_unpaired_dry_run_touches_nothing(flat_dataset):
    src = DatasetSource(flat_dataset)
    res = ops.fix_unpaired(src, ops.audit(src), Trash(flat_dataset))
    assert res.trashed == 2
    assert (flat_dataset / "images" / "nolabel.jpg").exists()
    assert (flat_dataset / "labels" / "orphan.txt").exists()


def test_fix_unpaired_moves_to_trash(flat_dataset):
    src = DatasetSource(flat_dataset)
    trash = Trash(flat_dataset)
    res = ops.fix_unpaired(src, ops.audit(src), trash, dry_run=False)
    assert res.trashed == 2
    assert not (flat_dataset / "images" / "nolabel.jpg").exists()
    assert not (flat_dataset / "labels" / "orphan.txt").exists()
    assert trash.undo_last() == 2


def test_fix_empty_labels_trashes_image_and_label(flat_dataset):
    src = DatasetSource(flat_dataset)
    res = ops.fix_empty_labels(src, ops.audit(src), Trash(flat_dataset), dry_run=False)
    assert res.trashed == 2
    assert not (flat_dataset / "images" / "empty.jpg").exists()
    assert not (flat_dataset / "labels" / "empty.txt").exists()


def test_fix_malformed_keeps_good_lines(flat_dataset):
    src = DatasetSource(flat_dataset)
    res = ops.fix_malformed_labels(src, ops.audit(src), dry_run=False)
    assert res.rewritten == 1
    lf = read_label_file(flat_dataset / "labels" / "broken.txt")
    assert lf.malformed == [] and len(lf.boxes) == 1


def test_fix_out_of_range_clamps(flat_dataset):
    src = DatasetSource(flat_dataset)
    ops.fix_out_of_range(src, ops.audit(src), dry_run=False)
    [b] = read_label_file(flat_dataset / "labels" / "outside.txt").boxes
    assert b.x_center + b.width / 2 == pytest.approx(1.0)
    assert b.x_center - b.width / 2 == pytest.approx(0.85)
    assert ops.audit(DatasetSource(flat_dataset)).out_of_range_boxes == []


def test_clamp_polygon():
    poly = BBox.from_polygon(0, [-0.1, 0.2, 1.2, 0.2, 1.2, 0.8, -0.1, 0.8])
    clamped = ops._clamp(poly)
    assert min(clamped.polygon) >= 0.0 and max(clamped.polygon) <= 1.0
    assert clamped.width == pytest.approx(1.0)


# ------------------------------------------------------------ class remaps

def test_remap_dry_run_counts_without_writing(flat_dataset):
    res = ops.remap_classes(DatasetSource(flat_dataset), {0: 5})
    # good_a, good_b, outside + orphan.txt: remaps cover label files with no image too
    assert (res.files_changed, res.boxes_changed) == (4, 4)
    assert _class_ids(flat_dataset / "labels" / "good_a.txt") == [0]


def test_swap_classes(flat_dataset):
    src = DatasetSource(flat_dataset)
    ops.remap_classes(src, ops.swap_mapping(0, 1), dry_run=False)
    assert _class_ids(flat_dataset / "labels" / "good_b.txt") == [1, 0]
    assert _class_ids(flat_dataset / "labels" / "good_a.txt") == [1]


def test_remap_leaves_coordinates_alone(flat_dataset):
    path = flat_dataset / "labels" / "good_a.txt"
    before = read_label_file(path).boxes[0]
    ops.remap_classes(DatasetSource(flat_dataset), {0: 7}, dry_run=False)
    after = read_label_file(path).boxes[0]
    assert after.class_id == 7
    assert (after.x_center, after.y_center, after.width, after.height) == \
           (before.x_center, before.y_center, before.width, before.height)


def test_merge_all_mapping():
    assert ops.merge_all_mapping([0, 1, 2], 0) == {0: 0, 1: 0, 2: 0}


def test_delete_class(flat_dataset):
    res = ops.delete_class(DatasetSource(flat_dataset), 1, dry_run=False)
    assert res.boxes_changed == 2
    assert _class_ids(flat_dataset / "labels" / "good_b.txt") == [0]
    assert (flat_dataset / "images" / "good_b.jpg").exists()


def test_reindex_closes_gaps(flat_dataset):
    ops.remap_classes(DatasetSource(flat_dataset), {1: 4}, dry_run=False)
    ops.reindex_classes(DatasetSource(flat_dataset), keep_order=[0, 4], dry_run=False)
    assert _class_ids(flat_dataset / "labels" / "good_b.txt") == [0, 1]


# ----------------------------------------------------------------- subsets

def test_random_sample_is_reproducible(flat_dataset, tmp_path):
    src = DatasetSource(flat_dataset)
    a = ops.random_sample(src, 3, tmp_path / "a", seed=1)
    b = ops.random_sample(src, 3, tmp_path / "b", seed=1)
    assert a.copied == 3
    names = lambda d: sorted(p.name for p in (d / "images").iterdir())
    assert names(tmp_path / "a") == names(tmp_path / "b")


def test_random_sample_too_many(flat_dataset, tmp_path):
    with pytest.raises(ValueError):
        ops.random_sample(DatasetSource(flat_dataset), 99, tmp_path / "out")


def test_copy_range_is_one_based_inclusive(flat_dataset, tmp_path):
    res = ops.copy_range(DatasetSource(flat_dataset), 2, 3, tmp_path / "out")
    assert res.copied == 2


@pytest.mark.parametrize("start,end", [(0, 2), (3, 2), (1, 99)])
def test_copy_range_rejects_bad_ranges(flat_dataset, tmp_path, start, end):
    with pytest.raises(ValueError):
        ops.copy_range(DatasetSource(flat_dataset), start, end, tmp_path / "out")


def test_copy_reports_images_missing_labels(flat_dataset, tmp_path):
    res = ops.copy_range(DatasetSource(flat_dataset), 1, 6, tmp_path / "out")
    assert res.missing_labels == ["nolabel.jpg"]
    assert len(list((tmp_path / "out" / "labels").iterdir())) == 5


def test_chunk_dataset(flat_dataset, tmp_path):
    res = ops.chunk_dataset(DatasetSource(flat_dataset), 4, tmp_path / "out")
    assert [c.name for c in res.chunks] == ["chunk_1", "chunk_2"]
    assert res.copied == 6
    assert len(list((tmp_path / "out" / "chunk_2" / "images").iterdir())) == 2


def test_chunk_size_must_be_positive(flat_dataset, tmp_path):
    with pytest.raises(ValueError):
        ops.chunk_dataset(DatasetSource(flat_dataset), 0, tmp_path / "out")


def test_filter_null_keeps_only_images_with_boxes(flat_dataset, tmp_path):
    res = ops.filter_null(DatasetSource(flat_dataset), tmp_path / "out")
    kept = sorted(p.stem for p in (tmp_path / "out" / "images").iterdir())
    assert kept == ["broken", "good_a", "good_b", "outside"]
    assert res.copied == 4


# ---------------------------------------------------------- review picking

@pytest.mark.parametrize("selector,expected", [
    (ops.REVIEW_ALL, ["broken", "empty", "good_a", "good_b", "nolabel", "outside"]),
    (ops.REVIEW_EMPTY, ["empty"]),
    (ops.REVIEW_UNLABELED, ["nolabel"]),
    (ops.REVIEW_MALFORMED, ["broken"]),
    (ops.REVIEW_MULTICLASS, ["good_b"]),
    (1, ["broken", "good_b"]),
])
def test_collect_for_review(flat_dataset, selector, expected):
    assert _stems(ops.collect_for_review(DatasetSource(flat_dataset), selector)) == expected
