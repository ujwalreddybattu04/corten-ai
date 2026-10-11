const fs = require("node:fs");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");
const Module = require("node:module");
const path = require("node:path");
const source = path.join(__dirname, "../src/lib/forecasting.ts");
const compiled = ts.transpileModule(fs.readFileSync(source, "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;
const moduleInstance = new Module(source, module);
moduleInstance._compile(compiled, source);
const f = moduleInstance.exports;
const series = (values) => values.map((value, i) => ({ date: f.addMonths("2024-01", i), value }));
test("chronological holdout selects exact trend without future training data", () => {
  const data = series(Array.from({ length: 24 }, (_, i) => 10 + 2 * i));
  const result = f.compareModels(data);
  assert.equal(result.scores[0].id, "trend");
  assert.equal(result.scores[0].mae, 0);
  assert.equal(result.holdout, 4);
  assert.deepEqual(
    f.predict(
      data.map((r) => r.value),
      2,
      "trend",
    ),
    [58, 60],
  );
});
test("seasonal naive repeats the last complete year and rejects insufficient history", () => {
  assert.deepEqual(
    f.predict(
      Array.from({ length: 12 }, (_, i) => i + 1),
      14,
      "seasonal",
    ),
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2],
  );
  assert.throws(() => f.predict([1, 2], 12, "seasonal"));
  assert.equal(f.compareModels(series(Array(12).fill(0))).scores[0].wape, null);
});
test("CSV sorts monthly observations and rejects gaps, duplicates and negative values", () => {
  const data = series(Array(12).fill(100));
  const csv = (rows) => "date,value\n" + rows.map((r) => `"${r.date}",${r.value}`).join("\n");
  assert.deepEqual(f.parseMonthlyCSV(csv([...data].reverse())), data);
  assert.throws(() => f.parseMonthlyCSV(csv([...data.slice(0, 11), data[0]])), /Duplicate/);
  assert.throws(
    () => f.parseMonthlyCSV(csv([...data.slice(0, 11), { date: "2025-01", value: 100 }])),
    /Missing/,
  );
  assert.throws(
    () => f.parseMonthlyCSV(csv(data.map((r, i) => ({ ...r, value: i === 0 ? -1 : r.value })))),
    /nonnegative/,
  );
});
test("every accepted CSV volume survives project validation and reload", () => {
  const csv = (value) =>
    "date,value\n" +
    series(Array(12).fill(value))
      .map((r) => `${r.date},${r.value}`)
      .join("\n");
  const p = f.createProject();
  p.series = f.parseMonthlyCSV(csv(1e15));
  assert.equal(f.isProject(JSON.parse(JSON.stringify(p))), true);
  assert.throws(() => f.parseMonthlyCSV(csv(1e15 + 1)), /supported maximum/);
  assert.throws(() => f.parseMonthlyCSV(csv(1e16)), /supported maximum/);
});
test("CSV handles BOM, decimal volumes, extra columns, and rejects malformed records", () => {
  const data = series(Array(12).fill(10.25));
  const csv =
    "\uFEFFsource,value,date\r\n" +
    data.map((r) => `internal,${r.value},${r.date}-01`).join("\r\n");
  assert.deepEqual(f.parseMonthlyCSV(csv), data);
  const valid = "date,value\n" + data.map((r) => `${r.date},${r.value}`).join("\n");
  for (const value of ["", "NaN", "Infinity", "-1", "$100", "1e5"]) {
    assert.throws(() => f.parseMonthlyCSV(valid.replace("10.25", value)), /nonnegative/);
  }
  assert.throws(() => f.parseMonthlyCSV(valid.replace("2024-01", '"2024-01')), /Unclosed/);
  assert.throws(() => f.parseMonthlyCSV(valid.replace("2024-01", "2024-01-02")), /monthly dates/);
});
test("zero population, full discontinuation, and capture saturation remain bounded", () => {
  const p = f.createProject();
  p.mode = "patient";
  p.horizon = 3;
  p.patient = {
    existingPatients: 100,
    annualIncidence: 0,
    diagnosis: 100,
    eligibility: 100,
    initiation: 100,
    capture: 100,
    discontinuation: 100,
    rampMonths: 1,
    unitsPerPatient: 1,
  };
  p.scenarios.upsideVolume = 100;
  p.scenarios.eventImpact = 100;
  p.scenarios.eventMonth = 1;
  const result = f.forecastProject(p);
  assert.equal(result.rows.Upside[0].starts, 100);
  assert.equal(result.rows.Base[1].patients, 0);
  p.patient.existingPatients = 0;
  assert.equal(
    f.forecastProject(p).rows.Base.every((r) => r.volume === 0 && r.netSales === 0),
    true,
  );
});
test("shortening a horizon does not silently move an event into the forecast", () => {
  const p = f.createProject(true);
  p.model = "average";
  p.scenarios.eventMonth = 6;
  p.scenarios.eventImpact = -50;
  p.horizon = 3;
  const unaffected = f.forecastProject(p).rows.Base;
  p.scenarios.eventImpact = 0;
  assert.deepEqual(unaffected, f.forecastProject(p).rows.Base);
});
test("patient cohort conservation, carryover and net sales follow supplied assumptions", () => {
  const p = f.createProject();
  p.mode = "patient";
  p.horizon = 2;
  p.price = 10;
  p.g2n = 0;
  p.patient = {
    existingPatients: 100,
    annualIncidence: 0,
    diagnosis: 100,
    eligibility: 100,
    initiation: 10,
    capture: 50,
    discontinuation: 20,
    rampMonths: 1,
    unitsPerPatient: 1,
  };
  const rows = f.forecastProject(p).rows.Base;
  assert.equal(rows[0].patients, 5);
  assert.equal(rows[1].starts, 4.5);
  assert.equal(rows[1].patients, 8.5);
  assert.equal(rows[1].netSales, 85);
  p.g2n = 100;
  assert.equal(f.forecastProject(p).rows.Base[1].netSales, 0);
  p.patient.capture = 0;
  assert.equal(f.forecastProject(p).rows.Base[1].patients, 0);
});
test("market events start in the specified forecast month across scenarios", () => {
  const p = f.createProject(true);
  p.series = series(Array(24).fill(100));
  p.horizon = 3;
  p.scenarios.eventMonth = 2;
  p.scenarios.eventImpact = -20;
  const rows = f.forecastProject(p).rows;
  assert.deepEqual(
    rows.Base.map((r) => r.volume),
    [100, 80, 80],
  );
  assert.ok(Math.abs(rows.Upside[1].volume - 92) < 1e-10);
  assert.ok(Math.abs(rows.Downside[1].volume - 68) < 1e-10);
  assert.equal(f.exportCSV(rows).split("\n").length, 10);
});
test("review import validates snapshot data and blocks unsafe source URLs", () => {
  const p = f.createProject(true);
  assert.equal(f.isProject(p), true);
  p.versions = [{ id: "bad", name: "bad", savedAt: "now", inputs: {}, rows: {} }];
  assert.equal(f.isProject(p), false);
  assert.equal(f.safeURL("javascript:alert(1)"), undefined);
  assert.equal(f.validMonth("0000-01"), false);
  assert.equal(
    f.safeURL("https://chryselys.com/forecasting/"),
    "https://chryselys.com/forecasting/",
  );
});
