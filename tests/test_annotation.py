import pytest

from core.annotation import BBox, read_label_file, save_yolo_annotations, load_yolo_annotations


# ------------------------------------------------------------------ parsing

def test_parses_axis_aligned_box():
    b = BBox.from_yolo_line("3 0.5 0.4 0.2 0.1")
    assert (b.class_id, b.x_center, b.y_center, b.width, b.height) == (3, 0.5, 0.4, 0.2, 0.1)
    assert not b.is_polygon


def test_float_class_id_is_accepted():
    assert BBox.from_yolo_line("2.0 0.5 0.5 0.1 0.1").class_id == 2


def test_parses_polygon_and_derives_bounds():
    b = BBox.from_yolo_line("1 0.1 0.2 0.5 0.2 0.5 0.6 0.1 0.6")
    assert b.is_polygon
    assert b.x_center == pytest.approx(0.3)
    assert b.y_center == pytest.approx(0.4)
    assert b.width == pytest.approx(0.4)
    assert b.height == pytest.approx(0.4)


@pytest.mark.parametrize("line", [
    "",
    "0 0.5 0.5 0.2",                 # too few values
    "0 0.5 0.5 0.2 0.2 0.3",         # 5 numbers: neither box nor polygon
    "cat 0.5 0.5 0.2 0.2",           # non-numeric class
    "0 nan 0.5 0.2 0.2",             # NaN coordinate
    "0 0.1 0.1 0.2 0.1 0.2 0.2 0.1", # odd number of polygon coords
])
def test_rejects_malformed_lines(line):
    assert BBox.from_yolo_line(line) is None


def test_yolo_line_round_trip():
    for line in ("0 0.500000 0.400000 0.200000 0.100000",
                 "4 0.100000 0.200000 0.500000 0.200000 0.500000 0.600000 0.100000 0.600000"):
        assert BBox.from_yolo_line(line).to_yolo_line() == line


# -------------------------------------------------------------- conversions

def test_pixel_round_trip():
    b = BBox.from_pixels(0, 10, 20, 50, 60, img_w=100, img_h=200)
    assert b.to_pixels(100, 200) == pytest.approx((10, 20, 50, 60))


def test_from_pixels_sorts_and_clamps_corners():
    # dragged right-to-left and past the image edge
    b = BBox.from_pixels(0, 120, 50, 80, -10, img_w=100, img_h=100)
    assert b.to_pixels(100, 100) == pytest.approx((80, 0, 100, 50))


def test_from_pixels_rejects_zero_size_image():
    with pytest.raises(ValueError):
        BBox.from_pixels(0, 0, 0, 10, 10, img_w=0, img_h=100)


def test_transformed_to_bounds_moves_polygon_with_box():
    b = BBox.from_polygon(0, [0.1, 0.1, 0.3, 0.1, 0.3, 0.3, 0.1, 0.3])
    moved = b.transformed_to_bounds(0.5, 0.5, 0.9, 0.9)   # shift + scale x2
    assert moved.polygon == pytest.approx([0.5, 0.5, 0.9, 0.5, 0.9, 0.9, 0.5, 0.9])
    assert moved.width == pytest.approx(0.4)


def test_clone_is_independent():
    b = BBox.from_polygon(0, [0.1, 0.1, 0.3, 0.1, 0.3, 0.3, 0.1, 0.3])
    c = b.clone()
    c.polygon[0] = 0.9
    c.class_id = 5
    assert b.polygon[0] == 0.1 and b.class_id == 0


# ------------------------------------------------------------------ files

def test_read_missing_file_is_empty(tmp_path):
    lf = read_label_file(tmp_path / "nope.txt")
    assert lf.boxes == [] and lf.malformed == [] and lf.is_empty


def test_read_keeps_malformed_lines_separately(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("0 0.5 0.5 0.2 0.2\n\ngarbage line\n1 0.1 0.1 0.05 0.05\n", encoding="utf-8")
    lf = read_label_file(p)
    assert [b.class_id for b in lf.boxes] == [0, 1]
    assert lf.malformed == ["garbage line"]
    assert load_yolo_annotations(p) == lf.boxes


def test_save_drops_degenerate_boxes(tmp_path):
    p = tmp_path / "sub" / "a.txt"
    save_yolo_annotations(p, [BBox(0, 0.5, 0.5, 0.2, 0.2), BBox(1, 0.5, 0.5, 0.0, 0.2)])
    assert p.read_text(encoding="utf-8") == "0 0.500000 0.500000 0.200000 0.200000\n"


def test_save_empty_list_writes_empty_file(tmp_path):
    p = tmp_path / "a.txt"
    save_yolo_annotations(p, [])
    assert p.exists() and p.read_text(encoding="utf-8") == ""
