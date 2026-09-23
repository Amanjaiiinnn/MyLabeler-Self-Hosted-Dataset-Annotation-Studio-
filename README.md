# MyLabeler — YOLO Dataset Studio

MyLabeler is a Windows desktop app for building YOLO object-detection datasets, modelled on Roboflow's workflow. You import images and YOLO labels, draw or fix boxes, auto-label with an Ultralytics YOLO model, check the dataset for problems, generate augmentations, and export a train/val (and optional test) split with a `data.yaml` that Ultralytics can train on.

Everything stays on your PC. Only two things go online, and only when you trigger them: **Publish to Roboflow**, and Ultralytics downloading a model you load by name instead of by file path.

It reads and writes both YOLO label formats, with every coordinate normalised to 0–1:

- **Axis-aligned boxes**: `class xc yc w h`
- **Oriented boxes and polygons**: `class x1 y1 x2 y2 x3 y3 x4 y4 …` (four or more points), including Roboflow `*-obb` exports

## Contents

- [Quick start](#quick-start)
- [Typical workflow](#typical-workflow)
- [Pages](#pages)
- [Auto-labelling](#auto-labelling)
- [Augmentation](#augmentation)
- [Exporting a version](#exporting-a-version)
- [Trash and undo](#trash-and-undo)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Project folders](#project-folders)
- [Settings](#settings)
- [Code structure](#code-structure)
- [Troubleshooting](#troubleshooting)
- [Known issues](#known-issues)

---

## Quick start

### Requirements

- Windows with Python 3.12
- The packages in `requirements.txt`: PySide6, ultralytics, albumentations, opencv-python, numpy, Pillow
- Optional: `roboflow`, only for **Publish to Roboflow**

Known-good versions (the `venv` in this folder): Python 3.12.4, PySide6 6.11.2, Ultralytics 8.4.121, PyTorch 2.13.0, Albumentations 2.0.8, OpenCV 5.0.0, NumPy 2.5.2, Pillow 12.3.0.

### Install

```powershell
cd path\to\Roboflow
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

Ultralytics pulls in PyTorch, so the first install is large.

### Run

```powershell
venv\Scripts\python.exe main.py
```

In VS Code, use the **MyLabeler (run app)** launch configuration; `.vscode\settings.json` already points at the venv's Python.

On start, MyLabeler opens the most recently changed project under `projects\` that has images. If there is none, it creates `projects\Default_Project`.

### Tests

```powershell
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m pytest
```

The tests in `tests\` cover `core\` only and build their datasets in a temp folder, so they never touch `projects\`. The `ui\` code, auto-labelling and Roboflow upload are not tested.

---

## Typical workflow

1. **Create or open a project** on **All Projects** (`Ctrl+N` / `Ctrl+O`).
2. **Upload** images, with their `.txt` labels if you have them.
3. **Label**: auto-label on **Dataset**, then draw or fix boxes on **Annotate**.
4. **Check**: walk the images on **Review** and scan on **Health**.
5. **Build a version** on **Versions**: apply a split, choose preprocessing, optionally generate augmentations, then **Create version**.
6. **Train** with the command shown when the export finishes:
   ```powershell
   yolo detect train data=<export folder>\data.yaml model=yolo11l.pt
   ```
7. Optionally upload the export with **Tools → Publish to Roboflow**.

---

## Pages

The sidebar has four groups: **Workspace** (All Projects), **Data** (Upload, Dataset, Annotate, Review), **Quality** (Health, Tools) and **Output** (Versions, Classes). At the bottom, **Trash** restores the last delete and **Collapse** (`Ctrl+B`) shrinks the sidebar to icons.

### All Projects

- Every folder under `projects\` (next to `main.py`) appears as a card with a thumbnail, its image count and when it was last edited.
- Search, and sort by date edited, name or image count.
- Click a card to open it. Its menu has **Open project**, **Rename…** and **Delete project…**.
- **Delete project** removes the whole folder permanently; it does not use the trash.
- **Open folder…** opens a dataset folder stored anywhere else. **New Project** creates an empty one.

### Upload

- Drop images or one dataset folder onto the page, or use **Choose files** / **Choose folder**.
- Supported images: `.jpg .jpeg .png .bmp .webp .tiff .tif`. Video isn't supported; extract frames first.
- Images are copied into the project's `images\`. A file whose name already exists there isn't copied again.
- Labels are matched by file name, in this order:
  1. the image's own folder: `photo.jpg` → `photo.txt`
  2. a `labels\` folder beside the image folder: `images\photo.jpg` → `labels\photo.txt`
  3. a `labels\` folder inside the image folder: `photo.jpg` → `labels\photo.txt`
- An import never overwrites a label the project already has.
- When you import a folder, `train\`, `valid\`/`val\` and `test\` layouts are recognised, and each image keeps its split. Class names are read from `classes.txt` or `_darknet.labels` in that folder.
- Class ids in imported labels that the project doesn't know yet are added as `class<id>`.

### Dataset

- A gallery of 60 images per page. Each card shows the boxes, the box count and a status pill:
  - **reviewed**: status *labeled*
  - **auto**: status *auto-labeled*, or boxes that haven't been reviewed
  - **no boxes**: status *unlabeled*
- Split tabs: **All, Train, Valid, Test, Unassigned**, with counts. **Rebalance…** deals images into train/valid/test by ratio (default 70/20/10, seed 42), optionally only the images that have no split yet.
- Filters: file-name search, status (All, Auto, Reviewed, Empty), class, sort (Newest, Oldest, Name), and **Boxes on/Off**.
- Tick images to show the batch bar: **Auto-label these**, **Move to** Train/Valid/Test/Unassigned, **Delete** (to the trash) and **Clear selection**.
- Toolbar: the loaded model, **Model** (load `.pt` weights), **conf**, **Auto-label** (every image with status *unlabeled*) and **Export**.
- Double-click an image to open it on **Annotate**.

### Annotate

- A filmstrip on the left (the first 400 images), the canvas in the middle, and the class list and box inspector on the right.
- **Draw** mode: drag to draw a box in the selected class. **Select** mode: click a box, drag it to move it, and drag its handles to resize it.
- The mouse wheel zooms around the cursor, and the scroll bars pan when zoomed in. `F` fits the image; `Ctrl+1` shows it at 100%.
- Right-click a box for **Change Class**, **Duplicate**, **Lock/Unlock** and **Delete**.
- The inspector edits the selected box's class and its position and size in pixels, and has lock, duplicate and delete.
- Oriented boxes and polygons are marked `◇` and keep their shape when moved or resized. New shapes you draw are always axis-aligned boxes.
- Every change is saved to the label file straight away. `Ctrl+S` saves too.
- The status button in the toolbar switches the image between **Reviewed** and **Unreviewed**.
- Class list: **+ Add Class**, **Remove**, **Rename** (or double-click) and **Color**. Clicking a class, or pressing `0`–`9` for the first ten, selects it for drawing and also changes the selected box to it.
- Undo/redo keeps 50 steps for the current image and resets when you change image.

### Review

Walk a filtered set of images quickly, in the open project or any dataset folder.

- Pick the dataset with **Current project** or **Folder…**, and optionally a split.
- **Show:** All images, Empty labels (0 boxes), Multiclass images, Malformed label lines, No label file at all, or one class.
- Each image is drawn with its boxes; the side panel shows its details and raw label lines.
- **Accept** marks the image reviewed and moves on. This is only stored for the open project.
- **Reject** sends the image and its label to the trash.
- **Accept all** and **Reject all** apply to the whole filtered set after a confirmation.
- The number keys and class buttons set **every** box in the image to that class.
- **Go to #** jumps to an image. **Open in annotator** opens it on Annotate (open project only).

| Key | Action |
|---|---|
| `←` / `→` | Previous / next image |
| `K` | Skip without a verdict |
| `A` | Accept and move on |
| `R`, `D` or `Delete` | Reject (to the trash) |
| `0`–`9` | Set every box to the class on button `[0]`–`[9]` |
| `Ctrl+Z` | Restore the last rejected image |

### Health

Scans a dataset (the open project or a folder) and fixes problems in bulk.

- Click **Scan Dataset**. Tick **Also open every image…** to catch truncated files; this is slower.
- Tiles show images, annotations, class ids and problems. The Health item in the sidebar shows the problem count from the last scan.

| Problem | What fixing does |
|---|---|
| Images with no label file | Image moves to the trash |
| Label files with no image | Label moves to the trash |
| Empty label files (0 boxes) | Image and label move to the trash |
| Label files with unparseable lines | File is rewritten without the bad lines |
| Boxes with coordinates outside 0–1 | Coordinates are clamped into range |
| Images that cannot be opened | Image and label move to the trash |

- Tick the problems to fix, click **Preview (dry run)** to list exactly what would change, then **Apply Selected Fixes**. The dataset is scanned again afterwards.
- The rewrite and clamp fixes change files in place and can't be undone; the other fixes use the trash.
- **Class distribution** lists boxes and images per class id and flags ids with no name.
- The **Trash** card has **Undo Last Delete** and **Empty Trash Permanently**.

### Tools

Works on the open project or any dataset folder, optionally a single split.

**Class tools** rewrite class ids in every label file without touching coordinates:

- Merge all classes into one
- Swap two classes
- Remap one class to another
- Delete all boxes of a class

**Preview** shows how many boxes and files would change. **Apply to Labels** rewrites the files in place, with no undo.

**Subset & split** copies part of a dataset into a new folder and never changes the original:

- Random sample of N images (with a seed; leave it blank for a different sample each run)
- Range of images, Nth to Mth (1-based, inclusive, in file-name order)
- Sequential chunks of N images, for uploading in batches
- Only images that have annotations

The copy goes into a subfolder of the output folder you choose (`random_<N>`, `range_<from>_<to>`, `chunks_<N>\chunk_1…` or `annotated_only`), each with `images\` and `labels\`.

**Publish to Roboflow** uploads a folder, usually an export, to a Roboflow project as object detection:

- Needs `roboflow`; the **Upload to Roboflow** button stays disabled until it's installed.
- Fill in the API key, workspace, project and dataset folder. **Save credentials** stores them in `settings.json`.
- If the API key box is empty, the `ROBOFLOW_API_KEY` environment variable is used.
- After an export, the dataset folder box is filled in with that export.

### Versions

Builds a trainable dataset from the project in three steps.

1. **Train / Test split**: set the ratios (default 70/20/10) and seed, optionally tick **Only images with no split yet**, then click **Apply split**.
2. **Preprocessing**, applied while the version is written (your originals aren't changed):
   - **Resize**: letterbox to 640×640 with grey padding, keeping the aspect ratio (added by default)
   - **Grayscale**
   - **Auto-contrast**: CLAHE on the luminance channel
   - **Filter null**: drop images with no boxes
   - **Random sample**: keep a random 50% of images
3. **Augmentation**: **Configure augmentations…** generates the copies straight away into `augmented\` (see [Augmentation](#augmentation)).

**Create version** opens the export dialog. **Auto-label first** labels every image with status *unlabeled*. The left panel lists existing versions with their train and val counts.

### Classes

- A table of class ids, names, colours, box counts and image counts, with search and sort.
- Tiles show classes, annotations, annotated images and **unnamed ids** (ids used in labels that have no name).
- **Add** creates a class with the next free id.
- Double-click a name to rename it, or click **Name it** for an unnamed id.
- Double-click an id to **change it**. Every label file, including `augmented\`, is rewritten; if the new id is taken, the two classes are swapped. This can't be undone.
- **Delete** removes the class and every box that uses it, including in `augmented\`. This can't be undone.
- **Close gaps** renumbers classes to 0…n-1 and rewrites the label files. This can't be undone.

---

## Auto-labelling

- Load weights with **Model** on Dataset, or **Choose model…** in the auto-label dialog. Any Ultralytics detection model works: a `.pt` file, or a model name such as `yolo11l.pt` that Ultralytics downloads on first use.
- The dialog lists every class the model knows. Tick the classes to detect and type the name each should have in your dataset; unticked classes are ignored.
- Set **Confidence** (0.05–0.95, default 0.25), and tick **Replace labels on images that already have boxes** to overwrite existing labels.
- Labels use the **model's** class ids (for a COCO model, `person` is 0 and `cell phone` is 67). The names you type are saved in the project under those ids, so the labels and `data.yaml` agree.
- Inference runs at 640 px with IoU 0.45 and writes axis-aligned boxes only.
- Labelled images get status *auto-labeled*, or *unlabeled* if nothing was found.
- Your ticked classes, names and confidence are remembered in `settings.json`.

## Augmentation

The dialog makes 1–20 copies (default 3) of **every image that has boxes**. Each copy draws its own random transforms:

| Option | On by default | Setting | Chance per copy |
|---|---|---|---|
| Horizontal flip | yes | — | 50% |
| Vertical flip | no | — | 50% |
| Rotate | no | ±15° | 60% |
| Shear | no | ±10° | 50% |
| Random crop | no | up to 10% off each side (max 40%) | 50% |
| Brightness / contrast | yes | ±0.2 | 70% |
| Hue / saturation shift | no | ±10 | 60% |
| Blur | no | kernel up to 5 | 40% |
| Gaussian noise | no | strength 0.02 | 40% |
| Cutout | no | up to 3 holes, 10% size | 50% |
| Grayscale | no | probability 0.1 | as set |

- Copies are saved as `augmented\images\<name>_aug<N><ext>` and `augmented\labels\<name>_aug<N>.txt`. Running it again overwrites copies with the same names.
- A box that ends up less than 20% visible is dropped.
- Oriented boxes and polygons are transformed point by point, so rotation and shear keep their shape.

## Exporting a version

The **Export Dataset** dialog has:

- **Export folder name** (default `v<YYYYMMDD_HHMM>`). If an export with that name exists, it's deleted and rebuilt after you confirm.
- **Validation split** (5–50%, default 20%), used for images that have no split.
- **Include augmented images** (on by default).

Output:

```
projects\<project>\exports\<version>\
├── train\images   train\labels
├── val\images     val\labels
├── test\images    test\labels     only when some images are assigned to Test
└── data.yaml
```

How images are placed:

- Only original images with at least one box are exported.
- An image's own split (set on Dataset or Versions) wins. Images without one are shuffled (seed 42) and dealt out by the validation percentage, with at least one going to val.
- **Random sample** is applied before splitting.
- Augmented copies follow their original into the same split, so a near-duplicate can't end up in both train and val.
- Pixel steps run in a fixed order (auto-contrast, grayscale, resize), and boxes are moved to match the letterbox.

`data.yaml` holds the absolute `path`, `train`, `val`, `test` (when present), and a `names` entry for every id from 0 to the highest id used. Ids used in labels but not named become `class<id>`; unused ids become `unused`. The preprocessing steps are listed as comments.

## Trash and undo

- Deleting on Dataset, Review or Health moves files to `<dataset>\.trash\<timestamp>\`, with a `manifest.json` recording where each file came from.
- `Ctrl+Shift+Z`, or **Trash** in the sidebar, restores the open project's most recent batch. Review and Health have their own **Undo** for the dataset they're working on.
- A file isn't restored if something already exists at its original path.
- **Empty Trash Permanently** (on Health) deletes every batch for good.
- These **can't** be undone: deleting a project, deleting a class, changing class ids, **Close gaps**, the class tools on Tools, and the rewrite and clamp fixes on Health.

## Keyboard shortcuts

**Anywhere**

| Key | Action |
|---|---|
| `Ctrl+O` | Open a project or dataset folder |
| `Ctrl+N` | New project |
| `Ctrl+I` | Go to Upload |
| `Ctrl+S` | Save the current image (Annotate) |
| `Ctrl+Shift+Z` | Restore the last delete |
| `Ctrl+B` | Collapse or expand the sidebar |

**Annotate** (only while the Annotate page is showing)

| Key | Action |
|---|---|
| `D` | Draw mode |
| `V` / `Esc` | Select mode |
| `←` / `→` | Previous / next image |
| `F` | Zoom to fit |
| `Ctrl+1` | Zoom to 100% |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo |
| `Ctrl+D` | Duplicate the selected box |
| `Delete` / `Backspace` | Delete the selected box |
| `L` | Lock or unlock the selected box |
| `0`–`9` | Select one of the first ten classes in the list |

**Review**: see the table under [Review](#review).

## Project folders

```
projects\<project>\
├── project.db           SQLite: images (file name, size, status, split) and classes (id, name, colour)
├── classes.txt          one class name per line; line number = class id; gaps are "__unused__"
├── images\              imported originals
├── labels\              YOLO .txt labels, same name as the image
├── augmented\images\    generated copies
├── augmented\labels\
├── exports\<version>\   exported datasets
└── .trash\<timestamp>\  deleted files and manifest.json
```

- Image status is `unlabeled`, `auto-labeled` or `labeled` (shown as *reviewed*). Split is `train`, `valid`, `test` or empty (unassigned).
- In this copy, `projects\models\` holds `yolo11l.pt`, so it also appears as a project called *models*.

**Opening a folder that isn't a project** (`Ctrl+O`):

- MyLabeler creates `project.db`, `classes.txt`, `images\`, `labels\`, `augmented\` and `exports\` inside it.
- If loose images or `.txt` files sit directly in the folder, it asks whether to move them into `images\` and `labels\`. **No** leaves them where they are, but they won't be part of the project; only files already in `images\` are indexed.
- For a dataset in `train\ valid\ test\` form, create a project and use **Upload → Choose folder**, or point Review, Health or Tools at the folder.

## Settings

`settings.json` sits next to `main.py` and is updated by the app. It's listed in `.gitignore` because it can contain your Roboflow API key.

| Key | Meaning |
|---|---|
| `model_weights`, `model_dir` | Last model loaded, and its folder |
| `confidence` | Auto-label confidence |
| `autolabel_classes`, `autolabel_names` | Classes ticked in the auto-label dialog, and the names you gave them |
| `last_dataset_dir`, `last_output_dir` | Last dataset folder picked on Review/Health/Tools, and last subset output folder |
| `roboflow_api_key`, `roboflow_workspace`, `roboflow_project` | Publish to Roboflow details |
| `theme` | Not used; the app is dark only |

## Code structure

```
Roboflow\
├── main.py                    Starts the Qt app
├── requirements.txt
├── requirements-dev.txt       requirements.txt + pytest
├── pytest.ini
├── tests\                     pytest suite for core\ (one test_<module>.py per module)
├── core\
│   ├── project.py             Project folder and SQLite index: images, classes, splits, import
│   ├── annotation.py          Box/polygon model; YOLO .txt reading and writing
│   ├── dataset_source.py      Reads any dataset layout (split folders, images/labels, flat)
│   ├── labelops.py            Health audit and fixes, class remaps, subsets, review filters
│   ├── augmentation.py        Albumentations pipeline (boxes and polygon points)
│   ├── dataset.py             Batch augmentation, preprocessing and export
│   ├── trash.py               Reversible deletes (.trash and manifest)
│   ├── workers.py             Background threads with progress and cancel
│   ├── yolo_predictor.py      Ultralytics wrapper for auto-labelling
│   ├── roboflow_sync.py       Roboflow upload
│   └── config.py              settings.json
└── ui\
    ├── main_window.py         Window, pages, shortcuts; model, auto-label and export flows
    ├── sidebar.py             Navigation
    ├── projects_view.py       All Projects
    ├── upload_view.py         Upload
    ├── dataset_view.py        Dataset gallery
    ├── annotate_view.py, canvas.py, class_panel.py, label_inspector.py    Annotate
    ├── review_view.py         Review
    ├── health_view.py         Health
    ├── tools_view.py          Tools
    ├── versions_view.py, preprocessing_dialog.py                          Versions
    ├── classes_view.py        Classes
    ├── autolabel_dialog.py, augmentation_dialog.py, export_dialog.py,
    │   rebalance_dialog.py, project_dialog.py                             Dialogs
    └── theme.py, widgets.py, icons.py                                     Styling and shared widgets
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named 'PySide6'` or `'ultralytics'` | You started a Python without the packages. Run `venv\Scripts\python.exe main.py`. |
| After `venv\Scripts\activate`, `python` still isn't the venv's Python | The venv was created in a different folder and then moved, and its activate script still points there. Run `venv\Scripts\python.exe` directly, or delete `venv` and create it again. |
| The auto-label dialog says **No model loaded** | Click **Choose model…**. The default path in `core\yolo_predictor.py` points to a folder on the original PC. |
| **Upload to Roboflow** is disabled | Run `venv\Scripts\python.exe -m pip install roboflow`, then restart the app. |
| A card shows **unreadable** | The image file is damaged. Run Health with **Also open every image…** ticked. |
| The export warns about `class<id>` names | Name those ids on **Classes**, then export again. |
| Opening a `train\ valid\ test\` dataset with `Ctrl+O` shows no images | Expected; see [Project folders](#project-folders). |

## Known issues

1. **Moving through images on Annotate marks them reviewed.** Changing image saves the previous one, and saving sets the status to *reviewed* whenever the image has boxes, so auto-labelled images lose their *auto* status without being checked.
2. **Box locks aren't saved.** YOLO label files have nowhere to store them, so they're lost when you change image.
3. **The augmentation dialog's "Apply to" choice is ignored.** Every image with boxes is augmented.
4. **Close gaps doesn't update `augmented\labels`**, so augmented copies keep the old ids. Changing an id or deleting a class does update them.
5. **Images with no boxes are never exported**, so background images can't be included, and the **Filter null** step makes no difference.
6. **Remove on the Annotate class list only removes the name.** The boxes keep the id, which comes back as `class<id>` the next time the project loads. Use **Delete** on Classes to remove the boxes too.
7. **The Upload page's "Batch name" field isn't used.**
8. **`core\yolo_predictor.py` has a default model path that only exists on the original PC** (see [Troubleshooting](#troubleshooting)).
