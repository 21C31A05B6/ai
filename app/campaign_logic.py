import csv
import io
import re
from typing import Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Phone normalisation
# ---------------------------------------------------------------------------

def normalize_phone(phone: str) -> str:
    """Keep digits and leading + if present.

    Examples:
      +91-90000 12345 -> +919000012345
      90000 12345 -> 9000012345
    """
    if phone is None:
        return ""

    s = str(phone).strip()
    if not s:
        return ""

    # Preserve leading + if present
    leading_plus = s.startswith('+')
    digits = re.sub(r"\D+", "", s)
    if leading_plus:
        return "+" + digits
    return digits


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_header_value(row: dict, keys: Iterable[str]) -> str:
    for k in keys:
        if k in row and row[k] is not None:
            return str(row[k]).strip()
    return ""


PHONE_KEYS = [
    "phone", "Phone", "mobile", "Mobile", "mobile_number", "phone_number",
    "PhoneNumber", "contact", "Contact", "number", "Number", "cell",
    "Cell", "telephone", "Telephone", "tel", "Tel",
]

NAME_KEYS = [
    "name", "full_name", "full name", "Name", "Full Name", "Full_Name",
    "candidate_name", "Candidate Name", "customer_name", "client_name",
    "first_name", "FirstName", "firstname",
]


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------

def parse_contacts_csv_bytes(data: bytes) -> List[Tuple[str, str]]:
    """Parse CSV bytes into list of (name, phone). Phone is required.

    Accepts headers like:
      - name, phone
      - Name, Phone
      - full_name, mobile
      - phone_number
    """
    text = data.decode("utf-8-sig", errors="ignore")
    f = io.StringIO(text)

    reader = csv.DictReader(f)
    if not reader.fieldnames:
        raise ValueError("CSV must include headers: name and phone")

    contacts: List[Tuple[str, str]] = []
    for row in reader:
        raw_phone = _pick_header_value(row, PHONE_KEYS)
        raw_name = _pick_header_value(row, NAME_KEYS)

        phone = normalize_phone(raw_phone)
        name = raw_name.strip() if raw_name else ""

        if not phone:
            # Skip invalid row
            continue
        contacts.append((name, phone))

    if not contacts:
        raise ValueError("No valid contacts found. Ensure the CSV has a phone column.")

    return contacts


# ---------------------------------------------------------------------------
# Excel (.xlsx) parser
# ---------------------------------------------------------------------------

def parse_contacts_excel_bytes(data: bytes) -> List[Tuple[str, str]]:
    """Parse Excel (.xlsx) bytes into list of (name, phone). Phone is required.

    Auto-detects name and phone columns by header names (case-insensitive).
    Works with files that have extra columns, merged cells in header rows, etc.
    """
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError(
            "openpyxl is required to read Excel files. "
            "Install it with: pip install openpyxl"
        )

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active  # first sheet

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Excel file is empty.")

    # Find header row (first row that contains a phone-like column)
    header_row_idx = None
    phone_col_idx = None
    name_col_idx = None

    for ri, row in enumerate(rows[:10]):  # search first 10 rows for header
        headers = [str(c).strip().lower() if c is not None else "" for c in row]
        for ci, h in enumerate(headers):
            if h in [k.lower() for k in PHONE_KEYS]:
                phone_col_idx = ci
                header_row_idx = ri
                break
        if phone_col_idx is not None:
            # Also look for name column in same row
            for ci, h in enumerate(headers):
                if h in [k.lower() for k in NAME_KEYS]:
                    name_col_idx = ci
                    break
            break

    if header_row_idx is None or phone_col_idx is None:
        # Try treating first row as header and scan all columns for phone-like data
        # Fall back: treat first column as name, second as phone
        header_row_idx = 0
        phone_col_idx = 1
        name_col_idx = 0

    contacts: List[Tuple[str, str]] = []
    for row in rows[header_row_idx + 1:]:
        if all(c is None for c in row):
            continue  # skip blank rows

        raw_phone = str(row[phone_col_idx]).strip() if (
            phone_col_idx < len(row) and row[phone_col_idx] is not None
        ) else ""

        raw_name = str(row[name_col_idx]).strip() if (
            name_col_idx is not None
            and name_col_idx < len(row)
            and row[name_col_idx] is not None
        ) else ""

        phone = normalize_phone(raw_phone)
        name = raw_name if raw_name else ""

        if not phone:
            continue

        contacts.append((name, phone))

    wb.close()

    if not contacts:
        raise ValueError(
            "No valid contacts found in Excel. "
            "Ensure there is a column named 'phone', 'mobile', or similar."
        )

    return contacts


# ---------------------------------------------------------------------------
# Auto-detect file type and parse
# ---------------------------------------------------------------------------

def parse_contacts_from_bytes(data: bytes, filename: str) -> List[Tuple[str, str]]:
    """Parse contacts from either CSV or Excel bytes based on file extension."""
    fname = filename.lower()
    if fname.endswith(".xlsx") or fname.endswith(".xls"):
        return parse_contacts_excel_bytes(data)
    else:
        # Default to CSV
        return parse_contacts_csv_bytes(data)
