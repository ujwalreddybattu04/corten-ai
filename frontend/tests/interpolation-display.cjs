const assert = require("node:assert/strict");
const { test } = require("node:test");
const path = require("node:path");
const display = require("./load-ts")(path.join(__dirname, "../src/lib/interpolationDisplay.ts"));

test("graph ranges stay finite for values near float64 limits, small series and constants", () => {
    for (const values of [[-1e308, 1e308], [Number.MAX_VALUE, Number.MAX_VALUE], [1e-300, 2e-300], [0, 0], [25, 25]]) {
        const scale = display.chartScale(values);
        for (const value of values) {
            assert.ok(Number.isFinite(scale.fraction(value)));
            assert.ok(scale.fraction(value) >= 0 && scale.fraction(value) <= 1);
        }
        for (let index = 0; index < 5; index++) {
            assert.ok(Number.isFinite((scale.lower + index / 4 * (scale.upper - scale.lower)) * scale.magnitude));
        }
    }
});

test("full precision and small positive values remain inspectable without clipping or percent conversion", () => {
    assert.equal(display.displayValue(100.19544143498757, true, "%"), "100.19544143498757%");
    assert.equal(display.displayValue(1e-100, false), "1.00e-100");
    assert.equal(display.displayValue(2500, false), "2,500.00");
    assert.equal(display.displayValue(25, false, "%"), "25.00%");
});

test("positive adoption axes start at zero when padding crosses zero and retain overshoot", () => {
    const values = [1, 98, 100, 100.19544143498757];
    const scale = display.chartScale(values);
    assert.equal(scale.lower * scale.magnitude, 0);
    assert.ok(scale.upper * scale.magnitude > Math.max(...values));
    assert.ok(scale.fraction(values.at(-1)) < 1);
});

test("negative, mixed-sign and flat-zero series remain visible on their own ranges", () => {
    const negative = display.chartScale([-100, -1]);
    assert.equal(negative.upper * negative.magnitude, 0);
    assert.ok(negative.lower * negative.magnitude < -100);
    const mixed = display.chartScale([-1, 1]);
    assert.ok(mixed.lower < 0 && mixed.upper > 0);
    const zero = display.chartScale([0, 0]);
    assert.equal(zero.fraction(0), .5);
});
