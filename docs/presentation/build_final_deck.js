// Builds docs/presentation/HW2_Group4_Final_Presentation.pptx from the project's real figures and results.
// Run from the repository root:  node docs/presentation/build_final_deck.js
const pptxgen = require("pptxgenjs");
const path = require("path");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const ROOT = path.resolve(__dirname, "../..");
const P = (p) => path.join(ROOT, p);
const OUT = path.join(__dirname, "HW2_Group4_Final_Presentation.pptx");

const THEME = {
  name: "Group4 HW2",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B2230", lt1: "FFFFFF", dk2: "3A4454", lt2: "F2F4F7",
    accent1: "E8590C", accent2: "2A78D6", accent3: "1BAF7A", accent4: "6B7280",
    accent5: "B54708", accent6: "0B7A50", hlink: "2A78D6", folHlink: "6B7280",
  },
};
const HEX = { ink: "1B2230", ink2: "3A4454", muted: "6B7280", light: "F2F4F7", line: "D5DAE1",
  orange: "E8590C", blue: "2A78D6", green: "1BAF7A", ph: "FFF4E8", phLine: "E8590C", phText: "9A3B06", white: "FFFFFF" };

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "INFT6000 HW2 - Group 4 - Distributed AMQP Messaging Cluster";
pres.author = "Group 4";
const C = pres.SchemeColor;
// Speaker notes = the word-for-word script in script.json (same text as the Word script).
const SCRIPT = require("./final_script.json").slides;
function notes(slide, n) {
  const x = SCRIPT.find((y) => y.n === n);
  slide.addNotes("About " + x.time + "\n\n" + x.script.join("\n\n"));
}

pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.7, y: 1.6, w: 11.9, h: 1.5, fontSize: 40, bold: true, color: C.background1, valign: "bottom", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.7, y: 3.2, w: 11.9, h: 0.8, fontSize: 20, color: "D5DAE1", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 10.4, h: 0.85, fontSize: 28, bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
});

// ---------- helpers
function presenterTag(slide, who) {
  slide.addText(who, { x: 11.05, y: 0.5, w: 1.7, h: 0.4, fontSize: 11, bold: true, color: C.background1, fill: { color: C.accent2 }, align: "center", valign: "middle", shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.08, isTextBox: true, margin: 0, objectName: "Presenter" });
}
function placeholderBox(slide, x, y, w, h, fileName, what) {
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: HEX.ph }, line: { color: HEX.phLine, width: 1.25, dashType: "dash" }, objectName: "Evidence placeholder " + fileName });
  slide.addText([
    { text: "ADD SCREENSHOT", options: { bold: true, fontSize: 12, color: HEX.phText, breakLine: true } },
    { text: fileName, options: { bold: true, fontSize: 13, color: HEX.phText, breakLine: true } },
    { text: what, options: { fontSize: 11, color: HEX.phText } },
  ], { x: x + 0.2, y: y + 0.15, w: w - 0.4, h: h - 0.3, valign: "middle", align: "left", isTextBox: true, margin: 0, objectName: "Placeholder text " + fileName });
}
function caption(slide, text, x, y, w) {
  slide.addText(text, { x, y, w, h: 0.32, fontSize: 10, italic: true, color: C.accent4, isTextBox: true, margin: 0 });
}
function card(slide, x, y, w, h, fill) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill || HEX.light }, line: { color: fill || HEX.light } });
}
function statBlock(slide, x, y, w, value, label, color) {
  slide.addText(value, { x, y, w, h: 0.65, fontSize: 30, bold: true, color: color || C.text1, isTextBox: true, margin: 0 });
  slide.addText(label, { x, y: y + 0.65, w, h: 0.45, fontSize: 12, color: C.text2, isTextBox: true, margin: 0, valign: "top" });
}
function codeBox(slide, x, y, w, h, lines, title) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.06, fill: { color: "1B2230" }, line: { color: "1B2230" } });
  slide.addText(title, { x: x + 0.25, y: y + 0.12, w: w - 0.5, h: 0.3, fontSize: 11, color: "9AA4B2", isTextBox: true, margin: 0 });
  slide.addText(lines.map((l, i) => ({ text: l, options: { breakLine: i < lines.length - 1, color: l.trim().startsWith("#") ? "8FD19E" : "E6EAF0" } })),
    { x: x + 0.25, y: y + 0.45, w: w - 0.5, h: h - 0.6, fontFace: "Courier New", fontSize: 12, valign: "top", isTextBox: true, margin: 0, paraSpaceAfter: 2 });
}
function bullets(slide, items, x, y, w, h, size) {
  slide.addText(items.map((t, i) => {
    const parts = Array.isArray(t) ? t : [{ text: t }];
    return parts.map((p, j) => ({ text: p.text, options: Object.assign({ bullet: j === 0 ? { indent: 16 } : undefined, breakLine: j === parts.length - 1 && i < items.length - 1 }, p.options || {}) }));
  }).flat(), { x, y, w, h, fontSize: size || 15, color: C.text1, valign: "top", isTextBox: true, margin: 0, paraSpaceAfter: 8 });
}

// =====================================================================
// 1. Title
pres.addSection({ title: "Introduction" });
let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Introduction" });
s.addText("Distributed AMQP Messaging Cluster", { placeholder: "title" });
s.addText("INFT6000 Principles of Distributed Systems  |  HW2  |  Group 4  |  Mr. Islam Elgedawy", { placeholder: "body" });
s.addText("Goal: a RabbitMQ cluster that never loses a confirmed message when a node fails, and test clients that prove it", { x: 0.7, y: 4.0, w: 11.9, h: 0.45, fontSize: 16, italic: true, color: "AEB7C4", isTextBox: true, margin: 0 });
s.addText("RabbitMQ 3.13.7 quorum queues  |  Docker Compose  |  Python 3 + pika clients  |  Prometheus + Grafana (bonus)", { x: 0.7, y: 4.5, w: 11.9, h: 0.4, fontSize: 14, bold: true, color: HEX.orange, isTextBox: true, margin: 0, objectName: "Technology line" });
const members = [
  ["Cluster & infrastructure", "Docker, quorum queues, failure injection"],
  ["Monitoring & performance", "Prometheus, Grafana, alerts, benchmarks"],
  ["Producer", "Publisher confirms, retries, failover"],
  ["Consumer & validation", "Manual acks, idempotency, persistence"],
];
members.forEach((m, i) => {
  const x = 0.7 + i * 3.0;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.25, w: 2.8, h: 1.2, rectRadius: 0.08, fill: { color: "273142" }, line: { color: "273142" }, objectName: "Member card " + (i + 1) });
  s.addText([{ text: m[0], options: { bold: true, fontSize: 15, color: C.background1, breakLine: true } }, { text: m[1], options: { fontSize: 12, color: "C9D1DC" } }],
    { x: x + 0.2, y: 5.33, w: 2.4, h: 1.05, valign: "middle", isTextBox: true, margin: 0 });
});
notes(s, 1);

// =====================================================================
// 2. C4 - all four diagrams
pres.addSection({ title: "Architecture and cluster" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Architecture and cluster" });
s.addText("Architecture: the four C4 diagrams", { placeholder: "title" });
function c4(slide, n, label, img, x, y, w, h) {
  slide.addImage({ path: P(img), x, y, w, h, altText: "C4 " + label + " diagram", objectName: "C4 " + label });
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: y - 0.02, w: 1.85, h: 0.34, rectRadius: 0.06, fill: { color: HEX.ink }, line: { color: HEX.ink }, objectName: "C4 label " + n });
  slide.addText(n + "  " + label, { x, y: y - 0.02, w: 1.85, h: 0.34, fontSize: 11.5, bold: true, color: HEX.white, align: "center", valign: "middle", isTextBox: true, margin: 0 });
}
c4(s, 1, "Context", "docs/c4/context-diagram.png", 0.6, 1.35, 6.6, 2.53);
c4(s, 3, "Component", "docs/c4/component-diagram.png", 0.6, 4.08, 5.8, 2.89);
c4(s, 2, "Container", "docs/c4/container-diagram.png", 7.45, 1.35, 2.55, 4.57);
c4(s, 4, "Deployment", "docs/c4/deployment-diagram.png", 10.25, 1.35, 2.5, 4.72);
s.addText("Full size in the report (sections 1, 4, 5 and 6); Component and Deployment also on backup slides 11-12. Every box, port and volume matches docker-compose.yml and the code.", { x: 7.45, y: 6.2, w: 5.3, h: 0.7, fontSize: 11, italic: true, color: C.accent4, isTextBox: true, margin: 0 });
notes(s, 2);

// =====================================================================
// 3. Cluster, quorum queue, Raft, health check (Docker evidence)
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Architecture and cluster" });
s.addText("Three nodes, one replicated quorum queue", { placeholder: "title" });
const nodes = [["Leader", "writes the log, replicates", HEX.orange], ["Follower", "votes, stores a copy", HEX.blue], ["Follower", "votes, stores a copy", HEX.blue]];
nodes.forEach((n, i) => {
  const x = 0.6 + i * 1.97;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.35, w: 1.8, h: 0.95, rectRadius: 0.08, fill: { color: n[2] }, line: { color: n[2] }, objectName: "Raft role " + (i + 1) });
  s.addText([{ text: n[0], options: { bold: true, fontSize: 15, color: HEX.white, breakLine: true } }, { text: n[1], options: { fontSize: 10.5, color: HEX.white } }], { x, y: 1.35, w: 1.8, h: 0.95, align: "center", valign: "middle", isTextBox: true, margin: 0 });
});
s.addText([
  { text: "Commit rule: ", options: { bold: true } },
  { text: "a message is confirmed to the producer only after 2 of 3 nodes have written it to disk. Three nodes is the smallest cluster that keeps that majority after one failure." },
], { x: 0.6, y: 2.45, w: 5.75, h: 1.2, fontSize: 13.5, color: C.text1, isTextBox: true, margin: 0, valign: "top" });
card(s, 6.75, 1.35, 6.0, 2.4, HEX.light);
bullets(s, [
  [{ text: "hw2.orders: ", options: { bold: true } }, { text: "quorum queue, 3 replicas, delivery limit 10" }],
  [{ text: "pause_minority: ", options: { bold: true } }, { text: "an isolated node stops serving - no split brain" }],
  [{ text: "reject-publish at 1,000,000: ", options: { bold: true } }, { text: "a full queue nacks, never drops" }],
  [{ text: "Volumes rabbitN_data: ", options: { bold: true } }, { text: "the Raft log survives restarts" }],
  [{ text: "Health: ", options: { bold: true } }, { text: "Docker healthcheck per node; up.sh waits for 3 members; mgmt_check.py" }],
], 6.95, 1.5, 5.65, 2.15, 12.5);
s.addText("Docker evidence: python3 scripts/mgmt/mgmt_check.py on our Mac (11 Nov 2026)", { x: 0.6, y: 3.95, w: 12.15, h: 0.32, fontSize: 12, bold: true, color: HEX.blue, isTextBox: true, margin: 0 });
s.addImage({ path: P("docs/evidence/docker/docker-mgmt-check.png"), x: 0.6, y: 4.32, w: 12.15, h: 2.66, altText: "mgmt_check.py output: three nodes running, no alarms or partitions, hw2.orders quorum with leader rabbit3 and 3 of 3 members online, RESULT HEALTHY", objectName: "Docker mgmt_check screenshot" });
notes(s, 3);

// =====================================================================
// 4. Monitoring (bonus) - Docker evidence
pres.addSection({ title: "Monitoring" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Monitoring" });
s.addText("Bonus: Prometheus + Grafana, verified on Docker", { placeholder: "title" });
s.addImage({ path: P("docs/evidence/docker/docker-grafana-message-flow.png"), x: 0.6, y: 1.3, w: 6.5, h: 2.65, altText: "Grafana HW2 dashboard, message flow panels during a message-processing run", objectName: "Grafana message flow" });
s.addImage({ path: P("docs/evidence/docker/docker-grafana-queue.png"), x: 0.6, y: 4.02, w: 6.5, h: 1.36, altText: "Grafana queue depth and consumers panels", objectName: "Grafana queue panels" });
caption(s, "Grafana, HW2 dashboard: message rates and queue depth during a message-processing run", 0.6, 5.42, 6.5);
s.addTable([
  [{ text: "Required by the bonus", options: { bold: true, fill: { color: HEX.light } } }, { text: "Grafana panel  /  Prometheus metric", options: { bold: true, fill: { color: HEX.light } } }],
  ["Queue depth", "Queue depth  /  rabbitmq_detailed_queue_messages"],
  ["Message rates", "Publish / confirm / deliver / ack  /  rabbitmq_global_messages_*"],
  ["Node health", "Nodes up, memory, disk  /  up, rabbitmq_alarms_*"],
], { x: 0.6, y: 5.8, w: 6.5, colW: [1.9, 4.6], fontSize: 10, color: HEX.ink, border: { type: "solid", pt: 0.75, color: HEX.line }, margin: 0.04 });
s.addImage({ path: P("docs/evidence/docker/docker-prometheus-targets.png"), x: 7.4, y: 1.3, w: 5.35, h: 3.04, altText: "Prometheus targets page: prometheus 1/1, rabbitmq 3/3 and rabbitmq-detailed 3/3 up", objectName: "Prometheus targets" });
caption(s, "Prometheus targets: 7 of 7 UP", 7.4, 4.36, 5.35);
s.addImage({ path: P("docs/evidence/docker/docker-check-monitoring-grafana-pass.png"), x: 7.4, y: 4.75, w: 5.35, h: 1.43, altText: "check_monitoring.py: Grafana up, data source and 3 dashboards provisioned, 22 of 22 panel queries return data, MONITORING CHECK PASS", objectName: "check_monitoring result" });
s.addText("check_monitoring.py also reported: 8 alert rules loaded with health ok; node health, queue depth, message and confirm rates present.", { x: 7.4, y: 6.25, w: 5.35, h: 0.7, fontSize: 11, italic: true, color: C.accent4, isTextBox: true, margin: 0 });
notes(s, 4);

// =====================================================================
// 5. Producer
pres.addSection({ title: "Clients" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Clients" });
s.addText("Producer: publisher confirms and failover", { placeholder: "title" });
codeBox(s, 0.6, 1.45, 6.9, 4.65, [
  "channel.confirm_delivery()        # once per channel",
  "channel.basic_publish(",
  "    exchange=\"\", routing_key=\"hw2.orders\", body=body,",
  "    properties=pika.BasicProperties(",
  "        delivery_mode=2, message_id=msg_id),",
  "    mandatory=True)    # returns only after the confirm",
  "except pika.exceptions.NackError:",
  "    retries += 1       # up to --nack-retry-limit (5)",
  "    manager.reconnect(); continue",
  "except (AMQPConnectionError, OSError):",
  "    manager.reconnect(); continue",
  "    # same msg_id and seq are sent again",
  "writer.writerow([msg_id, ..., sent_ts, confirm_ts])",
], "producer/producer.py, _publish_one()  (abridged)");
const flow = [
  ["1", "Each thread: own connection + channel", "pika objects are not thread-safe"],
  ["2", "Wait for the broker's confirm", "the confirm means 2 of 3 disks have it"],
  ["3", "Connection lost? Next node, same msg_id", "backoff 0.5 s doubling to 10 s, with jitter"],
  ["4", "confirmed.csv only after the confirm", "the list of messages that must arrive"],
];
flow.forEach((f, i) => {
  const y = 1.45 + i * 1.18;
  s.addShape(pres.shapes.OVAL, { x: 7.85, y: y + 0.1, w: 0.55, h: 0.55, fill: { color: HEX.orange }, line: { color: HEX.orange } });
  s.addText(f[0], { x: 7.85, y: y + 0.1, w: 0.55, h: 0.55, fontSize: 16, bold: true, color: HEX.white, align: "center", valign: "middle", isTextBox: true, margin: 0 });
  s.addText([{ text: f[1], options: { bold: true, fontSize: 14, color: C.text1, breakLine: true } }, { text: f[2], options: { fontSize: 12, color: C.text2 } }], { x: 8.6, y, w: 4.15, h: 0.95, valign: "middle", isTextBox: true, margin: 0 });
});
s.addText("Shared library common/connection.py: host list 5672/5673/5674 in random order, heartbeat 10 s, wrong password fails at once", { x: 0.6, y: 6.25, w: 12.15, h: 0.5, fontSize: 12.5, color: C.text2, isTextBox: true, margin: 0 });
notes(s, 5);

// =====================================================================
// 6. Consumer
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Clients" });
s.addText("Consumer: manual acks, redelivery and idempotency", { placeholder: "title" });
const cflow = [["Deliver", "prefetch 100"], ["Parse", "JSON message"], ["Seen msg_id?", "de-duplicate"], ["Write + flush", "received.csv"], ["basic_ack", "only now"]];
cflow.forEach((f, i) => {
  const x = 0.6 + i * 2.45;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.5, w: 2.15, h: 1.05, rectRadius: 0.08, fill: { color: i === 4 ? HEX.green : HEX.light }, line: { color: i === 4 ? HEX.green : HEX.light } });
  s.addText([{ text: f[0], options: { bold: true, fontSize: 15, color: i === 4 ? HEX.white : C.text1, breakLine: true } }, { text: f[1], options: { fontSize: 11.5, color: i === 4 ? HEX.white : C.text2 } }], { x, y: 1.5, w: 2.15, h: 1.05, align: "center", valign: "middle", isTextBox: true, margin: 0 });
  if (i < 4) s.addShape(pres.shapes.RIGHT_TRIANGLE, { x: x + 2.2, y: 1.9, w: 0.2, h: 0.25, rotate: 0, fill: { color: HEX.muted }, line: { color: HEX.muted }, flipH: false });
});
s.addText("Any error -> basic_nack(requeue=True); x-delivery-limit 10 stops a poison message", { x: 0.6, y: 2.7, w: 12.1, h: 0.4, fontSize: 13, italic: true, color: C.text2, isTextBox: true, margin: 0 });
card(s, 0.6, 3.35, 6.0, 3.35);
s.addText("Why duplicates can happen", { x: 0.85, y: 3.5, w: 5.6, h: 0.4, fontSize: 17, bold: true, color: C.text1, isTextBox: true, margin: 0 });
bullets(s, [
  "A consumer dies after processing but before its ack arrives -> the broker redelivers (redelivered = true)",
  "A producer loses a confirm in a crash -> it sends the same msg_id again",
  "Delivery is at-least-once; processing once per msg_id makes it idempotent",
], 0.85, 4.0, 5.55, 2.6, 13.5);
card(s, 6.9, 3.35, 5.85, 3.35, "EAF3FC");
s.addText("Validator: zero loss is a test, not a claim", { x: 7.15, y: 3.5, w: 5.4, h: 0.4, fontSize: 17, bold: true, color: C.text1, isTextBox: true, margin: 0 });
s.addText([
  { text: "lost = confirmed.csv - received.csv", options: { fontFace: "Courier New", fontSize: 14, bold: true, color: C.text1, breakLine: true } },
  { text: "Exit code 1 if lost > 0 or nothing was confirmed. Also reports duplicates, order per consumer and latency. Tested with planted errors: finds exactly 2 lost, 3 duplicated, 1 reordered.", options: { fontSize: 13, color: C.text2 } },
], { x: 7.15, y: 4.05, w: 5.4, h: 2.5, valign: "top", isTextBox: true, margin: 0, paraSpaceAfter: 8 });
notes(s, 6);

// =====================================================================
// 7. Integration and integrity (Docker results)
pres.addSection({ title: "Results" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("Integration test on Docker: zero lost messages", { placeholder: "title" });
s.addText("Run by us on a Mac with Docker Desktop: 3 healthy RabbitMQ containers, Prometheus and Grafana running", { x: 0.6, y: 1.3, w: 12.15, h: 0.4, fontSize: 14, bold: true, color: HEX.blue, isTextBox: true, margin: 0 });
function resultCard(x, w, fill, title, cmd, big, rows) {
  card(s, x, 1.85, w, 3.55, fill);
  s.addText(title, { x: x + 0.3, y: 2.0, w: w - 0.6, h: 0.4, fontSize: 17, bold: true, color: C.text1, isTextBox: true, margin: 0 });
  s.addText(cmd, { x: x + 0.3, y: 2.4, w: w - 0.6, h: 0.32, fontFace: "Courier New", fontSize: 11.5, color: C.text2, isTextBox: true, margin: 0 });
  statBlock(s, x + 0.3, 2.85, w - 0.6, big, "confirmed by the broker / received (unique)");
  s.addText(rows.map((r, i) => ({ text: r[0], options: { bold: r[1] === "b", color: r[1] === "g" ? HEX.green : C.text1, breakLine: i < rows.length - 1 } })), { x: x + 0.3, y: 4.05, w: w - 0.6, h: 1.25, fontSize: 14, isTextBox: true, margin: 0, valign: "top", paraSpaceAfter: 3 });
}
resultCard(0.6, 5.95, HEX.light, "Smoke test", "./scripts/p4/smoke.sh", "10,000 / 10,000", [["0 lost   0 duplicates", "b"], ["RESULT: PASS", "g"]]);
resultCard(6.8, 5.95, "EAF3FC", "Leader crash under load", "./scripts/p4/chaos_run.sh leader-crash", "23,680 / 23,680",
  [["0 lost   2 duplicates (detected, not reprocessed)", "b"], ["0 ordering violations per consumer;  p95 2.96 ms,  max 513.79 ms", "n"], ["RESULT: PASS - producer and consumer exited cleanly", "g"]]);
s.addText("NOT Docker - wider coverage on a native RabbitMQ 3.13.7 test cluster, same code and configuration", { x: 0.6, y: 5.6, w: 12.15, h: 0.35, fontSize: 13, bold: true, color: C.text2, isTextBox: true, margin: 0 });
const ext = [["24", "failure runs under load (5 fault types)"], ["467,287", "confirmed messages"], ["0", "lost"], ["50,000 -> 50,000", "messages through a full restart"]];
ext.forEach((e, i) => {
  const x = 0.6 + i * 3.08;
  s.addText([{ text: e[0], options: { bold: true, fontSize: 22, color: i === 2 ? HEX.green : C.text1, breakLine: true } }, { text: e[1], options: { fontSize: 11.5, color: C.text2 } }], { x, y: 6.0, w: 2.95, h: 0.95, valign: "top", isTextBox: true, margin: 0 });
});
notes(s, 7);

// =====================================================================
// 8. Fault tolerance (native test cluster, run 5 screenshots + campaign table)
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("Fault tolerance: automatic leader election, no loss", { placeholder: "title" });
s.addText("Native test cluster - leader crash run 5, all clients on the leader", { x: 0.6, y: 1.3, w: 6.6, h: 0.32, fontSize: 12.5, bold: true, color: C.text2, isTextBox: true, margin: 0 });
s.addImage({ path: P("docs/evidence/native-leadercrash-run5-quorum.png"), x: 0.6, y: 1.68, w: 6.6, h: 1.78, altText: "quorum_status before and after the leader crash: rabbit2 leader in term 25, then rabbit1 leader in term 26", objectName: "Raft before and after" });
caption(s, "results/chaos/leader-crash/run5/quorum_status_before.txt and _after.txt", 0.6, 3.48, 6.6);
s.addImage({ path: P("docs/evidence/native-leadercrash-run5-validation.png"), x: 0.6, y: 3.9, w: 6.6, h: 1.76, altText: "Validation report run 5: 21810 confirmed, 21810 received, 0 lost, 2 duplicates, PASS", objectName: "Validation run 5" });
caption(s, "results/chaos/leader-crash/run5/validation.txt", 0.6, 5.68, 6.6);
card(s, 0.6, 6.05, 6.6, 0.9, "EAF3FC");
s.addText([{ text: "rabbit2 -> rabbit1,  term 25 -> 26,  election 521 ms.  ", options: { bold: true } }, { text: "21,810 / 21,810 received, 0 lost, 2 redelivered duplicates handled." }], { x: 0.8, y: 6.05, w: 6.25, h: 0.9, fontSize: 12.5, color: C.text1, valign: "middle", isTextBox: true, margin: 0 });
s.addText("All failure scenarios, native test cluster (24 runs)", { x: 7.5, y: 1.3, w: 5.25, h: 0.32, fontSize: 12.5, bold: true, color: C.text2, isTextBox: true, margin: 0 });
s.addTable([
  [{ text: "Fault (runs)", options: { bold: true, fill: { color: HEX.light } } }, { text: "Election", options: { bold: true, fill: { color: HEX.light } } }, { text: "Confirms paused", options: { bold: true, fill: { color: HEX.light } } }, { text: "Lost", options: { bold: true, fill: { color: HEX.light } } }],
  ["Follower crash (6)", "none needed", "0.3 s", "0"],
  ["Leader crash (6)", "447-964 ms", "0.2-0.3 s", "0"],
  ["Partition (6)", "majority side", "up to 28 s", "0"],
  ["Rolling restart (3)", "automatic", "-", "0"],
  ["Two nodes down (3)", "after recovery", "31-38 s", "0"],
], { x: 7.5, y: 1.68, w: 5.25, colW: [1.75, 1.3, 1.45, 0.75], fontSize: 12, color: HEX.ink, border: { type: "solid", pt: 0.75, color: HEX.line }, margin: 0.06 });
bullets(s, [
  [{ text: "Crashes: ", options: { bold: true } }, { text: "a new leader in about half a second; all producer and consumer threads reconnected" }],
  [{ text: "Partition: ", options: { bold: true } }, { text: "slowest - clients only notice through missed heartbeats" }],
  [{ text: "Two nodes down: ", options: { bold: true } }, { text: "writes stop until a majority returns (consistency over availability)" }],
], 7.5, 4.15, 5.25, 2.6, 13);
notes(s, 8);

// =====================================================================
// 9. Benchmarks (native charts)
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
s.addText("Performance: 33 benchmark runs, analysed", { placeholder: "title" });
const chartText = { catAxisLabelColor: HEX.ink2, valAxisLabelColor: HEX.ink2, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisLabelFontSize: 11, valAxisLabelFontSize: 11, titleFontFace: "+mn-lt", titleFontSize: 13, titleColor: HEX.ink, valGridLine: { color: "E4E7EC", size: 0.75 }, catGridLine: { style: "none" }, legendFontFace: "+mn-lt", legendFontSize: 11, dataLabelFontFace: "+mn-lt", dataLabelFontSize: 11, dataLabelColor: HEX.ink };
s.addChart(pres.charts.BAR, [{ name: "Publish throughput", labels: ["1", "4", "8", "16"], values: [315, 494, 605, 774] }],
  Object.assign({ x: 0.6, y: 1.4, w: 4.1, h: 3.6, barDir: "col", chartColors: [HEX.orange], showTitle: true, title: "Throughput (msg/s) vs producer threads", showValue: true, dataLabelPosition: "outEnd", showLegend: false, valAxisMinVal: 0, valAxisMaxVal: 900, barGapWidthPct: 60 }, chartText));
s.addChart(pres.charts.LINE, [
  { name: "p50", labels: ["1", "4", "8", "16"], values: [2.3, 5.6, 8.8, 13.3] },
  { name: "p95", labels: ["1", "4", "8", "16"], values: [3.4, 11.3, 19.6, 33.0] },
  { name: "p99", labels: ["1", "4", "8", "16"], values: [5.1, 19.2, 31.9, 74.2] },
], Object.assign({ x: 4.9, y: 1.4, w: 4.1, h: 3.6, chartColors: [HEX.blue, HEX.orange, HEX.green], lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 7, showTitle: true, title: "End-to-end latency (ms) vs producer threads", showLegend: true, legendPos: "b", valAxisMinVal: 0 }, chartText));
card(s, 9.25, 1.4, 3.5, 3.6, "EAF3FC");
s.addText("What it shows", { x: 9.45, y: 1.5, w: 3.1, h: 0.4, fontSize: 16, bold: true, color: C.text1, isTextBox: true, margin: 0 });
bullets(s, [
  "1 thread: ~3.1 ms per message, 2.1 ms of it waiting for the Raft commit + confirm",
  "16 threads: 2.5x the throughput - CPU-bound on 2 vCPUs",
  "64 KB messages: 302 msg/s but 19.8 MB/s",
  "Prefetch 10/100/500: no difference",
], 9.45, 1.95, 3.15, 3.0, 12.5);
caption(s, "Source: benchmarks/results/summary.md, generated by benchmarks/analyze.py from 33 runs in benchmarks/results/raw/ (native test cluster)", 0.6, 5.05, 12.15);
s.addText("Limitations", { x: 0.6, y: 5.45, w: 3, h: 0.35, fontSize: 14, bold: true, color: C.text1, isTextBox: true, margin: 0 });
s.addText("Measured on a 2-vCPU native test cluster (same config, not Docker); absolute numbers will differ on our Macs. Broker's own Prometheus count matched the clients within 0.4 %. Synchronous confirms cap one thread at ~320 msg/s. Partitions are slow to resolve (60 s Erlang net_ticktime).", { x: 0.6, y: 5.8, w: 12.15, h: 1.1, fontSize: 13, color: C.text2, isTextBox: true, margin: 0, valign: "top" });
notes(s, 9);

// =====================================================================
// 10. Conclusion
pres.addSection({ title: "Conclusion" });
s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Conclusion" });
s.addText("What we proved, and what we learned", { x: 0.7, y: 0.55, w: 11.9, h: 0.9, fontSize: 36, bold: true, color: C.background1, isTextBox: true, margin: 0 });
const concl = [
  ["Proved", "No confirmed message lost: 0 of 10,000 and 0 of 23,680 (leader crash) on Docker; 0 of 467,287 in 24 native failure runs. Leaders replaced automatically in about half a second."],
  ["Learned", "Confirms + manual acks give at-least-once, so the consumer must be idempotent. A partition hurts more than a crash. Make the clients fail over in every test, or the test proves nothing."],
  ["Next", "Asynchronous confirms for throughput, a lower net_ticktime for faster partition detection, TLS and real secrets, nodes on separate machines."],
];
concl.forEach((c, i) => {
  const y = 1.75 + i * 1.6;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.7, y, w: 11.9, h: 1.35, rectRadius: 0.08, fill: { color: "273142" }, line: { color: "273142" }, objectName: "Conclusion " + c[0] });
  s.addText(c[0], { x: 0.95, y, w: 1.9, h: 1.35, fontSize: 20, bold: true, color: HEX.orange, valign: "middle", isTextBox: true, margin: 0 });
  s.addText(c[1], { x: 2.9, y, w: 9.5, h: 1.35, fontSize: 15, color: "E6EAF0", valign: "middle", isTextBox: true, margin: 0 });
});
s.addText("Questions?", { x: 0.7, y: 6.6, w: 6, h: 0.5, fontSize: 18, bold: true, color: "AEB7C4", isTextBox: true, margin: 0 });
notes(s, 10);

// =====================================================================
// 11-12. Backup
pres.addSection({ title: "Backup" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Backup" });
s.addText("Backup: C4 Component diagram", { placeholder: "title" });
s.addImage({ path: P("docs/c4/component-diagram.png"), x: 0.6, y: 1.35, w: 11.4, h: 5.68, altText: "C4 Component diagram", objectName: "C4 component" });
s.addNotes("Backup slide - show only if asked. Producer components, the shared ConnectionManager (our channel provider with retry and failover), consumer components, and inside one RabbitMQ node: connection handler, default exchange, quorum queue and Raft replica. Names match the functions in the code.");

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Backup" });
s.addText("Backup: C4 Deployment diagram", { placeholder: "title" });
s.addImage({ path: P("docs/c4/deployment-diagram.png"), x: 4.4, y: 1.3, w: 3.05, h: 5.75, altText: "C4 Deployment diagram", objectName: "C4 deployment" });
s.addText("One Docker host, network amqp-net. Host ports: AMQP 5672-5674, management 15672-15674, metrics 15692-15694, Prometheus 9090, Grafana 3000. Volumes rabbit1_data..rabbit3_data at /var/lib/rabbitmq.", { x: 7.9, y: 2.0, w: 4.8, h: 2.5, fontSize: 15, color: C.text2, isTextBox: true, margin: 0, valign: "top" });
s.addNotes("Backup slide - show if asked about ports, volumes or how the containers are deployed.");

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Backup" });
s.addText("Backup: Prometheus view of a leader crash (native, run 4)", { placeholder: "title" });
s.addImage({ path: P("docs/evidence/fig-leader-crash-run4.png"), x: 0.6, y: 1.3, w: 6.1, h: 5.59, altText: "Prometheus: message rates, nodes up and Raft term during leader crash run 4", objectName: "Prometheus leader crash run 4" });
bullets(s, [
  "Native test cluster, results/chaos/leader-crash/run4, all clients on the leader (rabbit1)",
  "Drawn by scripts/mgmt/plot_prometheus.py from Prometheus query_range over the run window",
  "Top: broker message rates dip and recover. Middle: rabbit1 not scraped while down. Bottom: Raft term steps up = election (461 ms in scenario.log)",
], 7.1, 1.5, 5.6, 4.5, 14);
s.addNotes("Backup slide - show if asked how failover looks in the metrics. Native test cluster, not Docker.");

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Backup" });
s.addText("Backup: where every result comes from", { placeholder: "title" });
s.addTable([
  [{ text: "Result", options: { bold: true, fill: { color: HEX.light } } }, { text: "Environment", options: { bold: true, fill: { color: HEX.light } } }, { text: "Evidence in the repository", options: { bold: true, fill: { color: HEX.light } } }],
  ["Smoke 10,000 / 10,000; leader crash 23,680 / 23,680", "Our Mac, Docker Desktop", "results/ folders on our Mac (terminal output)"],
  ["mgmt_check HEALTHY; 7/7 targets; Grafana; check_monitoring PASS", "Our Mac, Docker Desktop", "docs/evidence/docker/*.png"],
  ["Idle failure runs S1-S3 (55 ms election)", "Docker, 2026-10-23 (P1)", "results/failure_S*.log"],
  ["24 failure runs, 467,287 confirmed, 0 lost (incl. run 5 on slide 8)", "Native RabbitMQ 3.13.7 test cluster, same config", "results/chaos/, docs/evidence/p4-data-integrity.md"],
  ["Persistence 50,000 -> 50,000", "Native test cluster", "results/persistence/"],
  ["33 benchmark runs", "Native test cluster, 2 vCPU", "benchmarks/results/"],
  ["Code exactly as submitted: 12 runs, 0 lost", "Native test cluster", "results/as-submitted/"],
], { x: 0.6, y: 1.45, w: 12.15, colW: [4.4, 3.6, 4.15], fontSize: 13, color: HEX.ink, border: { type: "solid", pt: 0.75, color: HEX.line }, margin: 0.08 });
s.addText("Benchmark self-test output (fake clients) is never reported as a result.", { x: 0.6, y: 6.3, w: 12.1, h: 0.4, fontSize: 12, italic: true, color: C.accent4, isTextBox: true, margin: 0 });
s.addNotes("Backup slide - use it if the professor asks where a number was measured.");

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote " + OUT);
})();
