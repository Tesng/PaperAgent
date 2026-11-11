#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PaperAgent 工具腳本（流程與規範見 AGENT.md）

  python3 scripts/paper_tools.py pending
  python3 scripts/paper_tools.py text    <pdf> --slug <slug>
  python3 scripts/paper_tools.py render  <pdf> --slug <slug> [--pages 1-3,5] [--dpi 90]
  python3 scripts/paper_tools.py figures <pdf> --slug <slug> [--dpi 200]
  python3 scripts/paper_tools.py crop    <pdf> --page N --rect x0,y0,x1,y1 --out <png> [--dpi 220]
  python3 scripts/paper_tools.py new     <slug> --pdf <pdf>
  python3 scripts/paper_tools.py check   [<slug> ...]
  python3 scripts/paper_tools.py index

只有 text / render / figures / crop 需要 PyMuPDF（pip install pymupdf）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPERS_DIR = os.path.join(ROOT, "papers")
NOTES_DIR = os.path.join(ROOT, "notes")
WORK_DIR = os.path.join(ROOT, "work")
FIG_DIR = os.path.join(ROOT, "assets", "figures")
DATA_FILE = os.path.join(ROOT, "data", "papers.json")
TEMPLATE = os.path.join(ROOT, "templates", "note-template.md")

REQUIRED_FIELDS = ["slug", "title", "short", "authors", "year", "venue",
                   "pdf", "tags", "one_liner", "added", "status"]
LIST_FIELDS = {"authors", "tags", "builds_on", "superseded_by"}
REQUIRED_SECTIONS = ["## 0. 問題", "## 1. 核心想法", "## 2. 資料流",
                     "## 3. 怎麼訓練", "## 4. 證據與位置"]
OPTIONAL_SECTIONS = ["## 5. 限制與疑問", "## 參考"]
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PLACEHOLDER = "〔填寫"

try:  # 讓 Windows / 舊終端機也能印中文
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ───────────────────────── 共用工具 ─────────────────────────

def pdf_lib():
    try:
        import pymupdf  # PyMuPDF >= 1.24
        return pymupdf
    except ImportError:
        try:
            import fitz  # 舊版 PyMuPDF
            return fitz
        except ImportError:
            sys.exit("❌ 需要 PyMuPDF：pip install pymupdf（或 pip install -r requirements.txt）")


def rel(path: str) -> str:
    """轉成相對專案根目錄、使用 / 的路徑。"""
    p = os.path.relpath(os.path.abspath(path), ROOT)
    return p.replace(os.sep, "/")


def slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "paper"


def work_dir(pdf: str, slug: str | None, sub: str = "") -> str:
    key = slug or slugify(os.path.splitext(os.path.basename(pdf))[0])
    d = os.path.join(WORK_DIR, key, sub) if sub else os.path.join(WORK_DIR, key)
    os.makedirs(d, exist_ok=True)
    return d


def open_pdf(path: str):
    if not os.path.isfile(path):
        sys.exit(f"❌ 找不到 PDF：{path}")
    return pdf_lib().open(path)


# ───────────────────── Frontmatter（簡化 YAML） ─────────────────────

_DQ = re.compile(r'^"((?:[^"\\]|\\.)*)"')
_SQ = re.compile(r"^'((?:[^']|'')*)'")


def _scalar(v: str):
    v = v.strip()
    m = _DQ.match(v)
    if m:
        return m.group(1).replace('\\"', '"').replace("\\\\", "\\")
    m = _SQ.match(v)
    if m:
        return m.group(1).replace("''", "'")
    v = re.sub(r"\s+#.*$", "", v).strip()
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if v in ("", "null", "~"):
        return None
    if v in ("true", "false"):
        return v == "true"
    return v


def _inline_list(s: str) -> list:
    items, buf, quote = [], "", None
    for ch in s:
        if quote:
            if ch == quote:
                quote = None
            else:
                buf += ch
        elif ch in "\"'":
            quote = ch
        elif ch == ",":
            items.append(buf.strip())
            buf = ""
        else:
            buf += ch
    items.append(buf.strip())
    return [i for i in items if i]


def parse_yaml_subset(raw: str) -> dict:
    data: dict = {}
    key = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s+-\s+(.*)$", line) or re.match(r"^-\s+(.*)$", line)
        if m and key is not None and isinstance(data.get(key), list):
            val = _scalar(m.group(1))
            if val is not None:
                data[key].append(str(val))
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == "":
            data[key] = []
        elif val.startswith("["):
            end = val.rfind("]")
            data[key] = _inline_list(val[1:end] if end != -1 else val[1:])
        else:
            data[key] = _scalar(val)
    return data


def read_note(path: str) -> tuple[dict, str, str]:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not m:
        return {}, text, text
    return parse_yaml_subset(m.group(1)), text[m.end():], text


def norm_meta(meta: dict) -> dict:
    out = {}
    for k, v in meta.items():
        if k in LIST_FIELDS:
            if v is None or v == "":
                v = []
            elif not isinstance(v, list):
                v = [v]
            v = [str(x).strip() for x in v if str(x).strip()]
        else:
            if isinstance(v, list):
                v = ", ".join(map(str, v))
            if v is None:
                v = ""
        out[k] = v
    return out


def all_notes() -> list[str]:
    return sorted(p for p in glob.glob(os.path.join(NOTES_DIR, "*.md"))
                  if not os.path.basename(p).startswith("_"))


def list_pdfs() -> list[str]:
    found = []
    for dirpath, _, files in os.walk(PAPERS_DIR):
        for fn in files:
            if fn.lower().endswith(".pdf") and not fn.startswith("."):
                found.append(rel(os.path.join(dirpath, fn)))
    return sorted(found)


def norm_pdf_path(p: str) -> str:
    p = (p or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


# ───────────────────────── pending ─────────────────────────

def cmd_pending(args):
    pdfs = list_pdfs()
    used = {}
    for path in all_notes():
        meta, _, _ = read_note(path)
        used[norm_pdf_path(str(meta.get("pdf") or ""))] = os.path.basename(path)
    pending = [p for p in pdfs if p not in used]
    print(f"papers/ 共 {len(pdfs)} 個 PDF，已整理 {len(pdfs) - len(pending)} 篇。")
    if pending:
        print(f"\n待處理（{len(pending)}）：")
        for p in pending:
            print(f"  - {p}")
    else:
        print("✅ 沒有待處理的 PDF。")
    orphans = [(n, p) for p, n in used.items() if p and p not in pdfs]
    if orphans:
        print("\n⚠️  以下講義的 pdf 欄位找不到檔案：")
        for n, p in orphans:
            print(f"  - notes/{n} → {p}")


# ───────────────────────── text ─────────────────────────

HEADING_RES = [
    re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+([A-Z][^\n]{2,70})$"),
    re.compile(r"^([IVX]{1,5})\.\s+([A-Z][A-Z \-:&,]{2,60})$"),
    re.compile(r"^([A-H](?:\.\d{1,2})?)\.?\s+([A-Z][^\n]{2,60})$"),
    re.compile(r"^(Abstract|References|Bibliography|Appendix|Acknowledg(?:e)?ments?|Conclusions?)\b.{0,30}$", re.I),
]


def cmd_text(args):
    doc = open_pdf(args.pdf)
    wd = work_dir(args.pdf, args.slug)
    out = os.path.join(wd, "fulltext.txt")
    chunks, headings = [], []
    arxiv = None
    for i, page in enumerate(doc, 1):
        t = page.get_text("text")
        chunks.append(f"\n=== Page {i} ===\n{t}")
        if arxiv is None:
            m = re.search(r"arXiv:\s?(\d{4}\.\d{4,5})(v\d+)?", t)
            if m:
                arxiv = m.group(1)
        for line in t.splitlines():
            s = line.strip()
            if 3 <= len(s) <= 80 and any(r.match(s) for r in HEADING_RES):
                if not re.search(r"\d{3,}|[.,]\s*$|\bet al\b", s):
                    headings.append((i, s))
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(chunks))

    first = [l.strip() for l in doc[0].get_text("text").splitlines() if l.strip()]
    meta_title = (doc.metadata or {}).get("title") or ""
    nchar = sum(len(c) for c in chunks)
    print(f"📄 {rel(args.pdf)}")
    print(f"   頁數：{doc.page_count}｜字元數：{nchar:,}")
    if meta_title:
        print(f"   PDF metadata 標題：{meta_title}")
    print(f"   首頁前幾行：{' / '.join(first[:4])}")
    if arxiv:
        print(f"   arXiv：{arxiv}")
    if headings:
        print("   偵測到的章節（頁碼）：")
        seen = set()
        for p, h in headings[:60]:
            if h in seen:
                continue
            seen.add(h)
            print(f"     p{p:<3} {h}")
    print(f"✅ 全文已寫入 {rel(out)}")


# ───────────────────────── render ─────────────────────────

def parse_pages(spec: str | None, n: int) -> list[int]:
    if not spec:
        return list(range(1, n + 1))
    pages = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.update(range(int(a or 1), int(b or n) + 1))
        else:
            pages.add(int(part))
    return sorted(p for p in pages if 1 <= p <= n)


def cmd_render(args):
    doc = open_pdf(args.pdf)
    out_dir = work_dir(args.pdf, args.slug, "pages")
    pages = parse_pages(args.pages, doc.page_count)
    for p in pages:
        pix = doc[p - 1].get_pixmap(dpi=args.dpi)
        fn = os.path.join(out_dir, f"p{p:03d}.png")
        pix.save(fn)
        print(f"  {rel(fn)}  ({pix.width}×{pix.height})")
    print(f"✅ 已輸出 {len(pages)} 頁預覽（{args.dpi} dpi）")


# ───────────────────────── figures ─────────────────────────

# 圖說格式：「Figure 1: …」「Fig. 1. …」，或沒有標點的「Figure 1 Overview …」（後面接大寫字）
# 內文引用如「Figure 3 shows …」後面是小寫字，不會被當成圖說
CAPTION_RE = re.compile(r"^\s*((?i:Figure|Fig\.?|Table|Tab\.))\s*([0-9]{1,2}|[IVX]{1,5})(?:\s*[:.|]|\s+[A-Z(])")


def _r(b):  # bbox -> tuple
    return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))


def _w(r):
    return r[2] - r[0]


def _h(r):
    return r[3] - r[1]


def _union(rs):
    return (min(r[0] for r in rs), min(r[1] for r in rs),
            max(r[2] for r in rs), max(r[3] for r in rs))


def _text_blocks(page):
    blocks = []
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type") != 0:
            continue
        lines = []
        for ln in b.get("lines", []):
            t = "".join(s.get("text", "") for s in ln.get("spans", []))
            if t.strip():
                lines.append((_r(ln["bbox"]), t))
        if not lines:
            continue
        text = " ".join(t for _, t in lines).strip()
        blocks.append({"bbox": _r(b["bbox"]), "text": text, "lines": lines})
    return blocks


def _graphics(page, W, H):
    rects = []
    try:
        for info in page.get_image_info():
            r = _r(info["bbox"])
            if _w(r) > 2 or _h(r) > 2:
                rects.append(r)
    except Exception:
        pass
    try:
        for d in page.get_drawings():
            r = _r(d["rect"])
            if _w(r) * _h(r) > 0.85 * W * H:
                continue  # 整頁背景框
            if _w(r) < 0.5 and _h(r) < 0.5:
                continue
            rects.append(r)
    except Exception:
        pass
    return rects


def _split_captions(blocks):
    """找出圖說區塊。回傳 (kind, number, bbox, text, block_index)。"""
    caps = []
    for idx, b in enumerate(blocks):
        for li, (lb, lt) in enumerate(b["lines"]):
            m = CAPTION_RE.match(lt)
            if not m:
                continue
            if li == 0:
                bbox, text = b["bbox"], b["text"]
            else:
                rest = b["lines"][li:]
                bbox = _union([x for x, _ in rest])
                text = " ".join(t for _, t in rest)
            kind = "table" if m.group(1).lower().startswith("tab") else "figure"
            caps.append((kind, m.group(2), bbox, text.strip(), idx))
            break
    return caps


def _is_margin_noise(r, W, H):
    if r[3] < 0.055 * H or r[1] > 0.95 * H:  # 頁首、頁尾
        return True
    if _w(r) < 25 and _h(r) > 150:  # arXiv 側邊直排浮水印
        return True
    return False


def _is_paragraph(b, ref_w):
    r, text = b["bbox"], b["text"]
    if len(text) < 120 or _w(r) < 0.75 * ref_w or len(b["lines"]) < 2:
        return False
    full = sum(1 for lb, _ in b["lines"] if _w(lb) >= 0.8 * _w(r))
    if full / len(b["lines"]) < 0.5:
        return False
    chars = [c for c in text if not c.isspace()]
    letters = sum(c.isalpha() for c in chars)
    digits = sum(c.isdigit() for c in chars)
    return letters / max(1, len(chars)) >= 0.7 and digits / max(1, len(chars)) < 0.15


def _span_for(cap, W):
    cx = (cap[0] + cap[2]) / 2
    if _w(cap) > 0.55 * W or abs(cx - W / 2) < 0.08 * W:
        return (0.0, W)
    return (0.0, W / 2 + 4) if cx < W / 2 else (W / 2 - 4, W)


def _in_span(r, span):
    cx = (r[0] + r[2]) / 2
    return span[0] <= cx <= span[1] and r[0] >= span[0] - 8 and r[2] <= span[1] + 8


def _region(cap, cap_idx, blocks, cap_idxs, gfx, span, W, H, direction):
    ref_w = min(span[1] - span[0], 0.5 * W)
    barriers = [b["bbox"] for i, b in enumerate(blocks)
                if i != cap_idx and _in_span(b["bbox"], span)
                and (i in cap_idxs or _is_paragraph(b, ref_w))]
    if direction == "up":
        lo = max([0.05 * H] + [r[3] for r in barriers if r[3] <= cap[1] + 1])
        hi = cap[1]
    else:
        lo = cap[3]
        hi = min([0.95 * H] + [r[1] for r in barriers if r[1] >= cap[3] - 1])
    if hi - lo < 12:
        return None, "low"
    inside = lambda r: _in_span(r, span) and r[1] >= lo - 2 and r[3] <= hi + 2
    items = [g for g in gfx if inside(g)]
    texts = [b["bbox"] for i, b in enumerate(blocks)
             if i != cap_idx and i not in cap_idxs and inside(b["bbox"])
             and not _is_margin_noise(b["bbox"], W, H)]
    if not items and not texts:
        return None, "low"
    region = _union(items + texts)
    conf = "high" if items else "low"
    if _h(region) < 15 or _h(region) > 0.85 * H:
        conf = "low"
    return region, conf


def cmd_figures(args):
    doc = open_pdf(args.pdf)
    out_dir = work_dir(args.pdf, args.slug, "candidates")
    for old in glob.glob(os.path.join(out_dir, "*.png")):
        os.remove(old)
    results = []
    for pno in range(doc.page_count):
        page = doc[pno]
        pr = page.rect
        W, H = pr.width, pr.height
        blocks = _text_blocks(page)
        caps = _split_captions(blocks)
        if not caps:
            continue
        gfx = _graphics(page, W, H)
        cap_idxs = {c[4] for c in caps}
        for kind, num, cap, text, idx in caps:
            span = _span_for(cap, W)
            order = ["down", "up"] if kind == "table" else ["up", "down"]
            region, conf = None, "low"
            for direction in order:  # 圖說通常在圖下方、表上方；第一個方向找不到才試另一邊
                region, conf = _region(cap, idx, blocks, cap_idxs, gfx, span, W, H, direction)
                if region is not None:
                    break
            if region is None:
                continue
            pad = 3
            clip = (max(0, region[0] - pad), max(0, region[1] - pad),
                    min(W, region[2] + pad), min(H, region[3] + pad))
            prefix = "tab" if kind == "table" else "fig"
            cid = f"{prefix}{num}_p{pno + 1}"
            fn = os.path.join(out_dir, f"{cid}.png")
            Rect = pdf_lib().Rect
            pix = page.get_pixmap(clip=Rect(clip[0] + pr.x0, clip[1] + pr.y0,
                                            clip[2] + pr.x0, clip[3] + pr.y0), dpi=args.dpi)
            pix.save(fn)
            frac = [round(clip[0] / W, 4), round(clip[1] / H, 4),
                    round(clip[2] / W, 4), round(clip[3] / H, 4)]
            results.append({
                "id": cid, "kind": kind, "number": num, "page": pno + 1,
                "rect": frac, "confidence": conf, "file": rel(fn),
                "caption": re.sub(r"\s+", " ", text)[:240],
            })
    with open(os.path.join(out_dir, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    if not results:
        print("⚠️  沒有偵測到圖說（Figure N / Table N）。請用 render 看頁面，再用 crop 手動擷取。")
        return
    print(f"偵測到 {len(results)} 個候選區塊（{args.dpi} dpi）：")
    for r in results:
        flag = "" if r["confidence"] == "high" else "  ⚠️ 信心低，請目視確認"
        print(f"  [{r['id']:<12}] p{r['page']:<3} rect={','.join(map(str, r['rect']))}{flag}")
        print(f"      {r['caption'][:110]}")
    print(f"✅ 候選圖在 {rel(out_dir)}/，範圍記錄在 candidates.json")
    print("   下一步：逐張打開檢查；切不好就用 crop --rect 微調。")


# ───────────────────────── crop ─────────────────────────

def cmd_crop(args):
    doc = open_pdf(args.pdf)
    if not 1 <= args.page <= doc.page_count:
        sys.exit(f"❌ 頁碼超出範圍（1–{doc.page_count}）")
    page = doc[args.page - 1]
    pr = page.rect
    try:
        x0, y0, x1, y1 = [float(v) for v in args.rect.split(",")]
    except ValueError:
        sys.exit("❌ --rect 格式為 x0,y0,x1,y1，例如 0.08,0.06,0.92,0.41")
    if max(x0, y0, x1, y1) <= 1.0:  # 頁面比例
        x0, x1 = x0 * pr.width, x1 * pr.width
        y0, y1 = y0 * pr.height, y1 * pr.height
    if x1 <= x0 or y1 <= y0:
        sys.exit("❌ rect 範圍無效（x1 必須 > x0、y1 必須 > y0）")
    Rect = pdf_lib().Rect
    clip = Rect(pr.x0 + x0, pr.y0 + y0, pr.x0 + x1, pr.y0 + y1) & pr
    pix = page.get_pixmap(clip=clip, dpi=args.dpi)
    out = args.out
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    pix.save(out)
    print(f"✅ {rel(out)}  ({pix.width}×{pix.height}, p{args.page}, {args.dpi} dpi)")


# ───────────────────────── new ─────────────────────────

def cmd_new(args):
    slug = args.slug
    if not SLUG_RE.match(slug):
        sys.exit("❌ slug 只能用小寫英數與連字號，例如 2024-openvla")
    path = os.path.join(NOTES_DIR, f"{slug}.md")
    if os.path.exists(path) and not args.force:
        sys.exit(f"❌ {rel(path)} 已存在（要覆蓋請加 --force）")
    pdf = norm_pdf_path(rel(args.pdf) if os.path.isabs(args.pdf) else args.pdf)
    if not os.path.isfile(os.path.join(ROOT, pdf)):
        print(f"⚠️  找不到 {pdf}，仍會建立講義，請確認路徑。")
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    pdf_value = f'"{pdf}"' if re.search(r"[:#,\[\]{}]|^\s|\s$", pdf) else pdf
    out = (tpl.replace("{{slug}}", slug)
              .replace("{{pdf}}", pdf_value)
              .replace("{{added}}", dt.date.today().isoformat()))
    os.makedirs(NOTES_DIR, exist_ok=True)
    os.makedirs(os.path.join(FIG_DIR, slug), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"✅ 已建立 {rel(path)}，圖片請放在 assets/figures/{slug}/")


# ───────────────────────── check ─────────────────────────

IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def check_note(path: str, metas: dict) -> int:
    stem = os.path.splitext(os.path.basename(path))[0]
    raw_meta, body, full = read_note(path)
    meta = norm_meta(raw_meta)
    errs, warns = [], []

    if not raw_meta:
        errs.append("缺少 frontmatter（檔案開頭的 --- 區塊）")
    for k in REQUIRED_FIELDS:
        v = meta.get(k)
        if v in ("", None, []):
            errs.append(f"frontmatter 缺少 `{k}`")
    if meta.get("slug") and meta["slug"] != stem:
        errs.append(f"slug（{meta['slug']}）與檔名（{stem}）不一致")
    if not SLUG_RE.match(stem):
        errs.append("檔名不符合 slug 格式（小寫英數與連字號）")
    pdf = norm_pdf_path(str(meta.get("pdf", "")))
    if pdf and not os.path.isfile(os.path.join(ROOT, pdf)):
        errs.append(f"pdf 檔案不存在：{pdf}")
    if meta.get("year") and not isinstance(raw_meta.get("year"), int):
        errs.append("year 必須是數字")
    if meta.get("status") and meta["status"] not in ("draft", "done"):
        errs.append("status 只能是 draft 或 done")
    if len(str(meta.get("one_liner", ""))) > 70:
        warns.append(f"one_liner 有 {len(str(meta['one_liner']))} 字，建議精簡到 40 字左右")
    if not 2 <= len(meta.get("tags", [])) <= 5:
        warns.append("tags 建議 2–5 個")

    for sec in REQUIRED_SECTIONS:
        if not re.search(r"^" + re.escape(sec), body, re.M):
            errs.append(f"缺少章節：{sec}")
    for sec in OPTIONAL_SECTIONS:
        if not re.search(r"^" + re.escape(sec), body, re.M):
            warns.append(f"缺少章節：{sec}")

    n_ph = full.count(PLACEHOLDER)
    if n_ph:
        errs.append(f"還有 {n_ph} 個〔填寫…〕沒有完成")
    if "{{" in full:
        errs.append("還有模板變數 {{…}} 沒替換")
    if "<!--" in body:
        warns.append("還有模板的 <!-- 寫作提示 --> 沒刪")

    imgs = IMG_RE.findall(body)
    for src in imgs:
        if re.match(r"^(https?:)?//|^data:", src):
            continue
        p = os.path.normpath(os.path.join(NOTES_DIR, src))
        if not os.path.isfile(p):
            errs.append(f"圖片不存在：{src}")
        elif "/work/" in p.replace(os.sep, "/"):
            errs.append(f"不要引用 work/ 暫存區的圖片：{src}")
    if not any(s.endswith("/arch.png") for s in imgs):
        warns.append("沒有引用架構圖 arch.png")
    if not any(s.endswith("/key-result.png") for s in imgs):
        warns.append("沒有引用關鍵實驗圖 key-result.png")

    n_tbc = full.count("待確認")
    if n_tbc and meta.get("status") == "done":
        warns.append(f"status 是 done，但還有 {n_tbc} 處（待確認）")

    for field, back in (("builds_on", "superseded_by"), ("superseded_by", "builds_on")):
        for ref in meta.get(field, []):
            if SLUG_RE.match(ref) and re.match(r"^\d{4}-", ref):
                if ref not in metas:
                    warns.append(f"{field} 的 `{ref}` 看起來是 slug，但 notes/ 裡沒有這篇")
                elif stem not in metas[ref].get(back, []):
                    warns.append(f"雙向連結缺漏：{ref}.md 的 {back} 沒有 `{stem}`")

    head = f"── {rel(path)}"
    print(head)
    for e in errs:
        print(f"  ❌ {e}")
    for w in warns:
        print(f"  ⚠️  {w}")
    if not errs and not warns:
        print("  ✅ 全部通過")
    elif not errs:
        print("  ✅ 沒有錯誤（請看過警告）")
    return len(errs)


def cmd_check(args):
    notes = all_notes()
    metas = {os.path.splitext(os.path.basename(p))[0]: norm_meta(read_note(p)[0]) for p in notes}
    if args.slugs:
        targets = [os.path.join(NOTES_DIR, f"{s[:-3] if s.endswith('.md') else s}.md") for s in args.slugs]
    else:
        targets = notes
    if not targets:
        print("notes/ 裡還沒有講義。")
        return
    total = 0
    for t in targets:
        if not os.path.isfile(t):
            print(f"── {rel(t)}\n  ❌ 檔案不存在")
            total += 1
            continue
        total += check_note(t, metas)
    sys.exit(1 if total else 0)


# ───────────────────────── index ─────────────────────────

def first_image(body: str, slug: str) -> str:
    for name in ("arch.png", "teaser.png"):
        p = os.path.join(FIG_DIR, slug, name)
        if os.path.isfile(p):
            return rel(p)
    for src in IMG_RE.findall(body):
        if not re.match(r"^(https?:)?//|^data:", src):
            p = os.path.normpath(os.path.join(NOTES_DIR, src))
            if os.path.isfile(p):
                return rel(p)
    return ""


def cmd_index(args):
    papers, slugs = [], set()
    for path in all_notes():
        stem = os.path.splitext(os.path.basename(path))[0]
        raw, body, full = read_note(path)
        m = norm_meta(raw)
        slug = m.get("slug") or stem
        if slug in slugs:
            print(f"⚠️  slug 重複：{slug}")
        slugs.add(slug)
        year = raw.get("year") if isinstance(raw.get("year"), int) else None
        papers.append({
            "slug": slug,
            "title": m.get("title", ""),
            "short": m.get("short", "") or slug,
            "authors": m.get("authors", []),
            "year": year,
            "venue": m.get("venue", ""),
            "arxiv": str(m.get("arxiv", "")),
            "code": m.get("code", ""),
            "project": m.get("project", ""),
            "pdf": norm_pdf_path(str(m.get("pdf", ""))),
            "tags": m.get("tags", []),
            "one_liner": m.get("one_liner", ""),
            "builds_on": m.get("builds_on", []),
            "superseded_by": m.get("superseded_by", []),
            "added": str(m.get("added", "")),
            "status": m.get("status", "draft"),
            "incomplete": PLACEHOLDER in full,
            "note": f"notes/{stem}.md",
            "cover": first_image(body, slug),
            "chars": len(re.sub(r"\s", "", body)),
        })
    papers.sort(key=lambda p: (p["added"], p["year"] or 0), reverse=True)
    tags: dict[str, int] = {}
    for p in papers:
        for t in p["tags"]:
            tags[t] = tags.get(t, 0) + 1
    data = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "tags": dict(sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))),
        "papers": papers,
    }
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已更新 {rel(DATA_FILE)}：{len(papers)} 篇，{len(tags)} 個標籤")
    for p in papers:
        flag = "（未完成）" if p["incomplete"] else ""
        print(f"  - {p['slug']:<28} {p['status']:<5} {p['short']}{flag}")


# ───────────────────────── main ─────────────────────────

def main():
    ap = argparse.ArgumentParser(description="PaperAgent 工具（詳見 AGENT.md）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pending", help="列出還沒有講義的 PDF").set_defaults(func=cmd_pending)

    p = sub.add_parser("text", help="抽出全文到 work/<slug>/fulltext.txt")
    p.add_argument("pdf"); p.add_argument("--slug")
    p.set_defaults(func=cmd_text)

    p = sub.add_parser("render", help="把頁面轉成 PNG 預覽")
    p.add_argument("pdf"); p.add_argument("--slug")
    p.add_argument("--pages", help="例：1-3,5（預設全部）")
    p.add_argument("--dpi", type=int, default=90)
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("figures", help="依 Figure/Table 圖說自動擷取候選圖")
    p.add_argument("pdf"); p.add_argument("--slug")
    p.add_argument("--dpi", type=int, default=200)
    p.set_defaults(func=cmd_figures)

    p = sub.add_parser("crop", help="手動擷取頁面區域")
    p.add_argument("pdf")
    p.add_argument("--page", type=int, required=True, help="頁碼（從 1 開始）")
    p.add_argument("--rect", required=True, help="x0,y0,x1,y1；≤1 視為頁面比例，否則為 PDF point")
    p.add_argument("--out", required=True)
    p.add_argument("--dpi", type=int, default=220)
    p.set_defaults(func=cmd_crop)

    p = sub.add_parser("new", help="從模板建立講義")
    p.add_argument("slug"); p.add_argument("--pdf", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("check", help="檢查講義格式（不指定就檢查全部）")
    p.add_argument("slugs", nargs="*")
    p.set_defaults(func=cmd_check)

    sub.add_parser("index", help="重建 data/papers.json").set_defaults(func=cmd_index)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
