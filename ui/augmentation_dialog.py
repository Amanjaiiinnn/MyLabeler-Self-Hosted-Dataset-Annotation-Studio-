"""ui/augmentation_dialog.py - Roboflow-style 'Generate' dialog for augmentations."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QCheckBox,
    QSpinBox, QDoubleSpinBox, QLabel, QPushButton, QComboBox, QDialogButtonBox,
)

from core.augmentation import AugConfig


class AugmentationDialog(QDialog):
    def __init__(self, parent=None, image_count: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Generate Augmented Dataset")
        self.resize(480, 560)
        self.result_config: AugConfig | None = None
        self.result_scope: str = "all"
        self.result_variants: int = 3

        layout = QVBoxLayout(self)

        scope_box = QGroupBox("Apply to")
        scope_layout = QHBoxLayout(scope_box)
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["All labeled images", "Selected images only", "Current image only"])
        scope_layout.addWidget(self.scope_combo)
        layout.addWidget(scope_box)

        variants_box = QGroupBox("Variants per image")
        v_layout = QHBoxLayout(variants_box)
        self.variants_spin = QSpinBox()
        self.variants_spin.setRange(1, 20)
        self.variants_spin.setValue(3)
        v_layout.addWidget(QLabel("Generate"))
        v_layout.addWidget(self.variants_spin)
        v_layout.addWidget(QLabel("augmented copies per image"))
        layout.addWidget(variants_box)

        aug_box = QGroupBox("Augmentations")
        grid = QGridLayout(aug_box)
        row = 0

        self.cb_hflip = QCheckBox("Horizontal Flip")
        self.cb_hflip.setChecked(True)
        grid.addWidget(self.cb_hflip, row, 0); row += 1

        self.cb_vflip = QCheckBox("Vertical Flip")
        grid.addWidget(self.cb_vflip, row, 0); row += 1

        self.cb_rotate = QCheckBox("Rotate ±")
        self.rotate_spin = QSpinBox(); self.rotate_spin.setRange(1, 90); self.rotate_spin.setValue(15)
        grid.addWidget(self.cb_rotate, row, 0); grid.addWidget(self.rotate_spin, row, 1)
        grid.addWidget(QLabel("degrees"), row, 2); row += 1

        self.cb_shear = QCheckBox("Shear ±")
        self.shear_spin = QSpinBox(); self.shear_spin.setRange(1, 45); self.shear_spin.setValue(10)
        grid.addWidget(self.cb_shear, row, 0); grid.addWidget(self.shear_spin, row, 1)
        grid.addWidget(QLabel("degrees"), row, 2); row += 1

        self.cb_crop = QCheckBox("Random Crop (bbox-safe), up to")
        self.crop_spin = QSpinBox(); self.crop_spin.setRange(1, 50); self.crop_spin.setValue(10)
        grid.addWidget(self.cb_crop, row, 0); grid.addWidget(self.crop_spin, row, 1)
        grid.addWidget(QLabel("%"), row, 2); row += 1

        self.cb_bright = QCheckBox("Brightness / Contrast ±")
        self.bright_spin = QDoubleSpinBox(); self.bright_spin.setRange(0.05, 1.0)
        self.bright_spin.setSingleStep(0.05); self.bright_spin.setValue(0.2)
        self.cb_bright.setChecked(True)
        grid.addWidget(self.cb_bright, row, 0); grid.addWidget(self.bright_spin, row, 1); row += 1

        self.cb_hue = QCheckBox("Hue / Saturation shift ±")
        self.hue_spin = QSpinBox(); self.hue_spin.setRange(1, 50); self.hue_spin.setValue(10)
        grid.addWidget(self.cb_hue, row, 0); grid.addWidget(self.hue_spin, row, 1)
        grid.addWidget(QLabel("deg"), row, 2); row += 1

        self.cb_blur = QCheckBox("Blur, kernel up to")
        self.blur_spin = QSpinBox(); self.blur_spin.setRange(3, 15); self.blur_spin.setValue(5)
        grid.addWidget(self.cb_blur, row, 0); grid.addWidget(self.blur_spin, row, 1); row += 1

        self.cb_noise = QCheckBox("Gaussian Noise, strength")
        self.noise_spin = QDoubleSpinBox(); self.noise_spin.setRange(0.01, 0.2)
        self.noise_spin.setSingleStep(0.01); self.noise_spin.setValue(0.02)
        grid.addWidget(self.cb_noise, row, 0); grid.addWidget(self.noise_spin, row, 1); row += 1

        self.cb_cutout = QCheckBox("Cutout, count")
        self.cutout_count_spin = QSpinBox(); self.cutout_count_spin.setRange(1, 10); self.cutout_count_spin.setValue(3)
        self.cutout_size_spin = QSpinBox(); self.cutout_size_spin.setRange(2, 30); self.cutout_size_spin.setValue(10)
        grid.addWidget(self.cb_cutout, row, 0); grid.addWidget(self.cutout_count_spin, row, 1)
        grid.addWidget(QLabel("size %"), row, 2); grid.addWidget(self.cutout_size_spin, row, 3); row += 1

        self.cb_gray = QCheckBox("Grayscale, probability")
        self.gray_spin = QDoubleSpinBox(); self.gray_spin.setRange(0.05, 1.0)
        self.gray_spin.setSingleStep(0.05); self.gray_spin.setValue(0.1)
        grid.addWidget(self.cb_gray, row, 0); grid.addWidget(self.gray_spin, row, 1); row += 1

        layout.addWidget(aug_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        cfg = AugConfig(
            flip_horizontal=self.cb_hflip.isChecked(),
            flip_vertical=self.cb_vflip.isChecked(),
            rotate=self.cb_rotate.isChecked(), rotate_degrees=self.rotate_spin.value(),
            shear=self.cb_shear.isChecked(), shear_degrees=self.shear_spin.value(),
            crop=self.cb_crop.isChecked(), crop_percent=self.crop_spin.value(),
            brightness_contrast=self.cb_bright.isChecked(),
            brightness_limit=self.bright_spin.value(), contrast_limit=self.bright_spin.value(),
            hue_saturation=self.cb_hue.isChecked(),
            hue_shift=self.hue_spin.value(), sat_shift=self.hue_spin.value(),
            blur=self.cb_blur.isChecked(), blur_limit=self.blur_spin.value(),
            noise=self.cb_noise.isChecked(), noise_strength=self.noise_spin.value(),
            cutout=self.cb_cutout.isChecked(), cutout_count=self.cutout_count_spin.value(),
            cutout_size_percent=self.cutout_size_spin.value(),
            grayscale=self.cb_gray.isChecked(), grayscale_prob=self.gray_spin.value(),
        )
        self.result_config = cfg
        self.result_variants = self.variants_spin.value()
        scope_map = {0: "all", 1: "selected", 2: "current"}
        self.result_scope = scope_map[self.scope_combo.currentIndex()]
        self.accept()
