// Builds docs/presentation/HW2_Group4_Final_Presentation_Script.docx from final_script.json
// Run from the repository root:  node docs/presentation/build_final_script.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  HeadingLevel, AlignmentType, LevelFormat, BorderStyle, Footer, PageNumber,
} = require("docx");

const OUT = path.join(__dirname, "HW2_Group4_Final_Presentation_Script.docx");
const SL = require("./final_script.json").slides;
const FONT = "Calibri", W = 9360, GREY = "6B7280", ORANGE = "B54708", BLUE = "1F5FAD", LIGHT = "F2F4F7", CUE = "EAF3FC";

function runs(text, base = {}) {
  const out = []; const re = /(\*\*[^*]+\*\*|\[[^\]]+\]|`[^`]+`)/g; let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("`")) out.push(new TextRun({ text: t.slice(1, -1), font: "Courier New", size: 19, ...base }));
    else out.push(new TextRun({ text: t, italics: true, color: BLUE, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const P = (t, o = {}) => new Paragraph({ children: runs(t, o.run || {}), spacing: { after: o.after ?? 120, line: o.line ?? 276 } });
const H1 = (t, br = true) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: br });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const B = (t) => new Paragraph({ numbering: { reference: "bul", level: 0 }, children: runs(t), spacing: { after: 60 } });
const gap = () => new Paragraph({ children: [], spacing: { after: 80 } });
const border = { style: BorderStyle.SINGLE, size: 4, color: "C9CED6" };
const borders = { top: border, bottom: border, left: border, right: border };
function cell(content, width, opts = {}) {
  const paras = (Array.isArray(content) ? content : [content]).map((c) => new Paragraph({ children: runs(c, opts.bold ? { bold: true } : {}), spacing: { after: 40 } }));
  return new TableCell({ children: paras, width: { size: width, type: WidthType.DXA }, borders,
    shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill, color: "auto" } : undefined, margins: { top: 60, bottom: 60, left: 100, right: 100 } });
}
function table(rows, widths) {
  return new Table({ width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({ tableHeader: i === 0, children: r.map((c, j) => cell(c, widths[j], i === 0 ? { bold: true, fill: LIGHT } : {})) })) });
}
function kv(rows, k = 2000) {
  return new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: [k, W - k],
    rows: rows.map(([a, b]) => new TableRow({ children: [cell(a, k, { bold: true, fill: LIGHT }), cell(b, W - k)] })) });
}
const callout = (lines, fill = CUE) => new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: [W], rows: [new TableRow({ children: [cell(lines, W, { fill })] })] });

const secs = (t) => { const [m, s] = t.split(" ")[0].split(":").map(Number); return m * 60 + s; };
const fmt = (n) => Math.floor(n / 60) + ":" + String(n % 60).padStart(2, "0");
const words = (s) => s.script.join(" ").replace(/\[[^\]]*\]/g, "").split(/\s+/).filter(Boolean).length;
const per = {}; SL.forEach((s) => { per[s.who] = per[s.who] || { slides: [], t: 0, w: 0 }; per[s.who].slides.push(s.n); per[s.who].t += secs(s.time); per[s.who].w += words(s); });
const total = SL.reduce((a, s) => a + secs(s.time), 0);

const c = [];
c.push(new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun("HW2 Group 4 - Final Presentation Script")] }));
c.push(P("INFT6000 Principles of Distributed Systems  |  HW2: RabbitMQ Distributed AMQP Messaging Cluster  |  Mr. Islam Elgedawy", { run: { color: GREY } }));
c.push(P("Goes with HW2_Group4_Final_Presentation.pptx: 10 main slides, then 4 backup slides (11 Component diagram, 12 Deployment diagram, 13 Prometheus view of a leader crash, 14 where every result comes from). The speaker notes in the PowerPoint contain exactly the spoken text of section 2.", { run: { color: GREY } }));
c.push(gap());
c.push(callout([
  "**How to read this script.** Normal text is what you say. Text in [blue brackets] is what you do: point, click, hand over. Read it aloud three times, then speak from the key words.",
  "**Total: " + fmt(total) + "** (about 8 minutes of speech at a calm 140 words per minute, plus pointing and hand-overs). That leaves about half a minute spare under 10 minutes. Replace [P2 name], [P3 name] and [P4 name] with real names.",
  "**Never mix the two environments.** Docker = what we ran on our Mac (slides 3, 4 and 7). Native test cluster = the 24-run failure campaign, run 5 on slide 8 and the benchmarks on slide 9. Say \"native test cluster\" every time you show those.",
]));

// 1. plan
c.push(H1("1. Plan and timing", false));
c.push(table([["#", "Slide", "Presenter", "Time", "Evidence on the slide"],
  ...SL.map((s) => [String(s.n), s.title, s.who, s.time.split(" ")[0], {
    1: "-", 2: "Four C4 diagrams", 3: "Docker: mgmt_check.py (HEALTHY)", 4: "Docker: Grafana, Prometheus targets, check_monitoring.py (PASS)",
    5: "Real code from producer.py", 6: "Consumer flow, validator rule", 7: "Docker: smoke and leader-crash results", 8: "Native: run 5 Raft before/after + validation; 24-run table",
    9: "Native: benchmark charts from summary.md", 10: "-" }[s.n]])], [450, 2800, 1150, 700, 4260]));
c.push(gap());
c.push(table([["Presenter", "Slides", "Speaking slot", "Spoken words"],
  ...Object.keys(per).sort().map((k) => [k, per[k].slides.join(", "), fmt(per[k].t), String(per[k].w)]),
  ["Total", "1-10", fmt(total), String(Object.values(per).reduce((a, p) => a + p.w, 0))]], [2200, 2200, 2400, 2560]));
c.push(P("The four parts differ by at most 20 words, so everyone speaks for about the same time (2 min 15 s to 2 min 25 s each).", { run: { color: GREY } }));

// 2. script
c.push(H1("2. Word-for-word script"));
SL.forEach((s, i) => {
  if (i > 0) c.push(gap());
  c.push(H2(`Slide ${s.n} - ${s.title}`));
  c.push(kv([["Presenter", s.who], ["Time", s.time + "  (" + words(s) + " words)"]]));
  c.push(H3("Say"));
  s.script.forEach((t) => c.push(P(t, { line: 300 })));
  c.push(kv([["Point at", s.point], ["Key numbers", s.numbers], ["What it proves", s.proves], ["Transition", s.transition]]));
});

// 3. provenance
c.push(H1("3. Where every graph and screenshot comes from"));
c.push(P("Every visual in the deck is either a project file or a screenshot you took. Nothing was redrawn or edited, except cropping two browser screenshots to remove personal tabs, bookmarks and a URL."));
c.push(table([["Slide", "Visual", "Data and how it was produced", "Environment", "What it shows / supported?"],
  ["2", "C4 Context, Container, Component, Deployment", "docs/c4/*.png, rendered from context-diagram.mmd and the three .puml files; boxes, ports and volumes taken from docker-compose.yml and the code", "Design (not a measurement)", "All four required diagrams. Supported by the code."],
  ["3", "mgmt_check.py terminal", "Your screenshot of `python3 scripts/mgmt/mgmt_check.py`, 2026-11-11 19:22 UTC (Erlang 26.2.5.16 = the Docker image)", "Docker (your Mac)", "3 nodes running, no alarms, quorum queue 3/3, HEALTHY. Supported."],
  ["4", "Grafana message flow and queue panels", "Your screenshots of the HW2 dashboard (dashboards/hw2-overview.json), Last 15 minutes, burst at about 23:38 local time; cropped to the panels", "Docker (your Mac)", "Message rates about 500 msg/s, spread over 3 nodes, 0 redelivered; queue depth peak about 2.7 K, 4 consumers. Supported. It is a normal processing run, not a failure."],
  ["4", "Prometheus targets", "Your screenshot of http://localhost:9090/targets; cropped (browser tabs and a utm_source URL removed)", "Docker (your Mac)", "7 of 7 targets UP. Supported."],
  ["4", "check_monitoring.py", "Your screenshot; the slide shows sections 4-5 and the PASS line; the full output is docs/evidence/docker/docker-check-monitoring.png", "Docker (your Mac)", "Grafana, data source, 3 dashboards, 22/22 queries, PASS. Supported."],
  ["7", "Two result cards", "Numbers from your Docker runs of smoke.sh and chaos_run.sh leader-crash (results/ folders on your Mac); no screenshot in the deck", "Docker (your Mac)", "0 lost in both. Supported by your result files, which are not in the submitted ZIP (see section 5)."],
  ["7", "Bottom row", "results/chaos/*/run*/validation.json (24 runs) and results/persistence/; summarised by scripts/p4/summarize_chaos.py", "Native test cluster", "467,287 confirmed, 0 lost; 50,000 kept through a restart. Supported."],
  ["8", "Raft before/after screenshot", "`cat results/chaos/leader-crash/run5/quorum_status_before.txt` and `_after.txt`. These files come from the ZIP: run 5 of the native campaign, 2026-11-11 12:31 UTC, election 521 ms in scenario.log", "Native test cluster (shown in your terminal)", "rabbit2 to rabbit1, term 25 to 26, logs back in sync. Supported, but NOT a Docker run."],
  ["8", "Validation screenshot", "`cat results/chaos/leader-crash/run5/validation.txt` (same native run 5)", "Native test cluster", "21,810 / 21,810, 0 lost, 2 redelivered duplicates. Supported, NOT Docker."],
  ["8", "Scenario table", "Report section 8.3, computed from results/chaos/*/run*/: election time from scenario.log (management API polled every 200 ms), pause = largest gap between confirms in confirmed.csv", "Native test cluster", "Every fault type, 0 lost. Supported."],
  ["9", "Throughput bar chart and latency line chart", "Native PowerPoint charts. Values typed from benchmarks/results/summary.md, which benchmarks/analyze.py generates from benchmarks/results/raw/<scenario>/rep<k>/ (written by benchmarks/run_bench.py). Re-checked: 315 / 494 / 605 / 774 msg/s; p50 2.3 / 5.6 / 8.8 / 13.3, p95 3.4 / 11.3 / 19.6 / 33.0, p99 5.1 / 19.2 / 31.9 / 74.2 ms", "Native test cluster, 2 vCPU", "Throughput and latency against producer threads, 3 repetitions each. Supported."],
  ["9", "\"What it shows\" box", "summary_scenarios.csv: confirm p50 2.12 ms (1 thread); 64 KB = 302 msg/s, 19.80 MB/s; prefetch 10/100/500 = 482/487/467 msg/s; broker vs client difference at most 0.38 %", "Native test cluster", "Supported. \"~3.1 ms per message\" = 1 / 315 msg/s."],
  ["13 (backup)", "Prometheus leader-crash figure", "docs/evidence/fig-leader-crash-run4.png, drawn by scripts/mgmt/plot_prometheus.py --run results/chaos/leader-crash/run4 from Prometheus query_range during that run; election 461 ms in scenario.log", "Native test cluster", "Rate dip, rabbit1 not scraped, Raft term step. Real data, but the Prometheus time series themselves were not archived, so the figure cannot be regenerated now."],
], [700, 1600, 3300, 1500, 2260]));
c.push(gap());
c.push(callout(["**What was removed or corrected.** The earlier slide 7 put a run-5 screenshot next to the Docker 23,680 numbers; those are two different runs on two different environments. Slide 7 now shows only Docker numbers, and run 5 moved to slide 8, labelled native. The Prometheus graph from slide 8 moved to backup slide 13. Nothing on slides 8 and 9 is presented as Docker."], "FFF4E8"));

// 4. Q&A
c.push(H1("4. Likely questions and short answers"));
c.push(table([["Question", "Answer", "Who"],
  ["Why three nodes, not two or four?", "Raft needs a majority. Two nodes cannot survive a failure; four still survive only one. Three is the smallest useful size.", "Person 1"],
  ["What happens when the leader crashes?", "The followers miss heartbeats, one starts an election, the other votes for it, and it leads in a new term. Clients reconnect to another node. On slide 8: rabbit2 to rabbit1, term 25 to 26, 521 ms.", "Person 3"],
  ["Is slide 8 from Docker?", "No. It is run 5 of our native test-cluster campaign, with the same code and configuration. Our Docker leader crash is on slide 7: 23,680 messages, 0 lost.", "Person 3"],
  ["Your monitoring check says Raft term 6, slide 8 says 26. Why?", "They are different clusters: term 6 is our Docker queue, term 25 to 26 is the native test cluster. The term counts elections of one queue on one cluster.", "Person 2"],
  ["How do you know monitoring really works?", "check_monitoring.py: 7/7 targets, 8 rules healthy, Grafana data source and 3 dashboards, and all 22 dashboard queries return data through Grafana.", "Person 2"],
  ["Did an alert fire?", "On the native cluster, yes: NodeDown for the killed node every time, RaftLeaderElection after elections, QuorumLost only with two nodes down. On Docker we showed the rules loaded and healthy, not firing.", "Person 2"],
  ["Why are there duplicates?", "When an ack or confirm is lost in a crash, the message is sent again: at-least-once delivery. We remember processed IDs, so duplicates are not processed twice.", "Person 4"],
  ["How did you prove zero loss?", "Every confirmed ID goes to confirmed.csv, every received ID to received.csv before the ack. The validator subtracts them; anything left fails the run.", "Person 4"],
  ["Is the system CP or AP?", "CP. With two nodes down, writes stop (31-38 s in our tests) and nothing is lost.", "Person 1"],
  ["Why only about 315 msg/s per thread?", "Each thread waits about 2 ms for every confirm. Asynchronous confirms would be faster.", "Person 2"],
  ["Why were the benchmarks not on Docker?", "They ran on the native test cluster in our final review. Absolute numbers on a Mac will differ; the slide says so.", "Person 2"],
  ["Do you guarantee order?", "Per consumer, yes, and we measured 0 violations. With four competing consumers there is no global order.", "Person 4"],
  ["What if the consumer restarts?", "The seen-ID set is in memory, so a redelivered message could be processed again. In production we would store processed IDs in a database.", "Person 4"],
], [2600, 5860, 900]));

// 5. remaining issues
c.push(H1("5. Remaining issues and final checklist"));
[
  "**Names.** The title-slide cards show roles only. If you want names on the slide, type them under each role; otherwise introduce yourselves orally. The report title page and Appendix B still contain [FILL] markers for names, IDs and the repository URL.",
  "**Docker result files.** The smoke-test and 23,680 leader-crash files are on your Mac, not in the ZIP. Copy them into the repository (for example results/docker/smoke and results/docker/leader-crash), so the report's section 8.6 points to files the professor can open.",
  "**Your local results/ folder.** chaos_run.sh writes to results/chaos/<scenario>/run<k>. If your Docker leader crash used run 1-6, it replaced a native run in your local copy. Submit the ZIP's results/chaos folder (native), not your local one, or the report's 24-run table will no longer match.",
  "**No Docker screenshot of the 23,680 run.** If you still have it, `grep -l 23680 results/chaos/leader-crash/*/validation.txt` finds the file; a screenshot of it would make slide 7 even stronger. Not required.",
  "**Grafana screenshot shows a normal run, not a failure.** That is fine for the bonus; do not describe it as a leader crash.",
  "**Rehearse twice with a timer.** Target 9:30. If you run long, shorten slide 4 (the last sentence) and slide 9 (the box).",
].forEach((t) => c.push(B(t)));

const doc = new Document({
  creator: "Group 4", title: "HW2 Group 4 - Final Presentation Script",
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", next: "Normal", run: { font: FONT, size: 44, bold: true, color: "1B2230" }, paragraph: { spacing: { before: 0, after: 120 } } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 32, bold: true, color: "1B2230" }, paragraph: { spacing: { before: 240, after: 160 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 26, bold: true, color: ORANGE }, paragraph: { spacing: { before: 240, after: 100 }, keepNext: true, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 22, bold: true, color: "1B2230" }, paragraph: { spacing: { before: 160, after: 80 }, keepNext: true, outlineLevel: 2 } },
    ],
  },
  numbering: { config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "HW2 Group 4 - Final Presentation Script   ", color: GREY, size: 18 }), new TextRun({ children: [PageNumber.CURRENT], color: GREY, size: 18 })] })] }) },
    children: c,
  }],
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log("wrote " + OUT); });
