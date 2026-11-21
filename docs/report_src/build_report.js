// Builds docs/MedBook_Final_Report.docx.  Run from the repo root:  node docs/report_src/build_report.js
// Text lives in content.js; this file only turns it into Word formatting.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, ImageRun, Table, TableRow,
  TableCell, WidthType, ShadingType, BorderStyle, PageBreak, TableOfContents, Footer, Header,
  PageNumber, LevelFormat, TabStopType, VerticalAlign, SectionType, NumberFormat,
} = require("docx");
const { imageSize } = (() => {
  // minimal PNG size reader
  return {
    imageSize: (buf) => ({ width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) }),
  };
})();

const ROOT = path.resolve(__dirname, "..", "..");
const C = require("./content.js");

const FONT = "Times New Roman";
const PAGE_W = 11906, PAGE_H = 16838;           // A4
const MARGIN_L = 1800, MARGIN_R = 1440;         // 1.25" binding side, 1" right
const TEXT_W = PAGE_W - MARGIN_L - MARGIN_R;    // 8666 DXA
const ACCENT = "1F4E79";

let figNo = { ch: 0, n: 0 }, tabNo = { ch: 0, n: 0 };
let chapter = 0;
const figList = [], tabList = [], tocBody = [];
const PAGES = fs.existsSync(path.join(__dirname, "pages.json")) ? JSON.parse(fs.readFileSync(path.join(__dirname, "pages.json"), "utf8")) : {};
const pg = (key) => PAGES[key] || "0";

// ---------- inline markup: **bold**, *italic*, [[placeholder]], `code` ----------
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|\[\[[^\]]+\]\]|`[^`]+`|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("[[")) out.push(new TextRun({ text: "[" + t.slice(2, -2) + "]", bold: true, highlight: "yellow", ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: "Consolas", size: (base.size || 24) - 3, ...base, font: "Consolas" }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

const P = (text, opts = {}) => new Paragraph({
  children: runs(text, opts.run || {}),
  alignment: opts.align || AlignmentType.JUSTIFIED,
  spacing: { after: opts.after ?? 120, before: opts.before ?? 0, line: opts.line ?? 336 },
  indent: opts.indent,
  keepNext: opts.keepNext,
  style: opts.style,
});

const border = { style: BorderStyle.SINGLE, size: 4, color: "9A9893" };
const borders = { top: border, bottom: border, left: border, right: border };

function caption(kind, text) {
  let label;
  if (kind === "Figure") { figNo.n++; label = `Figure ${chapter}.${figNo.n}`; figList.push(`${label}: ${text}`); }
  else { tabNo.n++; label = `Table ${chapter}.${tabNo.n}`; tabList.push(`${label}: ${text}`); }
  return new Paragraph({
    children: [new TextRun({ text: label + ": ", bold: true, size: 20 }), ...runs(text, { size: 20 })],
    alignment: AlignmentType.CENTER,
    spacing: { before: kind === "Figure" ? 60 : 200, after: kind === "Figure" ? 240 : 80 },
    keepNext: kind === "Table",
  });
}

function table(t) {
  const n = t.header.length;
  const widths = t.widths
    ? t.widths.map((w) => Math.round((w / t.widths.reduce((a, b) => a + b, 0)) * TEXT_W))
    : Array(n).fill(Math.floor(TEXT_W / n));
  const fix = TEXT_W - widths.reduce((a, b) => a + b, 0); widths[widths.length - 1] += fix;
  const fs = t.size || 19;
  const cell = (txt, i, head, shade) => new TableCell({
    borders, width: { size: widths[i], type: WidthType.DXA },
    shading: head ? { fill: "DCE6F1", type: ShadingType.CLEAR, color: "auto" } : shade ? { fill: "F4F3F0", type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    verticalAlign: VerticalAlign.CENTER,
    children: String(txt).split("\n").map((line) => new Paragraph({
      children: runs(line, { size: fs, bold: head || undefined }),
      alignment: i === 0 || t.left ? AlignmentType.LEFT : AlignmentType.CENTER,
      spacing: { after: 0, line: 252 },
    })),
  });
  const rows = [new TableRow({ tableHeader: true, children: t.header.map((h, i) => cell(h, i, true)) })];
  t.rows.forEach((r, ri) => rows.push(new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false, t.highlightRows && t.highlightRows.includes(ri))) })));
  return [...(t.noCaption ? [] : [caption("Table", t.caption)]), new Table({ width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: widths, rows }),
    ...(t.note ? [P(t.note, { run: { size: 19, italics: true }, after: 200, before: 60, align: AlignmentType.LEFT })] : [new Paragraph({ spacing: { after: 160 }, children: [] })])];
}

function figure(f) {
  const file = path.join(ROOT, f.file);
  const buf = fs.readFileSync(file);
  const { width, height } = imageSize(buf);
  const wIn = f.width || 6.0;
  const wPx = wIn * 96, hPx = (height / width) * wPx;
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 0 },
      children: [new ImageRun({ type: "png", data: buf, transformation: { width: Math.round(wPx), height: Math.round(hPx) },
        altText: { title: f.caption, description: f.caption, name: path.basename(file) } })] }),
    caption("Figure", f.caption),
  ];
}

function bullets(items, ref = "bullets") {
  return items.map((it) => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(it),
    spacing: { after: 60, line: 312 }, alignment: AlignmentType.LEFT }));
}

function placeholder(text) {
  return [new Table({
    width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: [TEXT_W],
    rows: [new TableRow({ children: [new TableCell({
      width: { size: TEXT_W, type: WidthType.DXA },
      borders: { top: { style: BorderStyle.DASHED, size: 8, color: "C98500" }, bottom: { style: BorderStyle.DASHED, size: 8, color: "C98500" },
        left: { style: BorderStyle.DASHED, size: 8, color: "C98500" }, right: { style: BorderStyle.DASHED, size: 8, color: "C98500" } },
      shading: { fill: "FFF6DC", type: ShadingType.CLEAR, color: "auto" },
      margins: { top: 100, bottom: 100, left: 160, right: 160 },
      children: [new Paragraph({ children: [new TextRun({ text: "TO COMPLETE BEFORE SUBMISSION", bold: true, size: 19, color: "8A5A00" })], spacing: { after: 60 } }),
        ...text.map((t) => new Paragraph({ children: runs(t, { size: 21 }), spacing: { after: 60, line: 288 } }))],
    })] })],
  }), new Paragraph({ spacing: { after: 160 }, children: [] })];
}

function render(blocks) {
  const out = [];
  for (const b of blocks) {
    const [kind, a] = b;
    if (kind === "h1") {
      chapter++; figNo = { n: 0 }; tabNo = { n: 0 };
      out.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true,
        children: [new TextRun(`Chapter ${chapter}: ${a}`)] }));
      tocBody.push([1, `Chapter ${chapter}: ${a}`]);
    } else if (kind === "h1u") {   // unnumbered chapter-level heading (references, appendices)
      out.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun(a)] }));
      tocBody.push([1, a]);
    } else if (kind === "h2") { out.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(a)] })); tocBody.push([2, a]); }
    else if (kind === "h3") out.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(a)] }));
    else if (kind === "p") out.push(P(a));
    else if (kind === "ul") out.push(...bullets(a));
    else if (kind === "ol") { C._olCount = (C._olCount || 0) + 1; out.push(...bullets(a, "num" + C._olCount)); }
    else if (kind === "table") out.push(...table(a));
    else if (kind === "fig") out.push(...figure(a));
    else if (kind === "todo") out.push(...placeholder(a));
    else if (kind === "quote") out.push(P(a, { indent: { left: 567, right: 567 }, run: { size: 22 }, align: AlignmentType.LEFT }));
    else if (kind === "code") out.push(...a.split("\n").map((l, i, arr) => new Paragraph({ children: [new TextRun({ text: l || " ", font: "Consolas", size: 18 })],
      spacing: { after: i === arr.length - 1 ? 160 : 0, line: 240 }, indent: { left: 360 }, shading: { fill: "F4F3F0", type: ShadingType.CLEAR, color: "auto" } })));
    else if (kind === "ref") out.push(...a.map((r, i) => new Paragraph({ children: [new TextRun({ text: `[${i + 1}]\t` }), ...runs(r)],
      tabStops: [{ type: TabStopType.LEFT, position: 600 }], indent: { left: 600, hanging: 600 }, spacing: { after: 100, line: 288 }, alignment: AlignmentType.LEFT })));
    else throw new Error("unknown block " + kind);
  }
  return out;
}

// ---------- front matter ----------
function titlePage() {
  const c = (t, size, opts = {}) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: opts.after ?? 120, before: opts.before ?? 0 },
    children: runs(t, { size, bold: opts.bold, color: opts.color }) });
  const team = C.meta.students;
  return [
    c("GOVERNMENT COLLEGE UNIVERSITY, LAHORE", 30, { bold: true, before: 400 }),
    c("Department of Artificial Intelligence", 26, { after: 600 }),
    c("FINAL YEAR PROJECT REPORT", 24, { bold: true, color: ACCENT, after: 500 }),
    c("MedBook", 52, { bold: true, color: ACCENT, after: 160 }),
    c("A Code-Switched Conversational Agent for Clinic Appointment Scheduling and Department Routing", 30, { bold: true, after: 700 }),
    c("Submitted by", 22, { after: 120 }),
    new Table({
      width: { size: 6000, type: WidthType.DXA }, columnWidths: [3600, 2400], alignment: AlignmentType.CENTER,
      rows: team.map(([n, r]) => new TableRow({ children: [n, r].map((t, i) => new TableCell({
        width: { size: [3600, 2400][i], type: WidthType.DXA },
        borders: { top: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, bottom: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, left: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" } },
        children: [new Paragraph({ alignment: i ? AlignmentType.RIGHT : AlignmentType.LEFT, spacing: { after: 60 }, children: [new TextRun({ text: t, size: 24, bold: !i })] })] })) })),
    }),
    c("Session 2023 to 2027", 22, { before: 240, after: 600 }),
    c("Supervised by", 22, { after: 60 }),
    c("**Sir M. Hafeez**", 24, { after: 60 }),
    c("Lecturer, Department of Artificial Intelligence", 22, { after: 700 }),
    c("A report submitted in partial fulfilment of the requirements for the degree of", 22, { after: 60 }),
    c("Bachelor of Science in Artificial Intelligence", 24, { bold: true, after: 400 }),
    c(C.meta.date, 22),
  ];
}

function frontSection(title, blocks) {
  return [new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun(title)] }), ...render(blocks)];
}

function signLines(names) {
  return names.map((n) => new Paragraph({ spacing: { before: 360, after: 0 }, tabStops: [{ type: TabStopType.LEFT, position: 4200 }],
    children: [new TextRun({ text: n }), new TextRun({ text: "\t____________________________" })] }));
}

// ---------- static table of contents (page numbers measured from a rendered PDF, see measure_pages.py) ----------
const FRONT_TOC = ["Declaration", "Certificate of Approval", "Acknowledgements", "Abstract", "List of Figures", "List of Tables", "List of Abbreviations"];
function tocLine(level, text, page, front = false, list = false) {
  return new Paragraph({
    tabStops: [{ type: TabStopType.RIGHT, position: TEXT_W, leader: "dot" }],
    indent: { left: list ? 0 : level === 1 ? 0 : 440, hanging: list ? 0 : 0 },
    spacing: { before: level === 1 && !list ? 120 : 0, after: 40, line: 276 },
    children: [new TextRun({ text, bold: level === 1 && !front && !list, size: list ? 22 : 24 }), new TextRun({ text: "\t" + page, size: list ? 22 : 24 })],
  });
}

// ---------- build ----------
const body = render(C.body);   // render first so the figure/table lists are known
const preface = [
  ...frontSection("Declaration", C.declaration), ...signLines(C.meta.students.map((s) => s[0])),
  ...frontSection("Certificate of Approval", C.certificate),
  ...signLines(["Supervisor: Sir M. Hafeez", "Internal examiner", "External examiner", "Chairperson, Department of AI"]),
  ...frontSection("Acknowledgements", C.acknowledgements),
  ...frontSection("Abstract", C.abstract),
  new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun("Table of Contents")] }),
  ...FRONT_TOC.map((t) => tocLine(1, t, pg("h:" + t), true)),
  ...tocBody.map(([lvl, t]) => tocLine(lvl, t, pg("h:" + t))),
  new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun("List of Figures")] }),
  ...figList.map((f) => tocLine(2, f, pg("c:" + f.split(":")[0]), false, true)),
  new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun("List of Tables")] }),
  ...tabList.map((f) => tocLine(2, f, pg("c:" + f.split(":")[0]), false, true)),
  ...frontSection("List of Abbreviations", [["table", C.abbreviations]]),
];

const numbering = { config: [
  { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
  ...Array.from({ length: 30 }, (_, i) => ({ reference: "num" + (i + 1), levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] })),
] };

const footer = (fmt) => new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
  children: [new TextRun({ children: [PageNumber.CURRENT], size: 20 })] })] });
const header = new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
  border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF", space: 4 } },
  children: [new TextRun({ text: "MedBook: Final Year Project Report", size: 18, color: "7F7F7F", italics: true })] })] });

const page = { size: { width: PAGE_W, height: PAGE_H }, margin: { top: 1440, bottom: 1440, left: MARGIN_L, right: MARGIN_R, header: 708, footer: 708 } };

const doc = new Document({
  creator: "MedBook FYP team", title: "MedBook: Final Year Project Report",
  description: "Final report for the MedBook FYP", features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 24 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 34, bold: true, color: ACCENT }, paragraph: { spacing: { before: 0, after: 360 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 28, bold: true, color: ACCENT }, paragraph: { spacing: { before: 300, after: 140 }, keepNext: true, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 24, bold: true }, paragraph: { spacing: { before: 220, after: 100 }, keepNext: true, outlineLevel: 2 } },
    ],
  },
  numbering,
  sections: [
    { properties: { page }, children: titlePage() },
    { properties: { page: { ...page, pageNumbers: { start: 1, formatType: NumberFormat.LOWER_ROMAN } } }, footers: { default: footer() }, children: preface },
    { properties: { page: { ...page, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } } }, headers: { default: header }, footers: { default: footer() }, children: body },
  ],
});

const out = path.join(ROOT, "docs", "MedBook_Final_Report.docx");
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(out, b); console.log("wrote", out, figList.length, "figures", tabList.length, "tables"); });
