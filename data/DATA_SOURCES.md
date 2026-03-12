# Test Data Sources

## Currently Available

### NIST MBE PMI Test Cases (Primary)
- **Location:** `data/nist/NIST-PMI-STEP-Files/`
- **Files:** 11 STEP+PDF pairs (5 CTC, 6 FTC)
- **Format:** AP203 STEP (geometry only) + PDF drawings with GD&T
- **Units:** INCH (most FTC cases), Metric (CTC cases)
- **Source:** https://www.nist.gov/ctl/smart-connected-systems-division/smart-connected-manufacturing-systems-group/mbe-pmi-0

### NIST SMS Test Bed (Supplementary)
- **Location:** `data/nist_sms_testbed/`
- **Files:** plate.STEP, 827-9999-904.stp, box/cover 3D PDFs
- **Note:** PDFs are 3D PDFs, not traditional 2D drawings
- **Source:** https://github.com/usnistgov/smstestbed

## Potential Additional Sources

### CAx-IF / MBx-IF Test Rounds
- AP242 STEP files with semantic PMI
- Biannual test rounds with new models
- URL: https://www.mbx-if.org/home/cax/resources/

### MFCAD-VLM Dataset (Zenodo)
- 1000+ STEP files with manufacturing feature annotations
- Multi-view images, JSON annotations
- No traditional 2D drawings, no GD&T
- URL: https://zenodo.org/records/14038050

### GrabCAD Community
- Millions of CAD files, some with drawings
- Inconsistent quality, requires manual curation
- URL: https://grabcad.com/library

### TraceParts / 3D ContentCentral
- Catalog parts with datasheets (STEP + datasheet PDF)
- Limited GD&T (datasheet-level tolerances)
- URL: https://www.traceparts.com/en

## Notes
- The industry trend toward MBD (Model-Based Definition) means fewer
  STEP+PDF pairs are being created — GD&T increasingly lives in the 3D model.
- For training Vision LLM recognition, university practice drawing PDFs can
  supplement (no matching STEP files, but useful for annotation detection).
