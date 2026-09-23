import pytest

from core.project import ProjectManager
from tests.conftest import add_labeled_image, make_image, write_label


# ------------------------------------------------------------------ setup

def test_create_builds_folder_layout(project):
    for d in (project.images_dir, project.labels_dir, project.aug_images_dir,
              project.aug_labels_dir, project.exports_dir):
        assert d.is_dir()
    assert project.db_path.exists()
    assert (project.root / "classes.txt").exists()


def test_create_refuses_existing_folder(tmp_path, project):
    with pytest.raises(FileExistsError):
        ProjectManager.create(tmp_path, "proj")


def test_open_does_not_move_loose_files_by_default(tmp_path):
    root = tmp_path / "loose"
    make_image(root / "a.jpg")
    write_label(root / "a.txt", ["0 0.5 0.5 0.1 0.1"])
    pm = ProjectManager.open(root)
    try:
        assert (root / "a.jpg").exists()
        assert pm.get_images() == []
    finally:
        pm.close()


def test_open_adopts_loose_files_when_asked(tmp_path):
    root = tmp_path / "loose"
    make_image(root / "a.jpg")
    write_label(root / "a.txt", ["2 0.5 0.5 0.1 0.1"])
    (root / "readme.txt").write_text("notes", encoding="utf-8")

    images, labels = ProjectManager.scan_loose_files(root)
    assert [p.name for p in images] == ["a.jpg"]
    assert [p.name for p in labels] == ["a.txt"]          # readme.txt is reserved

    pm = ProjectManager.open(root, adopt_loose_files=True)
    try:
        assert (root / "images" / "a.jpg").exists()
        assert (root / "labels" / "a.txt").exists()
        assert (root / "readme.txt").exists()
        assert pm.get_image("a.jpg")["status"] == "labeled"
        assert (2, "class2") in [(c[0], c[1]) for c in pm.get_classes()]
    finally:
        pm.close()


def test_reopen_keeps_data(tmp_path, project):
    project.add_class("cat")
    add_labeled_image(project, "a.jpg", ["0 0.5 0.5 0.1 0.1"])
    project.close()

    pm = ProjectManager.open(project.root)
    try:
        assert [c[1] for c in pm.get_classes()] == ["cat"]
        assert pm.get_image("a.jpg") is not None
    finally:
        pm.close()


# ---------------------------------------------------------------- classes

def test_add_class_assigns_sequential_ids(project):
    assert project.add_class("cat") == 0
    assert project.add_class("dog") == 1
    assert [c[1] for c in project.get_classes()] == ["cat", "dog"]


def test_classes_txt_marks_gaps_unused(project):
    for name in ("cat", "dog", "bird"):
        project.add_class(name)
    project.remove_class(1)
    lines = (project.root / "classes.txt").read_text(encoding="utf-8").splitlines()
    assert lines == ["cat", "__unused__", "bird"]


def test_rename_class(project):
    cid = project.add_class("cat")
    project.rename_class(cid, "kitten")
    assert project.get_classes()[0][1] == "kitten"


def test_ensure_class(project):
    assert project.ensure_class(3, "car") is True
    assert project.ensure_class(3, "other") is False
    assert project.get_classes()[0][:2] == (3, "car")


def test_sync_classes_from_labels_uses_hint(project):
    add_labeled_image(project, "a.jpg", ["0 0.5 0.5 0.1 0.1", "9 0.2 0.2 0.1 0.1"])
    added = project.sync_classes_from_labels(names_hint={9: "traffic light"})
    assert added == [0, 9]
    assert dict((c[0], c[1]) for c in project.get_classes()) == {
        0: "class0", 9: "traffic light"}


# ----------------------------------------------------------------- images

def test_import_images_picks_up_neighbouring_labels(tmp_path, project):
    src = tmp_path / "incoming"
    make_image(src / "images" / "a.jpg", size=(80, 60))
    make_image(src / "images" / "b.jpg")
    write_label(src / "labels" / "a.txt", ["1 0.5 0.5 0.1 0.1"])

    added = project.import_images([str(src / "images" / "a.jpg"),
                                   str(src / "images" / "b.jpg"),
                                   str(src / "notes.md")])
    assert added == 2
    a = project.get_image("a.jpg")
    assert (a["width"], a["height"], a["status"]) == (80, 60, "labeled")
    assert project.get_image("b.jpg")["status"] == "unlabeled"
    assert 1 in [c[0] for c in project.get_classes()]


def test_import_folder_keeps_splits(tmp_path, project):
    src = tmp_path / "export"
    make_image(src / "train" / "images" / "a.jpg")
    make_image(src / "valid" / "images" / "b.jpg")
    write_label(src / "train" / "labels" / "a.txt", ["0 0.5 0.5 0.1 0.1"])

    result = project.import_folder(str(src))
    assert result["images"] == 2 and result["layout"] == "split"
    assert project.get_image("a.jpg")["split"] == "train"
    assert project.get_image("b.jpg")["split"] == "valid"


def test_get_images_filters(project):
    add_labeled_image(project, "cat_1.jpg", ["0 0.5 0.5 0.1 0.1"])
    make_image(project.image_path("dog_1.jpg"))
    project._sync_existing_files()

    assert [r["filename"] for r in project.get_images(filter_text="cat")] == ["cat_1.jpg"]
    assert [r["filename"] for r in project.get_images(filter_status="unlabeled")] == ["dog_1.jpg"]
    assert project.stats() == {"total": 2, "labeled": 1, "auto-labeled": 0, "unlabeled": 1}


def test_count_boxes(project):
    add_labeled_image(project, "a.jpg", ["0 0.5 0.5 0.1 0.1", "", "1 0.2 0.2 0.1 0.1"])
    assert project.count_boxes("a.jpg") == 2
    assert project.count_boxes("missing.jpg") == 0


def test_delete_and_undo(project):
    add_labeled_image(project, "a.jpg", ["0 0.5 0.5 0.1 0.1"])
    assert project.delete_image("a.jpg") == 2
    assert project.get_image("a.jpg") is None
    assert not project.image_path("a.jpg").exists()

    assert project.undo_last_delete() == 2
    assert project.image_path("a.jpg").exists()
    assert project.get_image("a.jpg")["status"] == "labeled"


# ----------------------------------------------------------------- splits

def _add_plain(project, n):
    for i in range(n):
        make_image(project.image_path(f"img{i:02d}.jpg"))
    project._sync_existing_files()


def test_set_split_rejects_unknown_values(project):
    _add_plain(project, 1)
    project.set_split("img00.jpg", "train")
    assert project.get_image("img00.jpg")["split"] == "train"
    project.set_split("img00.jpg", "banana")
    assert project.get_image("img00.jpg")["split"] == ""


def test_rebalance_splits(project):
    _add_plain(project, 10)
    assert project.rebalance_splits(7, 2, 1) == {"train": 7, "valid": 2, "test": 1}
    counts = project.split_counts()
    assert (counts["train"], counts["valid"], counts["test"], counts["default"]) == (7, 2, 1, 0)
    assert counts["all"] == 10


def test_rebalance_is_seeded(project):
    _add_plain(project, 10)
    project.rebalance_splits(seed=3)
    first = project.images_for_split("valid")
    project.rebalance_splits(seed=3)
    assert project.images_for_split("valid") == first


def test_rebalance_only_unassigned(project):
    _add_plain(project, 5)
    project.set_split("img00.jpg", "test")
    project.rebalance_splits(1, 0, 0, only_unassigned=True)
    assert project.get_image("img00.jpg")["split"] == "test"
    assert project.split_counts()["train"] == 4


def test_rebalance_rejects_zero_ratios(project):
    with pytest.raises(ValueError):
        project.rebalance_splits(0, 0, 0)


# --------------------------------------------------------------- metadata

def test_describe_and_list_projects(tmp_path, project):
    project.add_class("cat")
    add_labeled_image(project, "a.jpg", ["0 0.5 0.5 0.1 0.1"])
    (tmp_path / ".hidden").mkdir()

    info = ProjectManager.describe(project.root)
    assert info["name"] == "proj" and info["images"] == 1
    assert info["classes"] == ["cat"] and info["is_project"]
    assert info["thumbnail"].name == "a.jpg"

    assert [p["name"] for p in ProjectManager.list_projects(tmp_path)] == ["proj"]
