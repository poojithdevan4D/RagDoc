#!/usr/bin/env python3
"""
Government Document -> Audit Checklist Generator
Generates a master checklist (all checkpoints) and
a filtered audit sheet (depth-controlled subset).
"""
import os, sys, re, json, math

PDF_PATH    = "AFQMS_-_final_23_8_24.pdf"
MODEL_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "mistral-7b-instruct-v0.2.Q4_K_M.gguf")
OUTPUT_DOCX = "Audit_Checklist.docx"
MAX_ITEMS   = 10

if len(sys.argv) >= 2: PDF_PATH  = sys.argv[1]
if len(sys.argv) >= 3: MAX_ITEMS = int(sys.argv[2])

# ── Depth presets ───────────────────────────────────────
DEPTH_PRESETS = {
    "light":    {"n": 1, "m": 25},
    "standard": {"n": 2, "m": 50},
    "deep":     {"n": 3, "m": 75},
    "full":     {"n": 9999, "m": 100},
}

# ── Module-level constants ──────────────────────────────

# Pattern 1: dotted clause numbers — 2.1 / 21.B1.4 / 3.2.1
# Covers AFQMS, IMTAR
DOTTED_RE = re.compile(
    r'^((?:\d+|[A-Z])(?:\.[A-Z0-9]+){1,5})\s{1,6}(\S.{8,})',
    re.IGNORECASE
)

# Pattern 2: integer-titled paragraphs — "1. GOODS RECEIPT NUMBER"
# Covers AQA Directive top-level numbered items
# Must be: digit(s) + period + space + text of 4+ chars
NUMBERED_RE = re.compile(
    r'^(\d{1,2})\.\s{1,4}(\S.{3,})',
)

# Pattern 3: lettered sub-items — "(a) Visual Inspection - Check..."
# Covers AQA Directive (a)(b)(c) sub-activities
LETTERED_RE = re.compile(
    r'^\(([a-z])\)\s{1,4}(\S.{8,})',
)

# Legacy alias so detect_structure / compile_patterns still work
CLAUSE_RE = DOTTED_RE

SECTION_RE_FALLBACK = re.compile(
    r'^(PART|SECTION|CHAPTER|SUBPART|Subpart|ANNEX|APPENDIX)\s*[-–]?\s*([A-Z0-9]+)\b',
    re.IGNORECASE
)

# Section headers for directive-style docs (ALLCAPS standalone lines)
HEADER_RE = re.compile(
    r'^(INTRODUCTION|DEFINITIONS|CONCLUSION|PREFACE|'
    r'QA\s+ACTIVITIES|SAFETY|HANDLING|ASSEMBLY|ANNEXURE|APPENDIX)',
    re.IGNORECASE
)

OBLIGATION = re.compile(
    r'\b(shall|must|will\s+be|is\s+required|are\s+required|required\s+to|'
    r'to\s+be\s+(?:used|carried|checked|verified|performed|filled|submitted|'
    r'maintained|connected|fitted|followed|generated|screened|formed|accepted)|'
    r'ensure|maintain|establish|implement|document|verify|review|'
    r'check|inspect|audit|control|comply|responsible|'
    r'authoris|authoriz|monitor|record|report|assess|evaluate|screen)\b',
    re.IGNORECASE
)
# Sections whose content is never auditable (definitions, intro, conclusion etc.)
# When current_section matches any of these, all clauses inside are ignored.
SKIP_SECTIONS = {
    'DEFINITIONS', 'INTRODUCTION', 'PREFACE', 'CONCLUSION',
    'BACKGROUND', 'FOREWORD', 'SCOPE', 'PURPOSE', 'REFERENCES',
    'GLOSSARY', 'ABBREVIATIONS', 'ANNEXURE', 'ANNEX', 'APPENDIX',
    'TABLEOFCONTENTS', 'TOC',
}

def _section_is_skippable(section_name):
    normalised = re.sub(r'[^A-Z]', '', section_name.upper())
    for skip in SKIP_SECTIONS:
        skip_norm = re.sub(r'[^A-Z]', '', skip.upper())
        if skip_norm and (skip_norm in normalised or normalised.startswith(skip_norm)):
            return True
    return False

SKIP_LINE = re.compile(
    r'^(Figure|Fig\.|Table\s+\d|Appendix|Annex|Note:|NOTE:|'
    r'Page\s+\d+|Page\s+\|\s+\d+|\d+$|[ivxlIVXL]+$|[-–—]{3,}|www\.|http)',
    re.IGNORECASE
)

# ── Step 1: Read PDF ────────────────────────────────────
def read_pdf(path):
    print(f"\n[1/5] Reading: {path}")
    try:
        import pdfplumber
    except ImportError:
        sys.exit("ERROR: pip install pdfplumber")
    if not os.path.exists(path):
        sys.exit(f"ERROR: File not found - {path}")
    pages = []
    scanned = 0
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            try:
                t = pg.extract_text()
                text = t.strip() if t else ""
                # Heuristic: scanned page has very little extractable text
                # (OCR artifacts give a few chars but nothing readable)
                if len(text) < 30:
                    scanned += 1
                    pages.append("")
                else:
                    pages.append(text)
            except Exception:
                scanned += 1
                pages.append("")
    readable = sum(1 for p in pages if p)
    print(f"   {len(pages)} pages total — {readable} machine-readable, {scanned} scanned/empty (skipped).")
    if readable == 0:
        sys.exit("ERROR: No readable text found. PDF appears to be fully scanned.")
    return pages

# ── Step 2: Detect structure ────────────────────────────
STRUCTURE_PROMPT = """[INST] You are analyzing a government regulatory document.

Study the sample pages below and identify how major sections are labeled.
Give one example of a clause number from the document.

Respond with ONLY a JSON object, no explanation, no markdown:
{{
  "section_pattern": "^(Subpart\\\\s+[A-Z0-9]+)",
  "section_example": "Subpart B1",
  "clause_example": "21.B1.4"
}}

SAMPLE PAGES:
{sample}
[/INST]"""

def detect_structure(llm, pages):
    print("\n[2/5] Detecting document structure via LLM...")
    total = len(pages)
    indices = sorted(set([*range(5, min(11, total)), *range(min(30, total), min(36, total))]))
    sample = ""
    for i in indices:
        if i < total and pages[i].strip():
            sample += f"\n--- PAGE {i+1} ---\n{pages[i][:250]}\n"
        if len(sample) > 2000:
            break
    raw = llm(
        STRUCTURE_PROMPT.format(sample=sample),
        max_tokens=200, temperature=0.1,
        stop=["</s>", "[INST]"], echo=False,
    )["choices"][0]["text"].strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        try:
            s = json.loads(m.group())
            if "section_pattern" in s:
                print(f"   Section : {s.get('section_example','?')} -> {s.get('section_pattern')}")
                print(f"   Clause  : {s.get('clause_example','?')}")
                return s
        except Exception:
            pass
    print("   Could not detect structure - using fallback.")
    return None

# ── Step 3: Compile patterns ────────────────────────────
def compile_patterns(structure):
    if not structure:
        return CLAUSE_RE, SECTION_RE_FALLBACK
    try:
        section_re = re.compile(structure["section_pattern"], re.IGNORECASE)
        assert section_re.groups >= 1
        return CLAUSE_RE, section_re
    except Exception:
        print("   Section pattern invalid - using fallback.")
        return CLAUSE_RE, SECTION_RE_FALLBACK

# ── Step 4: Extract clauses ─────────────────────────────
def clean(t):
    t = re.sub(r'(?<=[A-Za-z]) (?=[A-Za-z] )', '', t)
    return re.sub(r'\s{2,}', ' ', t).strip()

def extract_clauses(pages, clause_re, section_re):
    """
    Multi-pattern clause extractor supporting three document styles:
      Style A — AFQMS/IMTAR: dotted refs like 2.1 / 21.B1.4
      Style B — AQA Directive: integer paragraphs "1. TITLE body..."
      Style C — AQA Directive sub-items: "(a) activity description"
    All three are tried on every line; whichever matches first wins.
    """
    print("\n[3/5] Extracting clauses...")
    current_section = ""
    pending_num     = None
    pending_section = ""
    pending_body    = []
    clauses         = []

    def flush():
        if pending_num and pending_body:
            # Skip clauses from non-auditable sections entirely
            if _section_is_skippable(pending_section):
                return
            body = clean(" ".join(pending_body))
            if len(body) > 20 and OBLIGATION.search(body):
                ref = f"{pending_section}/{pending_num}" if pending_section else pending_num
                clauses.append({"ref": ref, "text": body})

    # Track last integer-numbered parent for lettered sub-items
    last_int_num = None

    for page_text in pages:
        for line in page_text.split("\n"):
            line = line.strip()
            if not line or SKIP_LINE.match(line):
                continue

            # ── Section header detection ────────────────────────
            # Only treat as section if it clearly matches a known pattern
            # or is a short ALL-CAPS line (not mid-clause continuation)
            is_section = False
            for sr in [section_re, HEADER_RE]:
                sm = sr.match(line)
                if sm and len(line) < 70:
                    flush()
                    label = sm.group(0).strip()[:45]
                    current_section = re.sub(r'\s+', '-', label)
                    current_section = re.sub(r'[^A-Za-z0-9\-]', '-', current_section).strip('-')
                    pending_num  = None
                    pending_body = []
                    last_int_num = None
                    is_section   = True
                    break
            if is_section:
                continue

            # ── Pattern 1: dotted clause — 2.1 / 21.B1.4 ───────
            dm = DOTTED_RE.match(line)
            if dm:
                clause_num = dm.group(1)
                if re.match(r'^\d+\.0$', clause_num):
                    flush(); pending_num = None; pending_body = []; continue
                flush()
                pending_num     = clause_num
                pending_section = current_section
                pending_body    = [dm.group(2)]
                last_int_num    = None   # reset lettered context
                continue

            # ── Pattern 2: integer paragraph — "1. TITLE body" ──
            nm = NUMBERED_RE.match(line)
            if nm:
                # Skip if it looks like a plain list number with no real title
                body_text = nm.group(2).strip()
                if len(body_text) < 5:
                    continue
                # Skip pure page refs like "1. Introduction  4  4"
                if re.match(r'.+\s+\d+\s+\d+$', body_text):
                    continue
                flush()
                int_num         = nm.group(1)
                pending_num     = int_num
                pending_section = current_section
                pending_body    = [body_text]
                last_int_num    = int_num
                continue

            # ── Pattern 3: lettered sub-item — "(a) Check..." ───
            lm = LETTERED_RE.match(line)
            if lm:
                flush()
                letter      = lm.group(1)
                body_text   = lm.group(2).strip()
                parent      = last_int_num if last_int_num else (pending_num or "")
                ref_num     = f"{parent}({letter})" if parent else f"({letter})"
                pending_num     = ref_num
                pending_section = current_section
                pending_body    = [body_text]
                continue

            # ── Continuation line ────────────────────────────────
            if pending_num:
                # Flush if line looks like a new standalone heading
                if re.match(r'^[A-Z][A-Z\s\-\/\.]{8,}$', line) and len(line) < 60:
                    flush(); pending_num = None; pending_body = []
                else:
                    pending_body.append(line)

    flush()

    seen, unique = set(), []
    for c in clauses:
        if c["ref"] not in seen:
            seen.add(c["ref"])
            unique.append(c)
    print(f"   {len(unique)} unique obligation clauses found.")
    return unique

# ── Step 5: Load model ──────────────────────────────────
def load_model(model_path):
    print(f"\n[4/5] Loading model: {os.path.basename(model_path)}")
    try:
        from llama_cpp import Llama
    except ImportError:
        sys.exit("ERROR: pip install llama-cpp-python")
    if not os.path.exists(model_path):
        sys.exit(f"ERROR: Model not found - {model_path}")
    llm = Llama(model_path=model_path, n_ctx=4096,
                n_threads=os.cpu_count() or 4, verbose=False)
    print("   Ready.")
    return llm

# ── Step 6: Extract ALL checkpoints from a clause ───────
# Key change from previous version:
# Instead of generating ONE question per clause,
# we now ask the LLM to extract ALL distinct auditable
# requirements from the clause text as a numbered list.
# Each requirement becomes one row in the master checklist.

# DEFAULT_PROMPT is shown in the UI and can be edited by the auditor before generation.
# The {focus} slot is filled with any extra auditor instructions (empty string if none).
# The {text} slot is always filled with the clause text at runtime.
DEFAULT_CHECKPOINT_PROMPT = """[INST] You are a government quality auditor building a master audit checklist.

Read the clause text below carefully. Identify EVERY distinct auditable requirement in it.
Each sentence or sub-point that describes something that must be done, verified, maintained,
established, submitted, or complied with is a separate checkpoint.

Write each checkpoint as a short YES/NO audit question (max 15 words each).
Number them. Output ONLY the numbered list, nothing else.{focus}

Example output format:
1. Has the firm established a documented procedure for non-conformance control?
2. Does the procedure include root cause analysis?
3. Are corrective and preventive actions defined and implemented?

CLAUSE TEXT:
{text}
[/INST]"""

def extract_checkpoints(llm, clause, prompt_template=None, focus=""):
    """
    Returns a list of checkpoint question strings for one clause.
    prompt_template: full prompt string with {text} and {focus} placeholders.
                     If None, uses DEFAULT_CHECKPOINT_PROMPT.
    focus: optional auditor instruction appended to the prompt.
    """
    template = prompt_template if prompt_template else DEFAULT_CHECKPOINT_PROMPT
    # Format focus: if provided, add it as a new line after the main instruction
    focus_str = f"\n\nAuditor focus: {focus.strip()}" if focus and focus.strip() else ""
    try:
        filled = template.format(text=clause["text"][:800], focus=focus_str)
    except KeyError:
        # Template may not have {focus} slot if user removed it — that's fine
        filled = template.replace("{text}", clause["text"][:800])
    raw = llm(
        filled,
        max_tokens=400,
        temperature=0.15,
        top_p=0.9,
        repeat_penalty=1.1,
        stop=["</s>", "[INST]", "\n\n\n"],
        echo=False,
    )["choices"][0]["text"].strip()

    # Parse numbered list — handle "1.", "1)", "1 ." formats
    lines = raw.split("\n")
    checkpoints = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Strip leading number and punctuation
        cleaned = re.sub(r'^[\d]+[\.\)]\s*', '', line).strip()
        cleaned = cleaned.strip('"\'')
        cleaned = re.sub(r'\.+\?', '?', cleaned)
        cleaned = re.sub(r'\?+', '?', cleaned).strip()
        if len(cleaned) > 15:
            if not cleaned.endswith("?"):
                cleaned += "?"
            checkpoints.append(cleaned)

    return checkpoints if checkpoints else []

# ── Step 7: Filter checkpoints by depth ─────────────────
def filter_checkpoints(master_rows, n, m_pct, seed=None):
    """
    Given master rows (all checkpoints), return a randomly sampled subset.
    Per clause: take min(n, ceil(total * m_pct/100)) checkpoints, chosen
    randomly so each audit sheet varies — simulating real audit sampling.

    master_rows format:
      [{"ref": "Sec/2.1 (1/6)", "question": "...", "clause_base": "Sec/2.1"}, ...]
    """
    import random
    rng = random.Random(seed)  # seed=None means different each run

    from collections import OrderedDict
    grouped = OrderedDict()
    for row in master_rows:
        base = row["clause_base"]
        grouped.setdefault(base, []).append(row)

    filtered = []
    for base, rows in grouped.items():
        total = len(rows)
        by_m  = math.ceil(total * m_pct / 100)
        take  = min(n, by_m)
        take  = min(take, total)   # can't take more than exists
        take  = max(take, 1)       # always take at least 1
        # Random sample — preserves clause order within the selection
        selected = sorted(rng.sample(rows, take), key=lambda r: rows.index(r))
        filtered.extend(selected)

    return filtered

# ── Step 8: Write Word document ─────────────────────────
def create_docx(rows, output_path, doc_title="", sheet_label="MASTER AUDIT CHECKLIST"):
    print(f"\n[5/5] Writing: {output_path}")
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
    except ImportError:
        sys.exit("ERROR: pip install python-docx")

    doc = Document()
    for sec in doc.sections:
        sec.top_margin = sec.bottom_margin = Inches(0.75)
        sec.left_margin = sec.right_margin = Inches(0.65)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(sheet_label)
    r.bold = True; r.font.size = Pt(13)

    if doc_title:
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r2 = p2.add_run(doc_title)
        r2.italic = True; r2.font.size = Pt(9)

    doc.add_paragraph()

    HEADERS    = ["SL\nNO.", "Clause #", "Sub\nPoint", "DESCRIPTION",
                  "ORG. PROCEDURE #",
                  "ADEQUACY\nYES / NO",
                  "COMPLIANT\nYES / NO",
                  "REMARKS"]
    COL_WIDTHS = [0.32, 1.30, 0.45, 2.90, 1.10, 0.72, 0.72, 1.00]

    table = doc.add_table(rows=1, cols=len(HEADERS))
    table.style = "Table Grid"

    def shade(cell, color):
        tc = cell._tc; tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), color); tcPr.append(shd)

    def pad(cell):
        tc = cell._tc; tcPr = tc.get_or_add_tcPr()
        tcM = OxmlElement("w:tcMar")
        for side, val in [("top",50),("bottom",50),("left",80),("right",80)]:
            n = OxmlElement(f"w:{side}")
            n.set(qn("w:w"), str(val)); n.set(qn("w:type"), "dxa"); tcM.append(n)
        tcPr.append(tcM)

    for cell, w, h in zip(table.rows[0].cells, COL_WIDTHS, HEADERS):
        cell.width = Inches(w); pad(cell)
        p = cell.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(h); run.bold = True; run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF); shade(cell, "1F4E79")

    for idx, item in enumerate(rows, start=1):
        row = table.add_row()
        bg = "EBF3FB" if idx % 2 == 0 else "FFFFFF"
        vals = [
            str(idx),
            item.get("clause_base", item.get("ref", "")),
            item.get("subpoint", ""),
            item["question"],
            "", "", "", ""
        ]
        for i, (cell, val) in enumerate(zip(row.cells, vals)):
            cell.width = Inches(COL_WIDTHS[i]); pad(cell); shade(cell, bg)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if i == 3 else WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(val); run.font.size = Pt(8)

    doc.save(output_path)
    print(f"   Saved -> {output_path}  ({len(rows)} items)")

# ── Step 9: Build master rows from clauses ───────────────
def build_master(llm, clauses, max_items=0, progress_cb=None,
                 prompt_template=None, focus=""):
    """
    For each clause, extract all checkpoints.
    prompt_template: editable prompt from UI (None = use default).
    focus: auditor focus instruction.
    Returns flat list of rows with subpoint refs.
    """
    subset = clauses[:max_items] if max_items else clauses
    total  = len(subset)
    master = []

    for i, clause in enumerate(subset, 1):
        if progress_cb:
            progress_cb(i, total, clause["ref"])

        checkpoints = extract_checkpoints(llm, clause,
                                          prompt_template=prompt_template,
                                          focus=focus)

        if not checkpoints:
            print(f"   [{i:>3}/{total}] {clause['ref']} — no checkpoints extracted")
            continue

        n = len(checkpoints)
        for j, q in enumerate(checkpoints, 1):
            master.append({
                "clause_base": clause["ref"],
                "subpoint":    f"{j}/{n}",
                "ref":         f"{clause['ref']} ({j}/{n})",
                "question":    q,
            })
        print(f"   [{i:>3}/{total}] {clause['ref']} — {n} checkpoints")

    return master

# ── Main ────────────────────────────────────────────────
def main():
    pages              = read_pdf(PDF_PATH)
    llm                = load_model(MODEL_PATH)
    structure          = detect_structure(llm, pages)
    clause_re, sect_re = compile_patterns(structure)
    clauses            = extract_clauses(pages, clause_re, sect_re)

    if not clauses:
        sys.exit("\nERROR: No clauses found.")

    doc_name = os.path.splitext(os.path.basename(PDF_PATH))[0].replace("_", " ")
    print(f"\n   Extracting checkpoints for {min(MAX_ITEMS,len(clauses)) if MAX_ITEMS else len(clauses)} clauses...")

    master = build_master(llm, clauses, max_items=MAX_ITEMS)

    if not master:
        sys.exit("\nERROR: No checkpoints extracted.")

    # Write master
    create_docx(master, OUTPUT_DOCX, doc_title=doc_name,
                sheet_label="MASTER AUDIT CHECKLIST")
    print(f"\nMaster: {len(master)} checkpoints -> {OUTPUT_DOCX}")

    # Write filtered sheet (standard depth: n=2, m=50%)
    filtered = filter_checkpoints(master, n=2, m_pct=50)
    filtered_path = OUTPUT_DOCX.replace(".docx", "_filtered.docx")
    create_docx(filtered, filtered_path, doc_title=doc_name,
                sheet_label="AUDIT SHEET — STANDARD DEPTH (N=2, M=50%)")
    print(f"Filtered: {len(filtered)} checkpoints -> {filtered_path}")

if __name__ == "__main__":
    main()