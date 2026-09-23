import numpy as np
import pytest

from core.annotation import BBox
from core.augmentation import AugConfig, Augmentor

ALL_OFF = dict(flip_horizontal=False, brightness_contrast=False)


def _image(h=60, w=80):
    rng = np.random.default_rng(0)
    return rng.integers(0, 255, (h, w, 3), dtype=np.uint8)


def test_all_toggles_off_is_identity():
    img = _image()
    box = BBox(0, 0.3, 0.4, 0.2, 0.2)
    out_img, [out] = Augmentor(AugConfig(**ALL_OFF)).augment_once(img, [box])
    assert np.array_equal(out_img, img)
    assert (out.x_center, out.y_center, out.width, out.height) == pytest.approx((0.3, 0.4, 0.2, 0.2))


def test_horizontal_flip_mirrors_box_or_leaves_it():
    aug = Augmentor(AugConfig(flip_horizontal=True, brightness_contrast=False))
    seen = set()
    for _ in range(30):
        _, [b] = aug.augment_once(_image(), [BBox(1, 0.3, 0.4, 0.2, 0.2)])
        assert b.class_id == 1
        assert b.y_center == pytest.approx(0.4)
        assert b.x_center == pytest.approx(0.3) or b.x_center == pytest.approx(0.7)
        seen.add(round(b.x_center, 3))
    assert seen == {0.3, 0.7}       # p=0.5 over 30 draws: both outcomes appear


def test_polygon_survives_flip_as_polygon():
    poly = BBox.from_polygon(2, [0.1, 0.2, 0.3, 0.2, 0.3, 0.5, 0.1, 0.5])
    aug = Augmentor(AugConfig(flip_horizontal=True, brightness_contrast=False))
    for _ in range(10):
        _, [b] = aug.augment_once(_image(), [poly])
        assert b.is_polygon and b.class_id == 2
        assert b.width == pytest.approx(0.2, abs=0.02)
        assert b.x_center == pytest.approx(0.2, abs=0.02) or b.x_center == pytest.approx(0.8, abs=0.02)


def test_heavy_pipeline_keeps_boxes_in_range():
    cfg = AugConfig(flip_vertical=True, rotate=True, crop=True, shear=True,
                    blur=True, noise=True, cutout=True, hue_saturation=True)
    aug = Augmentor(cfg)
    boxes = [BBox(0, 0.5, 0.5, 0.3, 0.3), BBox(1, 0.2, 0.2, 0.1, 0.1)]
    for _ in range(20):
        img, out = aug.augment_once(_image(), boxes)
        assert img.ndim == 3
        for b in out:
            assert 0.0 <= b.x_center - b.width / 2 + 1e-6
            assert b.x_center + b.width / 2 <= 1.0 + 1e-6
            assert 0.0 <= b.y_center - b.height / 2 + 1e-6
            assert b.y_center + b.height / 2 <= 1.0 + 1e-6


def test_generate_returns_n_variants(tmp_path):
    from PIL import Image
    path = tmp_path / "a.jpg"
    Image.fromarray(_image()).save(path)
    variants = Augmentor(AugConfig()).generate(path, [BBox(0, 0.5, 0.5, 0.2, 0.2)], 3)
    assert len(variants) == 3
    assert all(img.shape == (60, 80, 3) for img, _ in variants)


def test_generate_rejects_unreadable_image(tmp_path):
    path = tmp_path / "bad.jpg"
    path.write_bytes(b"nope")
    with pytest.raises(OSError):
        Augmentor(AugConfig()).generate(path, [], 1)
