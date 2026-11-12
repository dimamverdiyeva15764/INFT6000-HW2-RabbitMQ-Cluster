"""Append a limited-Markdown file to an unpacked .docx using the document's own styles.
Supports: # / ## / ### headings, paragraphs, '- ' bullets, pipe tables, ``` code blocks,
![caption](image.png), `code`, **bold**, and [FILL: ...] (yellow highlight)."""
import os
import re
import sys
from xml.sax.saxutils import escape

unpacked, md_path, base_dir = sys.argv[1], sys.argv[2], sys.argv[3]
TEXT_W = 9360  # 8.5in - 2 x 1in margins, in dxa
BULLET_NUM = "3"

doc_p = os.path.join(unpacked, "word", "document.xml")
doc = open(doc_p, encoding="utf-8").read()
rels_p = os.path.join(unpacked, "word", "_rels", "document.xml.rels")
rels = open(rels_p, encoding="utf-8").read()
ct_p = os.path.join(unpacked, "[Content_Types].xml")
ct = open(ct_p, encoding="utf-8").read()
img_n = [0]


def runs(text, size=None, italic=False):
    extra = (f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>' if size else '') + ('<w:i/>' if italic else '')
    out = []
    for tok in re.split(r"(\[FILL[^\]]*\]|`[^`]+`|\*\*[^*]+\*\*)", text):
        if not tok:
            continue
        if tok.startswith("[FILL"):
            out.append(f'<w:r><w:rPr><w:b/><w:highlight w:val="yellow"/>{extra}</w:rPr><w:t xml:space="preserve">{escape(tok)}</w:t></w:r>')
        elif tok.startswith("`"):
            out.append(f'<w:r><w:rPr><w:rStyle w:val="CodeChar"/>{extra}</w:rPr><w:t xml:space="preserve">{escape(tok[1:-1])}</w:t></w:r>')
        elif tok.startswith("**"):
            out.append(f'<w:r><w:rPr><w:b/>{extra}</w:rPr><w:t xml:space="preserve">{escape(tok[2:-2])}</w:t></w:r>')
        else:
            out.append(f'<w:r>{"<w:rPr>"+extra+"</w:rPr>" if extra else ""}<w:t xml:space="preserve">{escape(tok)}</w:t></w:r>')
    return "".join(out)


def para(text, style=None, num=False, keep_next=False, page_break=False, size=None, italic=False, tight=False):
    ppr = ""
    if style or num or keep_next or page_break or tight:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{style}"/>' if style else "") + ('<w:spacing w:before="20" w:after="20"/>' if tight else "") + \
              ("<w:keepNext/>" if keep_next else "") + ("<w:pageBreakBefore/>" if page_break else "") + \
              (f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{BULLET_NUM}"/></w:numPr>' if num else "") + "</w:pPr>"
    return f"<w:p>{ppr}{runs(text, size, italic)}</w:p>"


def table(rows):
    rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
    ncol = len(rows[0])
    lens = [max(len(re.sub(r"[`*]", "", r[i])) for r in rows) for i in range(ncol)]
    words = [max((len(w) for r in rows for w in re.sub(r"[`*]", "", r[i] if i < len(r) else "").split()), default=1) for i in range(ncol)]
    weights = [max(min(max(l, 12), 60), int(w * 1.7) + 2) for l, w in zip(lens, words)]
    widths = [int(TEXT_W * w / sum(weights)) for w in weights]
    mins = [min(w * 105 + 220, 2600) for w in words]       # a whole word must fit on one line
    for i in range(ncol):
        while widths[i] < mins[i]:
            j = max(range(ncol), key=lambda k: widths[k] - mins[k])
            if widths[j] - mins[j] <= 0:
                break
            step = min(mins[i] - widths[i], widths[j] - mins[j])
            widths[i] += step
            widths[j] -= step
    widths[-1] = TEXT_W - sum(widths[:-1])
    x = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="%d" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
         '<w:tblLook w:val="0420" w:firstRow="1" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:noHBand="0" w:noVBand="1"/>'
         '</w:tblPr><w:tblGrid>' % TEXT_W + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>"]
    for ri, r in enumerate(rows):
        x.append("<w:tr>" + ("<w:trPr><w:tblHeader/></w:trPr>" if ri == 0 else ""))
        for ci in range(ncol):
            shd = '<w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>' if ri == 0 else ""
            cell = r[ci] if ci < len(r) else ""
            x.append(f'<w:tc><w:tcPr><w:tcW w:w="{widths[ci]}" w:type="dxa"/>{shd}</w:tcPr>{para(cell, size=18, tight=True)}</w:tc>')
        x.append("</w:tr>")
    x.append("</w:tbl>")
    return "".join(x) + "<w:p/>"


def image(caption, path, width=None):
    from PIL import Image
    img_n[0] += 1
    n = img_n[0]
    src = os.path.normpath(os.path.join(base_dir, path))
    os.makedirs(os.path.join(unpacked, "word", "media"), exist_ok=True)
    name = f"final_image{n}.png"
    with open(src, "rb") as f, open(os.path.join(unpacked, "word", "media", name), "wb") as g:
        g.write(f.read())
    w, h = Image.open(src).size
    cx = int((width or 6.3) * 914400)
    cy = int(cx * h / w)
    if cy > int(8.0 * 914400):                  # keep it on one page
        cy = int(8.0 * 914400)
        cx = int(cy * w / h)
    rid = f"rIdFinalImg{n}"
    global rels, ct
    rels = rels.replace("</Relationships>",
                        f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/></Relationships>')
    if 'Extension="png"' not in ct:
        ct = ct.replace("<Types ", "<Types ", 1).replace("<Default ", '<Default Extension="png" ContentType="image/png"/><Default ', 1)
    drawing = (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
               f'<wp:docPr id="{900 + n}" name="Figure {n}"/><wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
               '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
               f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{900 + n}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
               f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
               f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
               '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
    pic = f'<w:p><w:pPr><w:keepNext/><w:spacing w:after="60"/><w:jc w:val="center"/></w:pPr>{drawing}</w:p>'
    if not caption:
        return pic
    return pic + (f'<w:p><w:pPr><w:spacing w:after="160"/><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:i/><w:sz w:val="18"/></w:rPr>'
            f'<w:t xml:space="preserve">{escape(caption)}</w:t></w:r></w:p>')


lines = open(md_path, encoding="utf-8").read().splitlines()
out, i, first_h1 = [], 0, True
while i < len(lines):
    ln = lines[i]
    if ln.startswith("```"):
        i += 1
        while i < len(lines) and not lines[i].startswith("```"):
            out.append(f'<w:p><w:pPr><w:pStyle w:val="Code"/></w:pPr><w:r><w:t xml:space="preserve">{escape(lines[i])}</w:t></w:r></w:p>')
            i += 1
        i += 1
        continue
    if ln.startswith("|"):
        rows = []
        while i < len(lines) and lines[i].startswith("|"):
            rows.append(lines[i]); i += 1
        out.append(table(rows))
        continue
    m = re.match(r"!\[(.*)\]\(([^)]*)\)(?:\{width=([0-9.]+)\})?", ln)
    if m:
        out.append(image(m.group(1), m.group(2), float(m.group(3)) if m.group(3) else None))
    elif ln.startswith("### "):
        out.append(para(ln[4:], "Heading2", keep_next=True))
    elif ln.startswith("#### "):
        out.append(para(ln[5:], "Heading4", keep_next=True))
    elif ln.startswith("## "):
        out.append(para(ln[3:], "Heading1", keep_next=True, page_break=ln[3:].startswith("1. ")))
    elif ln.startswith("# "):
        out.append(para(ln[2:], "Title", keep_next=True))
    elif ln.startswith("*") and ln.rstrip().endswith("*") and not ln.startswith("**"):
        out.append(para(ln.strip()[1:-1], italic=True, size=18))
    elif ln.startswith("- "):
        out.append(para(ln[2:], "ListParagraph", num=True))
    elif ln.strip():
        out.append(para(ln))
    i += 1

body = "".join(out)
b0 = doc.index("<w:body>") + len("<w:body>")
k = doc.rfind("<w:sectPr")
doc = doc[:b0] + body + doc[k:]
open(doc_p, "w", encoding="utf-8").write(doc)
open(rels_p, "w", encoding="utf-8").write(rels)
open(ct_p, "w", encoding="utf-8").write(ct)
print("appended", len(out), "blocks,", img_n[0], "image(s)")
