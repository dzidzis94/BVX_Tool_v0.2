#!/usr/bin/env python3
"""
Frame specification PDF -> ONE Hundegger SC .bvx job.

    python app.py 1R-1_2.pdf                  # stops if the drawing has conflicts
    python app.py 1R-1_2.pdf --skip-conflicts # writes <name>_PARTIAL.bvx without conflicting numbers

CNC Part Number from the drawing is used unchanged as PartId. Numbers are never
renumbered: if one number has different sizes/lengths it is reported as a
conflict, so the drawing can be fixed and the script run again.
Straight 90 deg saw cuts only (angles/laps are not in this table).
Needs `pdftotext` (poppler) on PATH.
"""
import os
import re
import subprocess
import sys
import tempfile
import uuid
from collections import OrderedDict, defaultdict
from pathlib import Path
from xml.sax.saxutils import quoteattr

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

OPERATOR = "Operator"          # put the operator name here if needed
MACHINE_NUMBER = "9665"
PROG_VERSION = "2.28.35.56151"

ROW = re.compile(
    r"^\s*(?P<mark>\S+)\s+(?P<job>R-\d+_\d+)\s+(?P<num>\d+)\s+"
    r"(?P<desc>.+?)\s+(?P<count>\d+)\s+(?P<b>\d+)\s*x\s*(?P<d>\d+)\s+(?P<length>\d+)\s*$")

app = Flask(__name__)
UPLOAD_FOLDER = tempfile.gettempdir()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def read_rows(pdf):
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout
    rows = []
    for line in text.splitlines():
        m = ROW.match(line.split("3D Frame")[0])
        if m:
            g = m.groupdict()
            rows.append(dict(mark=g["mark"], name=g["job"], num=int(g["num"]),
                             desc=g["desc"].strip(), count=int(g["count"]),
                             width=int(g["b"]), height=int(g["d"]), length=int(g["length"])))
    return rows


def analyse(rows):
    by_num = OrderedDict()
    for r in rows:
        by_num.setdefault(r["num"], []).append(r)
    parts, conflicts = {}, {}
    for num, rs in by_num.items():
        if len({(r["width"], r["height"], r["length"]) for r in rs}) > 1:
            conflicts[num] = rs
        else:
            parts[num] = dict(rs[0], count=sum(r["count"] for r in rs),
                              marks=list(dict.fromkeys(r["mark"] for r in rs)), rows=rs)
    marks = defaultdict(set)
    for r in rows:
        marks[r["mark"]].add((r["width"], r["height"], r["length"]))
    mark_warn = {m: s for m, s in marks.items() if len(s) > 1}
    return parts, conflicts, mark_warn


def fmt(x, nd):
    return f"{x:.{nd}f}".rstrip("0").rstrip(".") if x else "0"


def build_xml(job, parts):
    ps = [parts[n] for n in sorted(parts)]
    lin = sum(p["length"] * p["count"] for p in ps) / 1000
    cub = sum(p["width"] * p["height"] * p["length"] * p["count"] for p in ps) / 1e9
    qty = sum(p["count"] for p in ps)
    o = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
         "<!--This file contains SC 1 job data. Please do not modify-->",
         f"<!--Job : {job}-->",
         f'<Job Operator={quoteattr(OPERATOR)} DeliveryDate="30.12.1899" ProcessingTime="0" '
         f'ReqLinMeter="{fmt(lin, 2)}" ReqQuantity="{qty}" CubicMeter="{fmt(cub, 5)}" RemainingTime="0" '
         f'CutLinMeter="0" Complete="no" Positions="{len(ps)}" FinishedQuantity="0" '
         f'MachineNumber="{MACHINE_NUMBER}" ProgVersion="{PROG_VERSION}" BvxVersion="1.0" '
         f'BoardQuantity="0" BoardPartQuantity="0" TotalPartLength="0" TotalBoardLength="0" '
         f'Autotext="no" PlaningLength="0" PlaningSurface="0" Key="{{{str(uuid.uuid4()).upper()}}}">',
         "\t<AttDefs/>", "\t<Parts>"]
    for p in ps:
        o += [f'\t\t<Part PartId="{p["num"]}" Width="{p["width"]}" Height="{p["height"]}" '
              f'Length="{p["length"]}" Dimension="Rectangular" ReqQuantity="{p["count"]}" '
              f'FinishedQuantity="0" Name={quoteattr("+".join(p["marks"]))} Time="0" ReqLength="{p["length"]}" '
              f'Problem="0" BoardNumber="0" ValidL="yes" EjectionPoint="0" PlaningLength="0" PlaningSurface="0">',
              "\t\t\t<Operations>",
              '\t\t\t\t<SawCut ReferenceSide="3" Orientation="Right" Angle="90" Bevel="90" '
              'CrossMeas1="0" CrossMeas2="0" LengthMeas="0"/>',
              f'\t\t\t\t<SawCut ReferenceSide="3" Orientation="Left" Angle="90" Bevel="90" '
              f'CrossMeas1="0" CrossMeas2="0" LengthMeas="{p["length"]}"/>',
              "\t\t\t</Operations>", "\t\t\t<MetaData>", "\t\t\t\t<CustomerNode/>",
              '\t\t\t\t<RotationNode RotationY="0" RotationX="0"/>', "\t\t\t</MetaData>", "\t\t</Part>"]
    return "\n".join(o + ["\t</Parts>", "\t<Boards/>", "</Job>", ""])


def report(rows, parts, conflicts, mark_warn):
    L = [f"Rows read: {len(rows)}, pieces: {sum(r['count'] for r in rows)}", ""]
    if conflicts:
        L.append("CONFLICTS - same CNC part number, different size/length (NOT written):")
        for n, rs in conflicts.items():
            L.append(f"  Number {n}:")
            for r in rs:
                L.append(f"    {r['mark']:6} {r['name']:6} {r['count']} pcs  "
                         f"{r['width']} x {r['height']}  L={r['length']}")
        L.append("")
    if mark_warn:
        L.append("CHECK - same mark used for different sizes/lengths:")
        for m, s in mark_warn.items():
            L.append(f"  {m}: " + "; ".join(f"{w}x{h} L={l}" for w, h, l in sorted(s)))
        L.append("")
    shared = [p for p in parts.values() if len(p["rows"]) > 1]
    if shared:
        L.append("CHECK - one number used by several rows (identical parts, quantities added):")
        for p in shared:
            L.append(f"  Number {p['num']}: " + " + ".join(f"{r['mark']}({r['count']})" for r in p["rows"])
                     + f" = {p['count']} pcs, {p['width']}x{p['height']} L={p['length']}")
        L.append("")
    return "\n".join(L)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded.", "report": ""}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"success": False, "error": "No file selected.", "report": ""}), 400

    skip_conflicts = request.form.get("skip_conflicts", "false").lower() in ("true", "1", "on")

    original_filename = secure_filename(file.filename) or "document.pdf"
    stem = Path(original_filename).stem or "document"

    temp_pdf = Path(UPLOAD_FOLDER) / f"upload_{uuid.uuid4().hex}_{original_filename}"
    file.save(temp_pdf)

    try:
        rows = read_rows(temp_pdf)
        parts, conflicts, mark_warn = analyse(rows)
        rep = report(rows, parts, conflicts, mark_warn)

        if conflicts and not skip_conflicts:
            rep_str = rep + "\nNot written: fix the conflicts in the drawing (or use --skip-conflicts)."
            return jsonify({
                "success": False,
                "report": rep_str,
                "error": "Not written: fix the conflicts in the drawing (or check '--skip-conflicts').",
                "download_url": None
            })

        out_filename = f"{stem}{'_PARTIAL' if conflicts else ''}.bvx"
        out_path = Path(UPLOAD_FOLDER) / out_filename
        out_path.write_text(build_xml(stem, parts), encoding="utf-8")

        summary = f"Written {out_filename}: {len(parts)} positions, {sum(p['count'] for p in parts.values())} pieces"
        full_report = rep + "\n" + summary

        return jsonify({
            "success": True,
            "report": full_report,
            "error": None,
            "filename": out_filename,
            "download_url": f"/download/{out_filename}"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Error processing PDF: {str(e)}",
            "report": f"Error processing PDF: {str(e)}",
            "download_url": None
        }), 500
    finally:
        if temp_pdf.exists():
            try:
                temp_pdf.unlink()
            except OSError:
                pass


@app.route("/download/<filename>")
def download_file(filename):
    safe_filename = secure_filename(filename)
    return send_from_directory(app.config['UPLOAD_FOLDER'], safe_filename, as_attachment=True)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    skip = "--skip-conflicts" in sys.argv
    pdf = Path(args[0])
    rows = read_rows(pdf)
    parts, conflicts, mark_warn = analyse(rows)
    rep = report(rows, parts, conflicts, mark_warn)
    print(rep)
    Path(f"{pdf.stem}_report.txt").write_text(rep, encoding="utf-8")
    if conflicts and not skip:
        sys.exit("Not written: fix the conflicts in the drawing (or use --skip-conflicts).")
    out = Path(f"{pdf.stem}{'_PARTIAL' if conflicts else ''}.bvx")
    out.write_text(build_xml(pdf.stem, parts), encoding="utf-8")
    print(f"Written {out}: {len(parts)} positions, {sum(p['count'] for p in parts.values())} pieces")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        main()
    else:
        app.run(host="0.0.0.0", port=5000, debug=True)
