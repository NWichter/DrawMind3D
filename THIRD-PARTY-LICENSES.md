# DrawMind3D - Third-Party Components and Licences

Prepared for licensing review. Generated from the pinned environment
(Python 3.12, 54 installed distributions) together with the front-end
libraries loaded by `web/static/index.html`.

DrawMind3D itself is proprietary; see `LICENSE`.

## 1. Summary

No component of the product is under a copyleft licence that would conflict
with integration into a closed-source commercial product, including SaaS and
customer-hosted deployments.

| Category                                                           | Count | Effect on proprietary use                              |
| ------------------------------------------------------------------ | ----- | ------------------------------------------------------ |
| Permissive (MIT, BSD, Apache-2.0, PSF, Unicode)                    | 52    | None                                                   |
| Weak copyleft, file level (MPL-2.0)                                | 2     | None while unmodified                                  |
| Weak copyleft, library level (LGPL-2.1 with OpenCASCADE exception) | 1     | None while dynamically linked and unmodified — see 2.1 |
| Strong copyleft (GPL / AGPL)                                       | 0     | -                                                      |

## 2. Components worth noting

### 2.1 OpenCASCADE via cadquery-ocp

The STEP parsing and geometry engine. The Python bindings are Apache-2.0;
the bundled OpenCASCADE Technology core is LGPL-2.1 with the OpenCASCADE
exception. It is used as an unmodified, dynamically linked library, which the
licence permits for proprietary products. The obligations that carry over are
attribution and passing on the licence text; there is no requirement to
disclose the source of the calling application.

### 2.2 PDFium via pypdfium2

Handles text extraction, vector path access and rasterisation. The wrapper is
Apache-2.0 or BSD-3-Clause; PDFium itself is BSD-3-Clause. Its bundled
third-party components (Abseil, AGG, FreeType, ICU, lcms, libjpeg-turbo,
libpng, libtiff, OpenJPEG, zlib, simdutf) are all permissive.

One point checked explicitly: the ICU licence file contains a GPL-2.0 notice.
It applies to `pkg.m4`, an autoconf macro in the ICU source tree used at build
time. It is not part of the distributed binary and does not affect
redistribution.

### 2.3 MPL-2.0 components

`certifi` (CA certificate bundle) and `tqdm` (progress output). MPL-2.0 is
file-level copyleft: obligations attach only to modified MPL files. Both are
used unmodified, so nothing carries over to the surrounding product.

### 2.4 Tesseract OCR

`pytesseract` (Apache-2.0) is a wrapper; it invokes the Tesseract binary
(Apache-2.0) as a separate process. The binary is a system dependency
installed by the container image, not redistributed as part of the product.
OCR is a fallback path and the product runs without it.

## 3. Front-end libraries

| Library  | Version  | Licence    |
| -------- | -------- | ---------- |
| three.js | r128     | MIT        |
| pdf.js   | 3.11.174 | Apache-2.0 |

Both are currently loaded from public CDNs at runtime. For customer-hosted or
air-gapped deployments they need to be vendored locally.

## 4. External services

The vision model is reached over an OpenAI-compatible API (OpenRouter by
default). Its terms govern commercial use and data handling and apply to the
operator directly, not through this licence. The backend is pluggable and can
be replaced with a self-hosted model.

## 5. Test data

The bundled NIST test cases (CTC, FTC, D2MI) are US Government
publications and are not subject to copyright in the United States. Each
dataset carries its own notice. They are test fixtures and are not part of
the product.

## 6. Test tooling

`scripts/generate_synthetic.py` regenerates the committed synthetic test
fixtures. It writes the PDF drawings itself and uses only dependencies listed
below (OCP, Pillow, matplotlib). No tool in the repository needs a component
outside this list.

## 7. Full dependency list

| Package            | Version     | Licence                                                         | Role       |
| ------------------ | ----------- | --------------------------------------------------------------- | ---------- |
| annotated-doc      | 0.0.4       | MIT                                                             | transitive |
| annotated-types    | 0.7.0       | MIT License                                                     | transitive |
| anyio              | 4.12.1      | MIT                                                             | transitive |
| cadquery-ocp       | 7.9.3.1     | Apache-2.0 (bindings); LGPL-2.1 with OCCT exception (OCCT core) | direct     |
| cadquery-ocp-proxy | 7.9.3.1     | Apache-2.0                                                      | transitive |
| certifi            | 2026.2.25   | MPL-2.0                                                         | transitive |
| click              | 8.3.1       | BSD-3-Clause                                                    | transitive |
| colorama           | 0.4.6       | BSD License                                                     | dev        |
| contourpy          | 1.3.3       | BSD 3-Clause License                                            | transitive |
| cycler             | 0.12.1      | Copyright (c) 2015, matplotlib project                          | transitive |
| dataclasses-json   | 0.6.7       | MIT                                                             | transitive |
| Deprecated         | 1.3.1       | MIT                                                             | transitive |
| distro             | 1.9.0       | Apache License, Version 2.0                                     | transitive |
| drawmind3d         | 1.0.0       | LicenseRef-Proprietary                                          | transitive |
| fastapi            | 0.135.1     | MIT                                                             | direct     |
| fonttools          | 4.62.0      | MIT                                                             | transitive |
| h11                | 0.16.0      | MIT                                                             | transitive |
| httpcore           | 1.0.9       | BSD-3-Clause                                                    | transitive |
| httpx              | 0.28.1      | BSD-3-Clause                                                    | direct     |
| idna               | 3.11        | BSD-3-Clause                                                    | transitive |
| iniconfig          | 2.3.0       | MIT                                                             | dev        |
| jiter              | 0.13.0      | MIT License                                                     | transitive |
| kiwisolver         | 1.5.0       | BSD-3-Clause                                                    | transitive |
| marshmallow        | 3.26.2      | MIT License                                                     | transitive |
| matplotlib         | 3.10.8      | Matplotlib License (BSD-style)                                  | direct     |
| mypy_extensions    | 1.1.0       | MIT                                                             | transitive |
| numpy              | 2.4.3       | BSD-3-Clause                                                    | direct     |
| openai             | 2.26.0      | Apache-2.0                                                      | direct     |
| packaging          | 26.0        | Apache-2.0 OR BSD-2-Clause                                      | dev        |
| pillow             | 12.1.1      | MIT-CMU                                                         | direct     |
| pluggy             | 1.6.0       | MIT                                                             | dev        |
| pydantic           | 2.12.5      | MIT                                                             | direct     |
| pydantic_core      | 2.41.5      | MIT                                                             | transitive |
| pygltflib          | 1.16.5      | MIT License                                                     | direct     |
| Pygments           | 2.19.2      | BSD-2-Clause                                                    | dev        |
| pyparsing          | 3.3.2       | MIT                                                             | transitive |
| pypdfium2          | 5.6.0       | BSD-3-Clause, Apache-2.0, dependency licenses                   | direct     |
| pytesseract        | 0.3.13      | Apache License 2.0                                              | direct     |
| pytest             | 9.0.2       | MIT                                                             | dev        |
| python-dateutil    | 2.9.0.post0 | Dual License                                                    | transitive |
| python-dotenv      | 1.2.2       | BSD-3-Clause                                                    | direct     |
| python-multipart   | 0.0.22      | Apache-2.0                                                      | direct     |
| ruff               | 0.15.5      | MIT License                                                     | dev        |
| scipy              | 1.17.1      | BSD-3-Clause                                                    | direct     |
| six                | 1.17.0      | MIT                                                             | transitive |
| sniffio            | 1.3.1       | MIT OR Apache-2.0                                               | transitive |
| starlette          | 0.52.1      | BSD-3-Clause                                                    | transitive |
| tqdm               | 4.67.3      | MPL-2.0 AND MIT                                                 | transitive |
| typing-inspect     | 0.9.0       | MIT                                                             | transitive |
| typing-inspection  | 0.4.2       | MIT                                                             | transitive |
| typing_extensions  | 4.15.0      | PSF-2.0                                                         | transitive |
| uvicorn            | 0.41.0      | BSD-3-Clause                                                    | direct     |
| vtk                | 9.5.2       | BSD                                                             | transitive |
| wrapt              | 2.1.2       | BSD-2-Clause                                                    | transitive |
