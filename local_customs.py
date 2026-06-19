"""Local customs/import data reader from Excel files."""

import logging
import os

logger = logging.getLogger(__name__)


class CustomsReader:
    """Read and search customs/import history from an Excel file."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.data = []
        self.loaded = False
        self.error = None
        self._load()

    def _load(self):
        if not os.path.isfile(self.filepath):
            self.error = f"File not found: {self.filepath}"
            return
        try:
            import openpyxl
            wb = openpyxl.load_workbook(self.filepath, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                self.error = "Empty spreadsheet"
                return
            headers = [str(h).lower().strip() if h else f"col_{i}" for i, h in enumerate(rows[0])]
            self.data = []
            for row in rows[1:]:
                record = {}
                for i, val in enumerate(row):
                    if i < len(headers):
                        record[headers[i]] = str(val) if val is not None else ""
                self.data.append(record)
            wb.close()
            self.loaded = True
            self.error = None
        except ImportError:
            self.error = "openpyxl not installed"
        except Exception as e:
            self.error = str(e)

    def reload(self):
        self.data = []
        self.loaded = False
        self.error = None
        self._load()

    def status(self):
        if self.loaded:
            return {"loaded": True, "records": len(self.data), "message": f"{len(self.data)} records loaded"}
        return {"loaded": False, "records": 0, "message": self.error or "Not loaded"}

    def match_company(self, company_name):
        """Search for a company in customs data. Returns matching records."""
        if not self.loaded or not company_name:
            return {"matched": False, "records": [], "query": company_name}

        company_lower = company_name.lower().strip()
        matches = []
        for record in self.data:
            # Search across all fields for company name
            for val in record.values():
                if company_lower in val.lower():
                    matches.append(record)
                    break

        return {
            "matched": len(matches) > 0,
            "records": matches[:50],  # cap at 50
            "total": len(matches),
            "query": company_name,
        }
