# Research: Linking PDF Technical Drawing Annotations to 3D CAD Model Features

## Table of Contents
1. [Parsing STEP/CAD Files](#1-parsing-stepcad-files)
2. [Extracting Annotations from Technical PDF Drawings](#2-extracting-annotations-from-technical-pdf-drawings)
3. [NIST PMI Dataset](#3-nist-pmi-dataset)
4. [Existing Open-Source Projects](#4-existing-open-source-projects)
5. [Recommended Architecture](#5-recommended-architecture)

---

## 1. Parsing STEP/CAD Files

### 1.1 PythonOCC (pythonocc-core) — RECOMMENDED

**What it is:** Python bindings for Open CASCADE Technology (OCCT), the industrial-strength B-Rep CAD kernel. This is the most powerful and complete option.

**Installation:**
```bash
# Conda is the ONLY supported installation method (no pip)
conda create --name=pyoccenv python=3.12
conda activate pyoccenv
conda install -c conda-forge pythonocc-core=7.9.3
```

**Supported Python versions:** 3.10, 3.11, 3.12, 3.13, 3.14

**Key capabilities:**
- Read STEP AP203/AP214/AP242 files natively
- Traverse B-Rep topology (solids → shells → faces → edges → vertices)
- Identify face surface types (plane, cylinder, cone, sphere, torus, B-spline)
- Extract geometric properties: center, radius, axis direction for cylindrical faces
- Access face IDs and names from STEP files
- Compute bounding boxes, surface areas, volumes
- PMI/annotation support for AP242 files (semantic & graphic)

**Code: Read STEP and extract all cylindrical faces with properties:**
```python
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core.GeomAbs import (GeomAbs_Cylinder, GeomAbs_Plane,
                               GeomAbs_Cone, GeomAbs_Sphere)
from OCC.Core.TopoDS import topods
from OCC.Core.BRep import BRep_Tool
from OCC.Core.GProp import GProp_GProps
from OCC.Core.BRepGProp import brepgprop

def read_step(filepath):
    """Read a STEP file and return the shape."""
    reader = STEPControl_Reader()
    status = reader.ReadFile(filepath)
    if status != 1:  # IFSelect_RetDone
        raise Exception(f"Error reading STEP file: {filepath}")
    reader.TransferRoots()
    shape = reader.OneShape()
    return shape

def extract_cylindrical_faces(shape):
    """Extract all cylindrical faces and their geometric properties."""
    cylinders = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_id = 0

    while explorer.More():
        face = topods.Face(explorer.Current())
        surf_adaptor = BRepAdaptor_Surface(face)
        surf_type = surf_adaptor.GetType()

        if surf_type == GeomAbs_Cylinder:
            # Get the underlying cylinder geometry
            cylinder = surf_adaptor.Cylinder()
            axis = cylinder.Axis()
            location = axis.Location()
            direction = axis.Direction()
            radius = cylinder.Radius()

            # Compute face area (useful for estimating depth)
            props = GProp_GProps()
            brepgprop.SurfaceProperties(face, props)
            area = props.Mass()

            # Estimate depth from area and radius: A = 2*pi*r*h => h = A/(2*pi*r)
            import math
            estimated_depth = area / (2 * math.pi * radius) if radius > 0 else 0

            cylinders.append({
                "face_id": face_id,
                "radius": radius,
                "diameter": radius * 2,
                "center": (location.X(), location.Y(), location.Z()),
                "axis_direction": (direction.X(), direction.Y(), direction.Z()),
                "surface_area": area,
                "estimated_depth": estimated_depth,
            })

        face_id += 1
        explorer.Next()

    return cylinders

# Usage
shape = read_step("model.step")
holes = extract_cylindrical_faces(shape)
for h in holes:
    print(f"Face {h['face_id']}: D={h['diameter']:.2f}mm, "
          f"center={h['center']}, axis={h['axis_direction']}, "
          f"depth~{h['estimated_depth']:.2f}mm")
```

**Code: Get face names/IDs from STEP file entity labels:**
```python
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.TDocStd import TDocStd_Document
from OCC.Core.XCAFDoc import XCAFDoc_ShapeTool, XCAFDoc_DocumentTool
from OCC.Core.STEPCAFControl import STEPCAFControl_Reader
from OCC.Core.TDF import TDF_LabelSequence
from OCC.Core.TCollection import TCollection_ExtendedString

def read_step_with_names(filepath):
    """Read STEP with XCAF to preserve names and structure."""
    doc = TDocStd_Document(TCollection_ExtendedString("pythonocc-doc"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    status = reader.ReadFile(filepath)
    if status != 1:
        raise Exception("Failed to read STEP file")
    reader.Transfer(doc)

    shape_tool = XCAFDoc_DocumentTool.ShapeTool(doc.Main())
    labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(labels)

    return doc, shape_tool, labels
```

**Limitations:**
- Installation ONLY via conda (not pip)
- Large dependency footprint (~500MB+ with OCCT)
- Steep learning curve due to OCCT API complexity
- 3D visualization requires a display backend (can be disabled for headless use)


### 1.2 CadQuery

**What it is:** A higher-level parametric CAD library built on top of OCCT. Easier API but less control for analysis tasks.

**Installation:**
```bash
# Conda (recommended)
conda install -c conda-forge cadquery

# Pip (also works)
pip install cadquery
```

**Supported Python:** 3.9-3.12

**Key capabilities:**
- Import STEP files easily
- Higher-level selectors for filtering faces by type, position, direction
- Built-in hole creation (useful for understanding hole geometry)
- Sits on top of OCCT so can drop down to OCC API when needed

**Code: Import STEP and filter faces:**
```python
import cadquery as cq
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core.GeomAbs import GeomAbs_Cylinder

# Import STEP file
result = cq.importers.importStep("model.step")

# Get all faces
all_faces = result.faces().vals()
print(f"Total faces: {len(all_faces)}")

# Filter cylindrical faces using the underlying OCCT API
cylindrical_faces = []
for face in all_faces:
    adaptor = BRepAdaptor_Surface(face.wrapped)
    if adaptor.GetType() == GeomAbs_Cylinder:
        cyl = adaptor.Cylinder()
        radius = cyl.Radius()
        loc = cyl.Axis().Location()
        dir = cyl.Axis().Direction()
        cylindrical_faces.append({
            "radius": radius,
            "center": (loc.X(), loc.Y(), loc.Z()),
            "axis": (dir.X(), dir.Y(), dir.Z()),
        })

print(f"Found {len(cylindrical_faces)} cylindrical faces (potential holes)")
for cf in cylindrical_faces:
    print(f"  R={cf['radius']:.3f}, center={cf['center']}, axis={cf['axis']}")
```

**Code: Use CadQuery selectors for quick filtering:**
```python
import cadquery as cq

result = cq.importers.importStep("model.step")

# CadQuery has built-in selectors for face types
# Filter faces pointing in Z direction (top/bottom faces)
top_faces = result.faces(">Z")

# Filter faces by area (small circular faces are likely holes)
small_faces = result.faces().filter(lambda f: f.Area() < 100)

# Get edges of a face to check if it's circular
for face in result.faces().vals():
    edges = face.Edges()
    # Circular edges suggest holes
```

**Limitations:**
- Cannot import parametric data from STEP (only geometry)
- Selectors are powerful for modeling but limited for analysis
- Must drop to OCCT API for detailed geometric queries
- Less documentation for analysis workflows (more focused on CAD creation)


### 1.3 FreeCAD Python API

**What it is:** FreeCAD's built-in Python scripting environment. Can be used headless.

**Installation:**
```bash
# Conda
conda install -c conda-forge freecad

# Or install FreeCAD and use its bundled Python
# Download from: https://www.freecad.org/downloads.php

# For headless scripting on Linux:
# sudo apt install freecad-python3
```

**Key capabilities:**
- Full STEP/IGES/BREP import
- Access to face Surface types (Plane, Cylinder, Cone, etc.)
- Rich scripting environment with Part workbench
- Can run headless for batch processing

**Code: Import STEP and find cylinders:**
```python
import FreeCAD
import Part
import Import

# Load STEP file
shape = Part.read("model.step")

# Iterate all faces and find cylinders
cylinders = []
for i, face in enumerate(shape.Faces):
    surface = face.Surface

    # Check if the surface is a Cylinder
    if hasattr(surface, 'Radius') and surface.TypeId == 'Part::GeomCylinder':
        center = surface.Center   # FreeCAD.Vector
        axis = surface.Axis       # FreeCAD.Vector
        radius = surface.Radius

        # Get face area to estimate depth
        area = face.Area
        import math
        depth = area / (2 * math.pi * radius) if radius > 0 else 0

        cylinders.append({
            "face_index": i,
            "radius": radius,
            "diameter": radius * 2,
            "center": (center.x, center.y, center.z),
            "axis": (axis.x, axis.y, axis.z),
            "area": area,
            "estimated_depth": depth,
        })

for c in cylinders:
    print(f"Face {c['face_index']}: D={c['diameter']:.2f}, "
          f"center={c['center']}, depth~{c['estimated_depth']:.2f}")
```

**Code: Alternative approach using shape analysis:**
```python
import FreeCAD
import Part

shape = Part.read("model.step")

# Explore the topology
print(f"Solids: {len(shape.Solids)}")
print(f"Shells: {len(shape.Shells)}")
print(f"Faces: {len(shape.Faces)}")
print(f"Edges: {len(shape.Edges)}")

for face in shape.Faces:
    surf = face.Surface
    surf_type = surf.TypeId
    print(f"  Face type: {surf_type}")

    if "Cylinder" in surf_type:
        print(f"    Radius: {surf.Radius}")
        print(f"    Center: {surf.Center}")
        print(f"    Axis: {surf.Axis}")
    elif "Plane" in surf_type:
        print(f"    Position: {surf.Position}")
        print(f"    Normal: {face.normalAt(0, 0)}")
```

**Limitations:**
- Requires FreeCAD installation (heavy ~1GB+)
- FreeCAD Python environment can conflict with other packages
- Headless mode setup can be tricky on some platforms
- Slower than raw pythonocc for batch processing
- During STEP conversion, explicit cylinder information is lost; must check surface types


### 1.4 Comparison Table

| Feature | PythonOCC | CadQuery | FreeCAD |
|---------|-----------|----------|---------|
| Install method | conda only | conda/pip | conda/installer |
| Dependency size | ~500MB | ~500MB | ~1GB |
| STEP reading | Native | Via OCCT | Native |
| Face type detection | Yes | Via OCCT | Yes |
| Cylinder properties | Full | Via OCCT | Full |
| Named entities | Via XCAF | Limited | Yes |
| PMI/annotation read | AP242 | No | Limited |
| Headless operation | Yes | Yes | Tricky |
| Learning curve | Steep | Medium | Medium |
| Best for | Deep analysis | Quick prototyping | Interactive use |

**Recommendation for hackathon:** Use **PythonOCC** directly for maximum control over geometry extraction, or **CadQuery** if you want a quicker start with the option to drop down to OCCT when needed.

---

## 2. Extracting Annotations from Technical PDF Drawings

### 2.1 PyMuPDF (fitz) — RECOMMENDED for text-native PDFs

**What it is:** Fast, full-featured PDF library. Best for extracting text with precise bounding box positions from vector PDFs (not scanned).

**Installation:**
```bash
pip install PyMuPDF
```

**Key capabilities:**
- Extract text with exact bounding box coordinates (x0, y0, x1, y1)
- Get font name, size, color for each text span
- Access PDF annotations natively
- Built-in OCR support via Tesseract integration
- Convert pages to images for further processing
- Search text with regex patterns

**Code: Extract all text blocks with positions:**
```python
import fitz  # PyMuPDF

def extract_text_with_positions(pdf_path):
    """Extract all text elements with their bounding boxes."""
    doc = fitz.open(pdf_path)
    all_annotations = []

    for page_num, page in enumerate(doc):
        # "dict" mode gives full detail: blocks -> lines -> spans
        text_dict = page.get_text("dict")

        for block in text_dict["blocks"]:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    for span in line["spans"]:
                        all_annotations.append({
                            "page": page_num,
                            "text": span["text"],
                            "bbox": span["bbox"],  # (x0, y0, x1, y1)
                            "font": span["font"],
                            "size": span["size"],
                            "color": span["color"],
                            "origin": span["origin"],  # (x, y) baseline
                        })

    doc.close()
    return all_annotations

# Usage
annotations = extract_text_with_positions("drawing.pdf")
for ann in annotations:
    print(f"[{ann['bbox']}] {ann['text']} (font={ann['font']}, size={ann['size']})")
```

**Code: Extract text + search for thread/tolerance patterns:**
```python
import fitz
import re

# Patterns for engineering annotations
PATTERNS = {
    "thread_metric": re.compile(
        r'M(\d+(?:\.\d+)?)'           # M followed by diameter
        r'(?:\s*[xX×]\s*'             # optional pitch separator
        r'(\d+(?:\.\d+)?))?'          # optional pitch
        r'(?:\s*[-–]\s*'              # optional tolerance separator
        r'(\d[A-Za-z]\d?[A-Za-z]?))?'  # optional tolerance class (e.g., 6H, 6g)
    ),
    "hole_tolerance": re.compile(
        r'[HhJjKkMmNnPpRrSsTtUu]'    # tolerance letter
        r'([0-9]{1,2})'               # tolerance grade
    ),
    "fit_spec": re.compile(
        r'([A-Z]\d{1,2})\s*/\s*'      # hole tolerance
        r'([a-z]\d{1,2})'             # shaft tolerance
    ),
    "diameter_symbol": re.compile(
        r'[⌀Øø∅]\s*(\d+(?:\.\d+)?)'   # diameter symbol + value
    ),
    "depth_symbol": re.compile(
        r'[↧⌴]\s*(\d+(?:\.\d+)?)'     # depth symbol + value
    ),
    "counterbore": re.compile(
        r'[⌳]\s*(\d+(?:\.\d+)?)'      # counterbore symbol + value
    ),
    "countersink": re.compile(
        r'[⌵]\s*(\d+(?:\.\d+)?)'      # countersink symbol + value
    ),
    "dimension": re.compile(
        r'(\d+(?:\.\d+)?)\s*'          # nominal value
        r'(?:[±]\s*(\d+(?:\.\d+)?))?'  # optional symmetric tolerance
    ),
    "gdt_tolerance": re.compile(
        r'[⏤⏥○⌭⌒⌓⏊∠⫽⌯⌖◎↗⌰]'  # GD&T symbols
    ),
}

def find_engineering_annotations(pdf_path):
    """Find thread callouts, tolerances, and GD&T in a PDF."""
    doc = fitz.open(pdf_path)
    results = []

    for page_num, page in enumerate(doc):
        # Get text blocks with positions
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                line_text = ""
                line_bbox = list(line["bbox"])
                for span in line["spans"]:
                    line_text += span["text"]

                # Check each pattern
                for pattern_name, pattern in PATTERNS.items():
                    for match in pattern.finditer(line_text):
                        results.append({
                            "page": page_num,
                            "type": pattern_name,
                            "text": match.group(0),
                            "full_line": line_text.strip(),
                            "match_groups": match.groups(),
                            "bbox": tuple(line_bbox),
                        })

    doc.close()
    return results

# Usage
annotations = find_engineering_annotations("drawing.pdf")
for ann in annotations:
    print(f"[{ann['type']}] '{ann['text']}' at bbox={ann['bbox']}")
    if ann['type'] == 'thread_metric':
        groups = ann['match_groups']
        print(f"  Diameter: M{groups[0]}, Pitch: {groups[1]}, Tolerance: {groups[2]}")
```

**Code: Extract PDF native annotations (markup/comments):**
```python
import fitz

doc = fitz.open("drawing.pdf")
for page in doc:
    # Get native PDF annotations (comments, markups, etc.)
    for annot in page.annots():
        print(f"Type: {annot.type}, Rect: {annot.rect}, "
              f"Content: {annot.info.get('content', '')}")
```

**Limitations:**
- GD&T symbols may not be in standard Unicode (could be custom fonts)
- Scanned/rasterized PDFs need OCR fallback
- Complex leader lines and callout arrows not directly accessible as text
- Font-encoded special symbols (diameter, depth) vary by CAD export


### 2.2 pdfplumber — Good for structured layouts

**What it is:** Plumbs PDFs for detailed info about characters, rectangles, lines. Great for table extraction.

**Installation:**
```bash
pip install pdfplumber
```

**Key capabilities:**
- Character-level extraction with position, font, size
- Line/rectangle detection (useful for title blocks, feature control frames)
- Table extraction with structure detection
- Visual debugging (renders pages with extracted elements highlighted)

**Code: Extract characters with positions and detect patterns:**
```python
import pdfplumber
import re

def extract_annotations_pdfplumber(pdf_path):
    """Extract text with positions using pdfplumber."""
    annotations = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            # Get all characters with positions
            chars = page.chars
            # Group chars into words by proximity
            words = page.extract_words(
                x_tolerance=3,
                y_tolerance=3,
                keep_blank_chars=False,
            )

            for word in words:
                annotations.append({
                    "page": page_num,
                    "text": word["text"],
                    "x0": word["x0"],
                    "y0": word["top"],
                    "x1": word["x1"],
                    "y1": word["bottom"],
                    "font": word.get("fontname", ""),
                    "size": word.get("size", 0),
                })

            # Also extract lines and rectangles
            # (useful for detecting feature control frames)
            lines = page.lines
            rects = page.rects
            for rect in rects:
                annotations.append({
                    "page": page_num,
                    "type": "rectangle",
                    "x0": rect["x0"],
                    "y0": rect["top"],
                    "x1": rect["x1"],
                    "y1": rect["bottom"],
                })

    return annotations

# Usage
data = extract_annotations_pdfplumber("drawing.pdf")
for item in data:
    if "text" in item:
        print(f"Word: '{item['text']}' at ({item['x0']:.1f}, {item['y0']:.1f})")
```

**Code: Visual debug — render page with extractions highlighted:**
```python
import pdfplumber

with pdfplumber.open("drawing.pdf") as pdf:
    page = pdf.pages[0]
    # Create debug image showing all detected elements
    img = page.to_image(resolution=150)
    img.draw_rects(page.rects)
    img.draw_lines(page.lines)
    img.draw_chars(page.chars)
    img.save("debug_output.png")
```

**Limitations:**
- Slower than PyMuPDF for large PDFs
- No built-in OCR
- Character grouping into words can be imperfect for engineering annotations
- Cannot handle scanned/rasterized PDFs


### 2.3 pdf2image + Tesseract OCR — For scanned/rasterized drawings

**What it is:** Convert PDF to images, then run OCR. Necessary for scanned drawings.

**Installation:**
```bash
pip install pdf2image pytesseract Pillow opencv-python
# Also install Tesseract OCR system package:
# Windows: download from https://github.com/UB-Mannheim/tesseract/wiki
# Linux: sudo apt install tesseract-ocr
# Mac: brew install tesseract
```

**Key capabilities:**
- Handle scanned/rasterized PDF drawings
- Get word-level bounding boxes from OCR
- Configurable OCR parameters for engineering text
- Works with any image-based PDF

**Code: OCR with bounding boxes for engineering drawings:**
```python
from pdf2image import convert_from_path
import pytesseract
import cv2
import numpy as np
import re

def ocr_engineering_drawing(pdf_path, dpi=300):
    """OCR a PDF drawing and extract text with bounding boxes."""
    # Convert PDF to images
    images = convert_from_path(pdf_path, dpi=dpi)
    results = []

    for page_num, pil_image in enumerate(images):
        # Convert to OpenCV format
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        # Optional: preprocess for better OCR
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Adaptive threshold helps with engineering drawings
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Get word-level data with bounding boxes
        data = pytesseract.image_to_data(
            thresh,
            output_type=pytesseract.Output.DICT,
            config='--psm 11'  # Sparse text mode, good for drawings
        )

        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])

            if text and conf > 30:  # Filter low-confidence results
                results.append({
                    "page": page_num,
                    "text": text,
                    "confidence": conf,
                    "bbox": (
                        data['left'][i],
                        data['top'][i],
                        data['left'][i] + data['width'][i],
                        data['top'][i] + data['height'][i]
                    ),
                    "dpi": dpi,  # needed to convert px to mm
                })

    return results

# Post-processing: find thread callouts
def find_threads_in_ocr(ocr_results):
    """Search OCR results for thread patterns."""
    thread_pattern = re.compile(
        r'M\s*(\d+(?:[.,]\d+)?)'
        r'(?:\s*[xX×]\s*(\d+(?:[.,]\d+)?))?'
        r'(?:\s*[-–]\s*(\d+[A-Za-z]\d?[A-Za-z]?))?'
    )

    threads = []
    for r in ocr_results:
        match = thread_pattern.search(r["text"])
        if match:
            threads.append({
                **r,
                "thread_diameter": match.group(1),
                "thread_pitch": match.group(2),
                "tolerance_class": match.group(3),
            })
    return threads

# Usage
ocr_data = ocr_engineering_drawing("scanned_drawing.pdf")
threads = find_threads_in_ocr(ocr_data)
for t in threads:
    print(f"Thread: M{t['thread_diameter']}x{t['thread_pitch']} "
          f"class={t['tolerance_class']} at bbox={t['bbox']}")
```

**Tesseract configuration tips for engineering drawings:**
```python
# Good Tesseract configs for engineering drawings:
configs = {
    # Sparse text (annotations scattered on drawing)
    "sparse": "--psm 11 --oem 3",
    # Single line (for reading individual annotations)
    "single_line": "--psm 7 --oem 3",
    # Digits + special chars only
    "numeric": "--psm 7 -c tessedit_char_whitelist=0123456789.+-×xMmHhø⌀",
}
```

**Limitations:**
- OCR accuracy drops with small text, special symbols, overlapping geometry
- GD&T symbols (geometric tolerance frames) are very hard for standard Tesseract
- Requires preprocessing (deskew, denoise) for good results
- Slow compared to native text extraction
- Special engineering symbols (diameter, depth) often misread


### 2.4 Hybrid Approach — RECOMMENDED

Combine PyMuPDF for native text + Tesseract for fallback:

```python
import fitz
from pdf2image import convert_from_path
import pytesseract
import re

def extract_annotations_hybrid(pdf_path):
    """Try native text extraction first, fall back to OCR."""
    doc = fitz.open(pdf_path)
    all_annotations = []

    for page_num, page in enumerate(doc):
        # Try native text extraction first
        text_dict = page.get_text("dict")
        native_texts = []

        for block in text_dict["blocks"]:
            if block["type"] == 0:
                for line in block["lines"]:
                    line_text = "".join(span["text"] for span in line["spans"])
                    if line_text.strip():
                        native_texts.append({
                            "text": line_text.strip(),
                            "bbox": line["bbox"],
                            "source": "native",
                        })

        if native_texts:
            all_annotations.extend(native_texts)
        else:
            # Fallback: page is likely scanned, use OCR
            pix = page.get_pixmap(dpi=300)
            img_data = pix.tobytes("png")

            # Use PyMuPDF's built-in OCR if available
            tp = page.get_textpage_ocr(flags=0, dpi=300)
            ocr_dict = page.get_text("dict", textpage=tp)

            for block in ocr_dict["blocks"]:
                if block["type"] == 0:
                    for line in block["lines"]:
                        line_text = "".join(span["text"] for span in line["spans"])
                        if line_text.strip():
                            all_annotations.append({
                                "text": line_text.strip(),
                                "bbox": line["bbox"],
                                "source": "ocr",
                            })

    doc.close()
    return all_annotations
```

### 2.5 PDF Annotation Library Comparison

| Feature | PyMuPDF | pdfplumber | pdf2image+Tesseract |
|---------|---------|------------|---------------------|
| Install | `pip install PyMuPDF` | `pip install pdfplumber` | `pip install pdf2image pytesseract` |
| Speed | Fast | Medium | Slow |
| Native text + bbox | Yes (excellent) | Yes (good) | N/A |
| OCR support | Built-in (Tesseract) | No | Yes |
| Line/rect detection | Basic | Excellent | Via OpenCV |
| Visual debugging | Via pixmaps | Built-in | Manual |
| Scanned PDFs | Via OCR | No | Yes |
| Best for | Text extraction + bbox | Layout analysis + tables | Scanned drawings |

---

## 3. NIST PMI Dataset

### 3.1 Overview

The NIST PMI dataset provides freely available CAD models and STEP files with Product Manufacturing Information (PMI) annotations. It was created to measure conformance of CAD software to ASME standards for GD&T.

**URL:** https://catalog.data.gov/dataset/nist-cad-models-and-step-files-with-pmi-3bb54

**Direct download page:** https://www.nist.gov/ctl/smart-connected-systems-division/smart-connected-manufacturing-systems-group/mbe-pmi-0

**Test case browser:** https://pages.nist.gov/CAD-PMI-Testing/models.html

### 3.2 What is Available

**Test Cases:**
- **CTC 1-5** (Conformance Test Cases): Focused tests for specific PMI types
- **FTC 6-11** (Fully Toleranced Test Cases): Complete GD&T annotation sets
- **STC** (Simplified Test Cases): Modified FTC with less complex PMI (developed 2023)
- **Hole-specific test cases** (developed 2024): counterbore, countersink, through holes, depth holes

**Total:** 421 PMI annotations across 11 test cases

**File Formats:**
- STEP AP242 (with graphical and semantic PMI)
- STEP AP203 (geometry only, limited PMI)
- Native CAD models: CATIA V5, Creo, NX
- 2D test case definition drawings (PDF)

### 3.3 PMI Annotation Types Covered

**Dimensions:**
- Linear dimensions
- Diameter dimensions
- Radius dimensions
- Hole callouts (counterbore, countersink, depth)
- Slope and taper dimensions
- Slot dimensions
- Basic dimensions

**Geometric Tolerances:**
- Position tolerance
- Surface profile tolerance
- Line profile tolerance
- Flatness
- Cylindricity
- Circularity (roundness)
- Perpendicularity
- Parallelism
- Angularity
- Runout (circular and total)
- Concentricity
- Symmetry

**Other PMI:**
- Datum features
- Datum targets
- Feature control frames (single and multi-line)
- Material condition modifiers (MMC, LMC)
- Surface finish annotations

### 3.4 How to Use This Dataset

This dataset is extremely valuable for your hackathon because:

1. **Ground truth for matching:** Each test case has a 2D drawing (PDF) AND a 3D STEP file with semantic PMI. You can use the 2D drawing as input and verify your extraction against the STEP PMI.

2. **AP242 semantic PMI:** The STEP AP242 files contain machine-readable PMI that you can programmatically extract and compare against PDF-extracted annotations.

3. **Variety of annotation types:** Covers all common GD&T and dimension types you'd encounter in real engineering drawings.

**Code: Download and extract NIST test case files:**
```python
import urllib.request
import os

# Base URL for NIST PMI test files
# Check https://www.nist.gov/ctl/smart-connected-systems-division/
# smart-connected-manufacturing-systems-group/mbe-pmi-0
# for the actual download links

# After downloading, parse the STEP AP242 file:
from OCC.Core.STEPControl import STEPControl_Reader

reader = STEPControl_Reader()
reader.ReadFile("nist-ctc-01-asme1-ap242.stp")
reader.TransferRoots()
shape = reader.OneShape()
# Now extract features as shown in Section 1
```

### 3.5 NIST STEP File Analyzer and Viewer (SFA)

**What it is:** A free tool from NIST that generates spreadsheets and visualizations from STEP files, with specific support for PMI analysis.

**GitHub:** https://github.com/usnistgov/SFA

**Key capabilities:**
- Generates spreadsheets of all STEP entity and attribute information
- Reports and analyzes semantic PMI, graphic PMI, and validation properties
- Checks conformance to STEP recommended practices
- Viewer for part geometry and graphical PMI annotations
- Can validate your STEP PMI extraction against expected results

**Limitations:**
- Written in Tcl (not Python)
- Windows-focused (uses IFCsvr toolkit)
- Primarily an analysis/validation tool, not a library

---

## 4. Existing Open-Source Projects

### 4.1 eDOCr — Engineering Drawing OCR

**What it is:** A packaged OCR system specifically for mechanical engineering drawings, based on keras-ocr. The most relevant open-source tool for GD&T extraction from drawings.

**GitHub:** https://github.com/javvi51/eDOCr

**Installation:**
```bash
conda create -n edocr python=3.9 -y
conda activate edocr
pip install eDOCr
```

**Key capabilities:**
- Detects and recognizes GD&T symbols (Feature Control Frames)
- Specialized models for dimensions, info blocks, and GD&T
- Trained to recognize GD&T Unicode symbols: flatness, straightness, circularity, cylindricity, perpendicularity, angularity, parallelism, position, concentricity, symmetry, profile, runout
- 90% precision/recall in detection, 94% F1-score in recognition
- Returns bounding boxes for all detected elements

**Code: Basic usage:**
```bash
# From terminal
python PATH/TO/eDOCr/ocr_it.py drawing.pdf --dest-folder output/ --cluster 40
```

```python
# From Python
import edocr

# Process a drawing
results = edocr.process_drawing("drawing.pdf")
# Returns detected dimensions, GD&T frames, info blocks with positions
```

**Limitations:**
- Requires TensorFlow 2.x
- Trained on specific drawing styles (may need retraining)
- Python 3.9 recommended (TF compatibility)
- Windows-focused development


### 4.2 Engineering Drawing Extractor (Bakkopi)

**GitHub:** https://github.com/Bakkopi/engineering-drawing-extractor

**What it does:**
- Extracts engineering drawings from blueprint images
- OCR-based extraction of key information (drawing numbers, authors, titles)
- Removes unnecessary lines, borders, annotations
- Table data extraction from images

**Installation:**
```bash
git clone https://github.com/Bakkopi/engineering-drawing-extractor
cd engineering-drawing-extractor
pip install -r requirements.txt
python mainExtractionOCR.py
```

**Limitations:**
- Focused on title block extraction, not GD&T
- Less sophisticated than eDOCr for annotation recognition


### 4.3 STEPfileparser (anjanadev96)

**GitHub:** https://github.com/anjanadev96/STEPfileparser

**What it does:**
- Converts STEP files to JSON using pythonocc
- Extracts face geometry including handling of holes
- Useful template for STEP parsing workflows

**Limitations:**
- Older project, may need updates for current pythonocc
- Limited documentation


### 4.4 Werk24 (Commercial with Python SDK)

**PyPI:** https://pypi.org/project/werk24/

**What it does:**
- AI-powered PMI extraction from technical drawings
- Extracts: dimensions, tolerances, threads, bores, chamfers, roughness, GD&T, radii
- Returns structured JSON with all annotations
- >95% accuracy claimed

**Installation:**
```bash
pip install werk24
```

**Code example:**
```python
from werk24 import W24TechreadClient, W24AskVariantMeasures

async def extract_pmi(drawing_path):
    async with W24TechreadClient.make_from_env() as client:
        result = await client.read_drawing(
            drawing_path,
            [W24AskVariantMeasures()]
        )
        for page in result:
            for measure in page.measures:
                print(f"Type: {measure.type}, Value: {measure.value}, "
                      f"Tolerance: {measure.tolerance}")
```

**Limitations:**
- COMMERCIAL — requires a paid license/API key
- Cloud-based processing (sends drawings to their servers)
- Not suitable if data sensitivity is a concern


### 4.5 Florence-2 Fine-tuned for GD&T (Research)

**Paper:** https://arxiv.org/pdf/2411.03707

**What it is:** Microsoft's Florence-2 vision-language model fine-tuned on 400 engineering drawings for GD&T extraction. Shows that VLMs can be adapted for this task.

**Relevance:** Could be used as a more modern alternative to eDOCr for GD&T detection, though requires significant compute for fine-tuning.


### 4.6 YOLO-based Approaches (Research)

Multiple research projects have used YOLOv5/v7 for detecting GD&T symbols and annotations in engineering drawings:
- Roboflow has a "CAD" object detection dataset available
- YOLOv5 has been used to classify GD&T symbols
- Can be combined with OCR for end-to-end annotation extraction

**Code: Using Ultralytics YOLO for symbol detection (conceptual):**
```python
from ultralytics import YOLO

# Would need a model trained on GD&T symbols
model = YOLO("gdnt_symbols.pt")  # hypothetical trained model

results = model("drawing_page.png")
for box in results[0].boxes:
    cls = box.cls  # class: e.g., "position_tolerance", "diameter_dim"
    bbox = box.xyxy  # bounding box
    conf = box.conf  # confidence
    print(f"Detected: {cls} at {bbox} (conf={conf})")
```

---

## 5. Recommended Architecture

For the hackathon challenge of linking PDF annotations to 3D CAD holes/threads:

### Pipeline Overview

```
PDF Drawing                          STEP 3D Model
    |                                      |
    v                                      v
[PyMuPDF text extraction]     [PythonOCC STEP reader]
    |                                      |
    v                                      v
[Regex pattern matching]       [Face topology explorer]
[Thread: M10x1.5-6H]          [Cylindrical faces]
[Tolerance: H7]                [Radius, center, axis]
[Diameter: O20]                [Depth estimation]
    |                                      |
    v                                      v
[Annotation list with          [Feature list with
 bounding boxes and             face IDs and
 parsed parameters]             geometric properties]
    |                                      |
    +------------- MATCHING ---------------+
                     |
                     v
            [Matched pairs:
             annotation <-> 3D feature]
```

### Matching Strategy

1. **By diameter:** Match PDF diameter dimensions to 3D cylindrical face radii (D = 2*R)
2. **By thread spec:** Match M10x1.5 in PDF to cylindrical faces with R ~= 5.0mm (or R ~= 4.25mm for minor diameter)
3. **By position:** If PDF has view projections, use annotation position relative to drawing views to correlate with 3D feature positions
4. **By depth:** Match PDF depth callouts to estimated cylinder depths from surface area
5. **By count:** If PDF says "4x M8" and model has exactly 4 cylindrical faces with R~4mm, match the group

### Quick Start Dependencies

```bash
# Create environment
conda create -n hackathon python=3.12 -y
conda activate hackathon

# CAD parsing
conda install -c conda-forge pythonocc-core=7.9.3

# PDF processing
pip install PyMuPDF pdfplumber

# OCR fallback
pip install pdf2image pytesseract Pillow opencv-python

# Utilities
pip install numpy pandas
```
