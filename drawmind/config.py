"""Configuration and environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "output"
TEMP_DIR = PROJECT_ROOT / "tmp"

# OpenRouter API (single key for all models)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# LLM Settings
USE_VISION_LLM = bool(OPENROUTER_API_KEY)
VISION_MODEL = os.getenv("VISION_MODEL", "google/gemini-2.5-flash")
VISION_MODEL_FALLBACK = os.getenv("VISION_MODEL_FALLBACK", "google/gemini-2.5-pro")
TEXT_MODEL = os.getenv("TEXT_MODEL", "anthropic/claude-haiku-4-5-20251001")
# Disambiguation uses the same cheap vision model — text-only context is sufficient
DISAMBIGUATE_MODEL = os.getenv("DISAMBIGUATE_MODEL", "google/gemini-2.5-flash")

# Vision fallback: re-analyze with stronger model if few annotations found
VISION_FALLBACK_MIN_ANNOTATIONS = 2  # Trigger fallback if fewer than this found

# Matching thresholds
MATCH_CONFIDENCE_THRESHOLD = 0.6
LLM_REVIEW_THRESHOLD = 0.8
DIAMETER_TOLERANCE_MM = 0.5
DEPTH_TOLERANCE_MM = 2.0
COAXIAL_ANGLE_TOLERANCE_DEG = 5.0
COAXIAL_DISTANCE_TOLERANCE_MM = 0.5

# Scoring weights (diameter is the strongest signal for mechanical features)
WEIGHT_DIAMETER = 0.45
WEIGHT_DEPTH = 0.18
WEIGHT_TYPE_COMPAT = 0.22
WEIGHT_COUNT = 0.08
WEIGHT_UNIQUENESS = 0.04
WEIGHT_SPATIAL = 0.03

# Scoring parameters
NEUTRAL_SCORE = 0.50  # Score for missing data: "no evidence for or against"
MAX_DIAMETER_RATIO = 2.5  # Reject matches beyond this diameter ratio

# Vision false-positive filter
VISION_FP_CONFIDENCE_THRESHOLD = 0.75  # Vision annotations below this are checked against 3D
VISION_FP_DIAMETER_TOLERANCE_FACTOR = 2.5  # Multiplier on DIAMETER_TOLERANCE_MM for FP filter

# Depth association (PDF proximity for linking depth annotations to holes)
DEPTH_ASSOCIATION_DISTANCE_PTS = 150  # Max distance in PDF points

# Parser limits
MAX_HOLE_DIAMETER_MM = 100.0
MAX_HOLE_DIAMETER_INCH = 4.0
GDT_MAX_INCH_VALUE = 0.1

# PDF extraction
OCR_DPI = 300
OCR_CONFIDENCE_THRESHOLD = 30
MIN_TEXT_COUNT_FOR_NATIVE = 5  # Below this, assume scanned PDF

# Tesseract OCR path (auto-detect on Windows)
import shutil as _shutil
TESSERACT_PATH = _shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if Path(TESSERACT_PATH).exists():
    _tess_dir = str(Path(TESSERACT_PATH).parent)
    if _tess_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _tess_dir + os.pathsep + os.environ.get("PATH", "")
    _tessdata = str(Path(TESSERACT_PATH).parent / "tessdata")
    if Path(_tessdata).exists():
        os.environ.setdefault("TESSDATA_PREFIX", _tessdata)

# Ensure directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
