import deepdoctection as dd
import matplotlib.pyplot as plt
from pathlib import Path
from collections import defaultdict
import subprocess
import os
import json
import shutil

# For HTML and Image conversion
# pip install playwright img2pdf fpdf
try:
    from playwright.sync_api import sync_playwright
    import img2pdf
    from fpdf import FPDF
except ImportError:
    print("Please install missing deps: pip install playwright img2pdf fpdf")

# ==============================
# CONFIG
# ==============================
INPUT_FILE = "input/sample.pdf"  # Change this to any of your files
OUTPUT_DIR = Path("output")
TEMP_DIR = Path("temp_processing")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# ==============================
# UNIVERSAL CONVERTER LAYER
# ==============================
class UniversalConverter:
    @staticmethod
    def to_pdf(input_path):
        input_path = Path(input_path)
        ext = input_path.suffix.lower()
        output_pdf = TEMP_DIR / f"{input_path.stem}.pdf"

        print(f"[*] Converting {ext} to PDF...")

        if ext == ".pdf":
            return str(input_path)

        # 1. Office Docs (.docx, .pptx, .xlsx)
        elif ext in ['.docx', '.pptx', '.xlsx']:
            # Requires LibreOffice installed (soffice)
            subprocess.run([
                'soffice', '--headless', '--convert-to', 'pdf',
                '--outdir', str(TEMP_DIR), str(input_path)
            ], check=True)

        # 2. HTML
        elif ext == '.html':
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(f"file://{input_path.absolute()}")
                page.pdf(path=str(output_pdf))
                browser.close()

        # 3. Images (.png, .jpg)
        elif ext in ['.png', '.jpg', '.jpeg']:
            with open(output_pdf, "wb") as f:
                f.write(img2pdf.convert(str(input_path)))

        # 4. Plain Text (.txt)
        elif ext == '.txt':
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            with open(input_path, "r", encoding="utf-8") as f:
                for line in f:
                    pdf.cell(200, 10, txt=line, ln=1)
            pdf.output(str(output_pdf))
        
        else:
            raise ValueError(f"Unsupported file format: {ext}")

        return str(output_pdf)

# ==============================
# HELPER: TABLE → HTML
# ==============================
def table_to_html(table):
    rows = defaultdict(dict)
    for cell in table.cells:
        row = cell.row_number
        col = cell.column_number
        text = cell.text.replace("\n", " ").strip()
        rows[row][col] = text

    html = "<table border='1' cellspacing='0' cellpadding='5' style='border-collapse: collapse; margin-bottom: 20px;'>\n"
    for r in sorted(rows.keys()):
        html += "  <tr>\n"
        for c in sorted(rows[r].keys()):
            html += f"    <td>{rows[r].get(c, '')}</td>\n"
        html += "  </tr>\n"
    html += "</table>\n"
    return html

# ==============================
# MAIN EXECUTION
# ==============================
def main():
    # 1. Convert Input to PDF (Assumes your UniversalConverter is defined)
    try:
        final_pdf_path = UniversalConverter.to_pdf(INPUT_FILE)
    except Exception as e:
        print(f"Error during conversion: {e}")
        return

    # 2. Initialize DeepDoctection
    print("[*] Creating DeepDoctection analyzer...")
    analyzer = dd.get_dd_analyzer()

    # 3. Analyze
    print("[*] Analyzing Document...")
    df = analyzer.analyze(path=final_pdf_path)
    df.reset_state()

    all_tables_html = []
    structured_data = {"pages": []}

    # 4. Process Results
    for page in df:
        page_num = page.page_number
        print(f"[+] Processing page {page_num}")

        # Save Visuals
        image = page.viz()
        image_path = OUTPUT_DIR / f"page_{page_num}.png"
        plt.imshow(image)
        plt.axis("off")
        plt.savefig(image_path, bbox_inches="tight", dpi=200)
        plt.close()

        page_entry = {
            "page_number": page_num,
            "texts": [],
            "tables": [],
            "titles": [],
            "lists": [],
            "figures": []
        }

        # --- Text blocks ---
        for block in page.get_layout_items(category_names="text"): 
            page_entry["texts"].append({
                "text": block.text.strip() if block.text else "",
                "bbox": block.bbox.get_export() if block.bbox else None
            })

        # --- Titles / Headings ---
        for t in page.get_layout_items(category_names="title"):
            page_entry["titles"].append({
                "text": t.text.strip() if t.text else "",
                "bbox": t.bbox.get_export() if t.bbox else None
            })

        # --- Lists ---
        for lst in page.get_layout_items(category_names="list"):
            page_entry["lists"].append({
                "text": lst.text.strip() if lst.text else "",
                "bbox": lst.bbox.get_export() if lst.bbox else None
            })

        # --- Tables ---
        if page.tables:
            for idx, table in enumerate(page.tables, start=1):
                table_html = table_to_html(table)
                wrapped_html = f"<h3>Page {page_num} - Table {idx}</h3>{table_html}"
                all_tables_html.append(wrapped_html)

                # Table JSON Logic (Keeping your logic but ensuring bbox safety)
                rows_json = []
                for cell in table.cells:
                    r, c = cell.row_number, cell.column_number
                    while len(rows_json) <= r: rows_json.append([])
                    while len(rows_json[r]) <= c: rows_json[r].append("")
                    rows_json[r][c] = cell.text.strip() if cell.text else ""
                
                page_entry["tables"].append({
                    "table_index": idx,
                    "rows": [row for row in rows_json if any(row)],
                    "bbox": table.bbox.get_export() if table.bbox else None
                })

        # --- Figures (Images) ---
        for img_idx, fig in enumerate(page.get_layouts(category_names="figure"), start=1):
            page_entry["figures"].append({
                "figure_index": img_idx,
                "bbox": fig.bbox.get_export() if fig.bbox else None
            })

        structured_data["pages"].append(page_entry)

    # 5. Save Files (HTML & JSON)
    # ... (Your existing saving logic) ...

    print("\n✅ Done!")

if __name__ == "__main__":
    main()