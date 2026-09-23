from core.dataset_source import FLAT_SPLIT, DatasetSource, parse_yaml_names
from tests.conftest import make_image, write_label


def test_flat_layout(flat_dataset):
    src = DatasetSource(flat_dataset)
    assert src.layout == "flat"
    assert src.splits() == [FLAT_SPLIT]
    assert len(src.pairs()) == 6


def test_split_layout_normalises_valid_to_val(tmp_path):
    root = tmp_path / "ds"
    make_image(root / "train" / "images" / "a.jpg")
    make_image(root / "valid" / "images" / "b.jpg")
    make_image(root / "test" / "images" / "c.jpg")
    make_image(root / "augmented" / "images" / "x.jpg")   # ignored dir
    src = DatasetSource(root)
    assert src.layout == "split"
    assert src.splits() == ["train", "val", "test"]
    assert {p.split: p.image.name for p in src.pairs()} == {
        "train": "a.jpg", "val": "b.jpg", "test": "c.jpg"}


def test_same_dir_layout(tmp_path):
    make_image(tmp_path / "a.png")
    write_label(tmp_path / "a.txt", ["0 0.5 0.5 0.1 0.1"])
    src = DatasetSource(tmp_path)
    assert src.layout == "same-dir"
    [pair] = src.pairs()
    assert pair.has_image and pair.has_label


def test_missing_folder_is_invalid(tmp_path):
    src = DatasetSource(tmp_path / "does-not-exist")
    assert not src.is_valid
    assert src.pairs() == []


def test_label_files_skip_reserved_names(flat_dataset):
    names = {p.name for p in DatasetSource(flat_dataset).label_files()}
    assert "classes.txt" not in names
    assert "orphan.txt" in names


def test_orphan_labels(flat_dataset):
    orphans = DatasetSource(flat_dataset).orphan_labels()
    assert [p.label.name for p in orphans] == ["orphan.txt"]
    assert orphans[0].image is None


def test_class_names_from_classes_txt(flat_dataset):
    assert DatasetSource(flat_dataset).class_names() == {0: "cat", 1: "dog"}


def test_data_yaml_wins_over_classes_txt(flat_dataset):
    (flat_dataset / "data.yaml").write_text("names: [bird, fish]\n", encoding="utf-8")
    assert DatasetSource(flat_dataset).class_names() == {0: "bird", 1: "fish"}


# --------------------------------------------------------- parse_yaml_names

def test_yaml_inline_list():
    assert parse_yaml_names("nc: 2\nnames: ['cat', \"dog\"]\n") == {0: "cat", 1: "dog"}


def test_yaml_inline_dict():
    assert parse_yaml_names("names: {0: cat, 2: dog}") == {0: "cat", 2: "dog"}


def test_yaml_block_dict():
    text = "path: x\nnames:\n  0: cat\n  1: dog\ntrain: t\n"
    assert parse_yaml_names(text) == {0: "cat", 1: "dog"}


def test_yaml_block_list():
    assert parse_yaml_names("names:\n  - cat\n  - dog\n") == {0: "cat", 1: "dog"}


def test_yaml_without_names():
    assert parse_yaml_names("train: a\nval: b\n") == {}
