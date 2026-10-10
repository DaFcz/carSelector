# Car Price Lists and Equipment Collection Platform – Solution Architecture

## Overview

The goal is to build a Python-based data collection platform that gathers car price lists and equipment information from all OEMs actively selling new vehicles in Czechia.

The platform should:

- Maintain a registry of OEM source websites.
- Detect newly published price lists and equipment documents.
- Download PDF files and preserve historical versions.
- Parse price and equipment information.
- Normalize extracted data.
- Store structured data in a SQL database.
- Provide search and reporting capabilities through an API.

---

## High-Level Architecture

```text
OEM Source Registry
        |
        v
Source Monitoring
        |
        v
PDF Downloader
        |
        v
PDF Parsing Layer
        |
        v
Data Normalization
        |
        v
SQL Database
        |
        v
API / Reporting Layer
```

---

## Recommended Technology Stack

### Core

- Python 3.12+
- Docker
- Git

### Data Collection

- requests
- BeautifulSoup4
- Playwright

### Scheduling

- APScheduler

### Database

- PostgreSQL
- SQLAlchemy
- Alembic

### PDF Processing

- PDFPlumber
- PyMuPDF
- Camelot
- Tabula-Py
- pytesseract (OCR fallback)

### API

- FastAPI

---

## Source Registry

Maintain all OEM sources in a database table.

Example schema:

```sql
CREATE TABLE source (
    id SERIAL PRIMARY KEY,
    brand VARCHAR(100),
    country VARCHAR(50),
    source_url TEXT,
    pdf_pattern TEXT,
    active BOOLEAN DEFAULT TRUE
);
```

Example brands:

- Škoda
- Volkswagen
- Toyota
- Hyundai
- Kia
- BMW
- Mercedes-Benz
- Audi
- Renault
- Peugeot

---

## New Document Detection

The system should avoid redownloading previously processed files.

Recommended process:

1. Discover available PDFs.
2. Download or inspect content.
3. Calculate SHA256 hash.
4. Compare with existing records.
5. Download and process only new files.

Example schema:

```sql
CREATE TABLE document (
    id SERIAL PRIMARY KEY,
    source_id INT,
    document_url TEXT,
    sha256_hash VARCHAR(64),
    release_date DATE,
    downloaded_at TIMESTAMP
);
```

This approach handles cases where OEMs replace PDF content while keeping the same URL.

---

## Document Storage

Never overwrite existing files.

Suggested structure:

```text
storage/
    skoda/
        2026/
            octavia_pricelist_202607.pdf
    toyota/
        2026/
            corolla_pricelist_202606.pdf
```

Benefits:

- Historical analysis
- Traceability
- Auditing
- Easier debugging

---

## PDF Parsing Layer

### Text Extraction

Preferred libraries:

- PDFPlumber
- PyMuPDF

Example use cases:

- Metadata extraction
- Variant names
- Equipment descriptions
- Prices

### Table Extraction

Preferred libraries:

- Camelot
- Tabula-Py

Useful when price lists are structured as tables.

### OCR Fallback

For image-based PDFs:

```text
PDF
 -> Image Conversion
 -> OCR (Tesseract)
 -> Structured Text
```

---

## Parser Strategy

Avoid creating one universal parser.

Use a plugin architecture.

```python
class BaseParser:
    def parse(self, pdf_path):
        pass
```

OEM-specific implementations:

```python
class SkodaParser(BaseParser):
    pass


class ToyotaParser(BaseParser):
    pass


class BMWParser(BaseParser):
    pass
```

Advantages:

- Easier maintenance
- Better extraction quality
- Faster adaptation to OEM layout changes

---

## Database Design

### Vehicle Model

Examples:

- Octavia
- Golf
- Corolla

### Trim Level

Examples:

- Selection
- Style
- Sportline
- RS

### Vehicle Variant

Examples:

- Octavia Sportline 2.0 TDI DSG
- Golf R 2.0 TSI DSG

### Equipment

Examples:

- Adaptive Cruise Control
- Matrix LED Headlights
- Heated Seats

### Price History

Recommended schema:

```sql
price_history (
    id,
    variant_id,
    price,
    currency,
    valid_from,
    document_id
)
```

This allows tracking price development over time.

---

## Equipment Processing

OEMs commonly use markers such as:

```text
● Standard
○ Optional
S = Standard
O = Optional
```

Normalize equipment availability into:

- STANDARD
- OPTIONAL
- PACKAGE
- NOT_AVAILABLE

Example schema:

```sql
equipment_assignment (
    variant_id,
    equipment_id,
    availability
)
```

---

## Data Normalization

One of the most important layers.

Example aliases:

```text
ACC
Adaptive Cruise Control
Distance Assist
```

Mapped to:

```text
adaptive_cruise_control
```

Recommended table:

```sql
equipment_alias
```

Benefits:

- Consistent reporting
- Easier comparison across brands

---

## API Layer

Implement with FastAPI.

Suggested endpoints:

```text
GET /brands
GET /models
GET /variants
GET /equipment
GET /price-history
```

Example:

```text
GET /variants?brand=Skoda
```

---

## Recommended Project Structure

```text
car-catalog/
├── scraper/
│   ├── sources/
│   ├── downloaders/
│   └── monitors/
│
├── parser/
│   ├── base.py
│   ├── skoda.py
│   ├── vw.py
│   └── toyota.py
│
├── database/
│   ├── models.py
│   └── repositories.py
│
├── api/
│   └── main.py
│
├── scheduler/
├── storage/
└── tests/
```

---

## Implementation Roadmap

### Phase 1 – MVP

Collect:

- Brand
- PDF metadata
- Vehicle variants
- Prices

Initial OEMs:

- Škoda
- Volkswagen
- Toyota
- Hyundai
- Kia

### Phase 2

Add:

- Equipment extraction
- Historical price comparison

### Phase 3

Add:

- Option packages
- Technical specifications
- CO₂ values
- WLTP consumption

### Phase 4

Add AI-assisted extraction:

- LLM-based parsing
- Automatic parser generation
- Layout classification

---

## Final Recommendation

Recommended stack:

- Playwright
- PostgreSQL
- SQLAlchemy
- PDFPlumber
- Camelot
- PyMuPDF
- FastAPI
- APScheduler
- Docker

The key architectural principle should be a plugin-based parser model with full document versioning, since OEM PDF formats differ significantly and change frequently.
