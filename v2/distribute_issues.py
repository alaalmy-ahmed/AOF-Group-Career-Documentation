"""
Daily: write one Excel file per branch with that day's quality issues,
inside a folder per area manager, with each issue's photo next to its row.
This is v1's notebook 01 as a script.

    output/managers/<Manager>/<Branch>.xlsx

That day's issues are checked first (validate_workbook.find_day_problems).
If any check fails, the problems are listed and no files are written.

Usage:
    python v2/distribute_issues.py
    REPORT_DATE=2026-10-26 python v2/distribute_issues.py     # the sample data's last day

Settings: WORKBOOK_PATH, MEALS_PATH, OUTPUT_DIR, REPORT_DATE (see settings.py).
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

import openpyxl
import pandas as pd
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from settings import OUTPUT_DIR, REPORT_DATE, WORKBOOK_PATH
from validate_workbook import excel_row, find_day_problems, print_problems, read_workbook

SHEET = "Reviewing Reports"
PHOTO_COLUMN = "Images"


# --------------------------------------------------------------------------------------------------------
# Read the photos

def read_photos(xlsx_path, sheet_name):
    """Return {excel_row: image_bytes} for every photo placed in a cell of the sheet.

    Excel's "Place in Cell" stores photos as rich values, which pandas and
    openpyxl can't see, so this reads the .xlsx package (a zip of XML files):

        cell vm="n"  ->  rich value n  ->  richValueRel.xml  ->  xl/media/imageN.png
    """
    NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
    NS_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    NS_WB = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    NS_RVR = "http://schemas.microsoft.com/office/spreadsheetml/2022/richvaluerel"

    with zipfile.ZipFile(xlsx_path) as z:
        if "xl/richData/richValueRel.xml" not in z.namelist():
            return {}                                   # the workbook has no in-cell photos

        # 1. Find the sheet's XML file: workbook.xml gives its relationship id,
        #    workbook.xml.rels turns the id into a file path.
        workbook = ET.parse(z.open("xl/workbook.xml")).getroot()
        sheet_id = next(s.get(f"{{{NS_DOC}}}id") for s in workbook.iter(f"{{{NS_WB}}}sheet")
                        if s.get("name") == sheet_name)
        workbook_rels = ET.parse(z.open("xl/_rels/workbook.xml.rels")).getroot()
        target = next(r.get("Target") for r in workbook_rels.iter(f"{{{NS_PKG}}}Relationship")
                      if r.get("Id") == sheet_id)
        sheet_path = "xl/" + target.lstrip("/").removeprefix("xl/")

        # 2. Every cell with a photo has a vm="n" attribute. Collect the rows for each n.
        #    The same photo can sit in several rows, so each n keeps a list.
        rows_of_vm = {}
        for cell in ET.parse(z.open(sheet_path)).getroot().iter(f"{{{NS_WB}}}c"):
            if cell.get("vm") is not None:
                row = int(re.search(r"\d+", cell.get("r")).group())       # "K5" -> 5
                rows_of_vm.setdefault(int(cell.get("vm")), []).append(row)

        # 3. Rich value n (counting from 1) points to the n-th relationship id,
        #    and each relationship id points to an image file.
        rel_ids = [r.get(f"{{{NS_DOC}}}id")
                   for r in ET.parse(z.open("xl/richData/richValueRel.xml")).getroot().iter(f"{{{NS_RVR}}}rel")]
        image_of_rel = {r.get("Id"): r.get("Target")
                        for r in ET.parse(z.open("xl/richData/_rels/richValueRel.xml.rels")).getroot()
                                   .iter(f"{{{NS_PKG}}}Relationship")}

        photos = {}
        for vm, rows in rows_of_vm.items():
            image_path = image_of_rel[rel_ids[vm - 1]].replace("..", "xl")   # "../media/image1.png"
            image = z.read(image_path)
            for row in rows:
                photos[row] = image
        return photos


# --------------------------------------------------------------------------------------------------------
# Write one branch file

def write_branch_file(path, rows, photos):
    """Write one formatted branch file. `photos` is {row position in `rows`: image bytes}."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active

    headers = list(rows.columns)
    if PHOTO_COLUMN not in headers:
        headers.append(PHOTO_COLUMN)
    centred = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin")

    # Header row, then one row per issue
    for col, header in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=col, value=header)
        cell.font = Font(size=10, name="Calibri", bold=True)
    for row, values in enumerate(rows.itertuples(index=False), start=2):
        for col, value in enumerate(values, start=1):
            sheet.cell(row=row, column=col, value=None if pd.isna(value) else value)

    # Every cell: centred, wrapped, thin border
    for line in sheet.iter_rows(min_row=1, max_row=len(rows) + 1, max_col=len(headers)):
        for cell in line:
            cell.alignment = centred
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Column widths (the photo column is ~200 px wide), dates as yyyy-mm-dd, fit to one page width
    for col, header in enumerate(headers, start=1):
        sheet.column_dimensions[get_column_letter(col)].width = 28.57 if header == PHOTO_COLUMN else 12
    if "Date" in headers:
        for cell in sheet[get_column_letter(headers.index("Date") + 1)][1:]:
            cell.number_format = "yyyy-mm-dd"
    sheet.page_setup.fitToWidth = 1

    # Photos: each one at the top-left of its row's photo cell, about the cell's size
    photo_letter = get_column_letter(headers.index(PHOTO_COLUMN) + 1)
    for position, image_bytes in photos.items():
        row = position + 2                                # + 2: header row, and Excel counts from 1
        image = Image(BytesIO(image_bytes))               # a fresh Image per file
        image.width, image.height = 206, 199              # pixels
        sheet.add_image(image, f"{photo_letter}{row}")
        sheet.row_dimensions[row].height = 150            # 200 px = 150 points

    workbook.save(path)


# --------------------------------------------------------------------------------------------------------

def main():
    sheets = read_workbook()
    problems = find_day_problems(sheets, REPORT_DATE)
    if problems:
        print_problems(problems)
        print("No files were written.")
        sys.exit(1)

    issues = sheets[SHEET]
    day_issues = issues[issues["Date"] == REPORT_DATE]
    if day_issues.empty:
        print(f"No issues on {REPORT_DATE}. Nothing to write.")
        return

    photos = read_photos(WORKBOOK_PATH, SHEET)
    # The checks made sure each issue's Manager matches the Managers sheet,
    # so the Manager column decides the folder.
    for (manager, branch), rows in day_issues.groupby(["Manager", "Branch"]):
        folder = os.path.join(OUTPUT_DIR, "managers", manager)
        os.makedirs(folder, exist_ok=True)
        # The row's position in this file -> its photo, found by its row in the workbook
        branch_photos = {position: photos[excel_row(index)]
                         for position, index in enumerate(rows.index) if excel_row(index) in photos}
        write_branch_file(os.path.join(folder, f"{branch}.xlsx"), rows, branch_photos)
        print(f"{manager}/{branch}.xlsx: {len(rows)} issue(s), {len(branch_photos)} photo(s)")

    print(f"Done: {len(day_issues)} issues from {REPORT_DATE}.")


if __name__ == "__main__":
    main()
