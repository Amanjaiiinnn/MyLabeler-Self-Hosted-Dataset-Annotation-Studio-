import pytest
from PIL import Image

from core.annotation import BBox, read_label_file
from core.dataset import (PreprocessConfig, _apply_label_steps, _remap_for_letterbox,
                          export_dataset, source_stem)
from tests.conftest import add_labeled_image, make_image, write_label


def _names(folder):
    return sorted(p.name for p in folder.iterdir())


def _yaml(report):
    return (report.out_root / "data.yaml").read_text(encoding="utf-8")


@pytest.fixture
def labeled_project(project):
    project.add_class("cat")
    project.add_class("dog")
    for i in range(5):
        add_labeled_image(project, f"img{i}.jpg", [f"{i % 2} 0.5 0.5 0.2 0.2"])
    make_image(project.image_path("unlabeled.jpg"))
    project._sync_existing_files()
    return project


# ---------------------------------------------------------------- helpers

@pytest.mark.parametrize("stem,expected", [
    ("frame_07_aug2", "frame_07"),
    ("frame_07_aug12", "frame_07"),
    ("frame_07", "frame_07"),
    ("aug_frame", "aug_frame"),
])
def test_source_stem(stem, expected):
    assert source_stem(stem) == expected


def test_preprocess_config_noop_and_describe():
    assert PreprocessConfig().is_noop
    cfg = PreprocessConfig(grayscale=True, modify_classes={2: 0, 1: 0}, drop_classes=[3])
    assert not cfg.is_noop and cfg.touches_pixels
    assert cfg.describe() == ["Grayscale", "Remap classes (1->0, 2->0)", "Drop classes [3]"]


def test_apply_label_steps_drops_then_remaps_without_mutating():
    boxes = [BBox(0, .5, .5, .1, .1), BBox(1, .5, .5, .1, .1), BBox(2, .5, .5, .1, .1)]
    out = _apply_label_steps(boxes, PreprocessConfig(modify_classes={1: 0}, drop_classes=[2]))
    assert [b.class_id for b in out] == [0, 0]
    assert boxes[1].class_id == 1


def test_letterbox_remap_keeps_box_centred():
    # 200x100 into 100x100: scale 0.5, content 100x50, 25px pad top and bottom
    [b] = _remap_for_letterbox([BBox(0, 0.5, 0.5, 0.5, 0.5)], 200, 100, 100, 100, 0.5, (0, 25))
    assert (b.x_center, b.y_center, b.width, b.height) == pytest.approx((0.5, 0.5, 0.5, 0.25))


# ---------------------------------------------------------------- exports

def test_export_layout_and_yaml(labeled_project):
    rep = export_dataset(labeled_project, "v1", val_ratio=0.2)

    assert (rep.train, rep.val, rep.test) == (4, 1, 0)
    assert not (rep.out_root / "test").exists()
    all_images = _names(rep.out_root / "train" / "images") + _names(rep.out_root / "val" / "images")
    assert sorted(all_images) == [f"img{i}.jpg" for i in range(5)]   # unlabeled.jpg left out

    yaml = _yaml(rep)
    assert "train: train/images" in yaml and "val: val/images" in yaml
    assert "  0: cat\n  1: dog" in yaml
    assert rep.classes == 2


def test_export_is_reproducible(labeled_project):
    a = _names(export_dataset(labeled_project, "a", seed=7).out_root / "val" / "images")
    b = _names(export_dataset(labeled_project, "b", seed=7).out_root / "val" / "images")
    assert a == b


def test_export_never_leaves_val_empty(project):
    add_labeled_image(project, "only.jpg", ["0 0.5 0.5 0.2 0.2"])
    rep = export_dataset(project, "v1", val_ratio=0.2)
    assert rep.val == 1


def test_export_overwrites_previous_version(labeled_project):
    rep = export_dataset(labeled_project, "v1")
    stale = rep.out_root / "train" / "images" / "stale.jpg"
    make_image(stale)
    export_dataset(labeled_project, "v1")
    assert not stale.exists()


def test_export_respects_assigned_splits(labeled_project):
    labeled_project.set_splits(["img0.jpg", "img1.jpg"], "valid")
    labeled_project.set_split("img2.jpg", "test")
    labeled_project.set_splits(["img3.jpg", "img4.jpg"], "train")

    rep = export_dataset(labeled_project, "v1")
    assert _names(rep.out_root / "val" / "images") == ["img0.jpg", "img1.jpg"]
    assert _names(rep.out_root / "test" / "images") == ["img2.jpg"]
    assert _names(rep.out_root / "train" / "images") == ["img3.jpg", "img4.jpg"]
    assert "test: test/images" in _yaml(rep)


def test_augmented_variants_follow_their_source(labeled_project):
    pm = labeled_project
    for v in range(2):
        make_image(pm.aug_images_dir / f"img0_aug{v}.jpg")
        write_label(pm.aug_labels_dir / f"img0_aug{v}.txt", ["0 0.4 0.4 0.2 0.2"])
    make_image(pm.aug_images_dir / "gone_aug0.jpg")               # source no longer exists
    write_label(pm.aug_labels_dir / "gone_aug0.txt", ["0 0.4 0.4 0.2 0.2"])
    pm.set_split("img0.jpg", "valid")

    rep = export_dataset(pm, "v1")
    assert _names(rep.out_root / "val" / "images") == ["img0.jpg", "img0_aug0.jpg", "img0_aug1.jpg"]
    assert not any("aug" in n for n in _names(rep.out_root / "train" / "images"))
    assert any("no surviving source" in w for w in rep.warnings)

    rep = export_dataset(pm, "no_aug", include_augmented=False)
    assert rep.train + rep.val == 5


def test_export_names_unknown_class_ids(labeled_project):
    add_labeled_image(labeled_project, "extra.jpg", ["3 0.5 0.5 0.2 0.2"])
    rep = export_dataset(labeled_project, "v1")
    yaml = _yaml(rep)
    assert "  2: unused" in yaml and "  3: class3" in yaml
    assert rep.classes == 4
    assert any("class id(s) 3" in w for w in rep.warnings)


def test_export_applies_label_preprocessing(labeled_project):
    cfg = PreprocessConfig(drop_classes=[1], filter_null=True)
    rep = export_dataset(labeled_project, "v1", preprocess=cfg)
    # img1 and img3 only had class-1 boxes, so filter_null drops them
    assert rep.train + rep.val == 3
    for lbl in (rep.out_root / "train" / "labels").iterdir():
        assert all(b.class_id == 0 for b in read_label_file(lbl).boxes)
    assert "# preprocessing: Drop classes [1]" in _yaml(rep)


def test_export_resizes_images(project):
    add_labeled_image(project, "wide.png", ["0 0.5 0.5 0.5 0.5"], size=(200, 100))
    rep = export_dataset(project, "v1", preprocess=PreprocessConfig(resize=(100, 100)))
    [out] = list((rep.out_root / "val" / "images").iterdir())
    with Image.open(out) as im:
        assert im.size == (100, 100)
    [b] = read_label_file(rep.out_root / "val" / "labels" / "wide.txt").boxes
    assert b.height == pytest.approx(0.25)


def test_export_empty_project_warns(project):
    rep = export_dataset(project, "v1")
    assert rep.train == rep.val == 0
    assert any("empty" in w for w in rep.warnings)
