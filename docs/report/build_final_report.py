"""Build HW2_Group4_Final_Report.docx (and .pdf) from HW2_Group4_Final_Report.md.

Uses the team's Word template in drafts/ for styles, md2docx.py for the body,
and adds a centred page number in the footer.
Run from docs/report:  python3 build_final_report.py [path/to/soffice.py]
"""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "drafts", "Dist. Systems - HW 2 Report (with P2).docx")
MD = os.path.join(HERE, "HW2_Group4_Final_Report.md")
OUT = os.path.join(HERE, "HW2_Group4_Final_Report.docx")

FOOTER = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
          '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
          '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>'
          '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
          '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r>'
          '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:t>1</w:t></w:r>'
          '<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>')


def add_footer(unpacked):
    with open(os.path.join(unpacked, "word", "footerPageNo.xml"), "w", encoding="utf-8") as f:
        f.write(FOOTER)
    rels_p = os.path.join(unpacked, "word", "_rels", "document.xml.rels")
    rels = open(rels_p, encoding="utf-8").read()
    rels = rels.replace("</Relationships>",
                        '<Relationship Id="rIdFooterPageNo" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footerPageNo.xml"/></Relationships>')
    open(rels_p, "w", encoding="utf-8").write(rels)
    ct_p = os.path.join(unpacked, "[Content_Types].xml")
    ct = open(ct_p, encoding="utf-8").read()
    ct = ct.replace("</Types>", '<Override PartName="/word/footerPageNo.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>')
    open(ct_p, "w", encoding="utf-8").write(ct)
    doc_p = os.path.join(unpacked, "word", "document.xml")
    doc = open(doc_p, encoding="utf-8").read()
    k = doc.rfind("<w:sectPr")
    j = doc.index(">", k) + 1
    doc = doc[:j] + '<w:footerReference w:type="default" r:id="rIdFooterPageNo"/>' + doc[j:]
    open(doc_p, "w", encoding="utf-8").write(doc)


def main():
    tmp = tempfile.mkdtemp()
    zipfile.ZipFile(TEMPLATE).extractall(tmp)
    subprocess.run([sys.executable, os.path.join(HERE, "md2docx.py"), tmp, MD, HERE], check=True)
    add_footer(tmp)
    if os.path.exists(OUT):
        os.remove(OUT)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(tmp):
            for name in files:
                full = os.path.join(root, name)
                z.write(full, os.path.relpath(full, tmp))
    shutil.rmtree(tmp)
    print("wrote", OUT)
    if len(sys.argv) > 1:
        subprocess.run([sys.executable, sys.argv[1], "--headless", "--convert-to", "pdf", "--outdir", HERE, OUT], check=True)
        print("wrote", OUT[:-5] + ".pdf")


if __name__ == "__main__":
    main()
