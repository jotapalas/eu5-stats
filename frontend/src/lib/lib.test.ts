import { describe, expect, it } from "vitest";

import { colorScale, PALETTE_DARK, PALETTE_LIGHT } from "./colors";
import {
  countryLabel,
  deltaTone,
  formatDelta,
  formatValue,
  gameDateToYear,
  LOWER_IS_BETTER,
  RANK_METRICS,
} from "./format";

describe("gameDateToYear", () => {
  it("maps Jan 1 to the integer year", () => expect(gameDateToYear("1367.1.1")).toBe(1367));
  it("uses 365-day years without leap days", () => {
    expect(gameDateToYear("1367.1.5")).toBeCloseTo(1367 + 4 / 365);
    expect(gameDateToYear("1368.3.1")).toBeCloseTo(1368 + 59 / 365);
    expect(gameDateToYear("1367.12.31")).toBeCloseTo(1367 + 364 / 365);
  });
  it("is monotonic across saves", () => {
    const dates = ["1337.4.1", "1338.1.1", "1338.12.31", "1339.1.1"];
    const xs = dates.map(gameDateToYear);
    expect([...xs].sort((a, b) => a - b)).toEqual(xs);
  });
});

describe("formatValue", () => {
  it("handles missing values", () => {
    expect(formatValue(null)).toBe("–");
    expect(formatValue(undefined)).toBe("–");
  });
  it("keeps decimals only for small numbers", () => {
    expect(formatValue(0.05)).toBe("0,05");
    expect(formatValue(157)).toBe("157");
  });
  it("compacts big numbers", () => expect(formatValue(1_234_567)).toMatch(/1,2/));
  it("signs deltas", () => {
    expect(formatDelta(3)).toBe("+3");
    expect(formatDelta(-3)).toBe("-3");
  });
});

describe("deltaTone", () => {
  it("treats increases as good by default", () => expect(deltaTone("gold", 10)).toBe("good"));
  it("inverts lower-is-better metrics", () => expect(deltaTone("score_place", 2)).toBe("bad"));
  it("is neutral for zero or missing", () => {
    expect(deltaTone("gold", 0)).toBe("neutral");
    expect(deltaTone("gold", null)).toBe("neutral");
  });
});

describe("RANK_METRICS", () => {
  it("contains only rank positions, not lower-is-better magnitudes", () => {
    expect([...RANK_METRICS].sort()).toEqual(["great_power_rank", "score_place"]);
    for (const m of RANK_METRICS) expect(LOWER_IS_BETTER.has(m)).toBe(true);
  });
});

describe("countryLabel", () => {
  it("adds players", () => expect(countryLabel("ENG", ["Miranda"])).toBe("ENG (Miranda)"));
  it("leaves AI countries bare", () => expect(countryLabel("FRA", [])).toBe("FRA"));
});

describe("colorScale", () => {
  const tags = Array.from({ length: 20 }, (_, i) => `T${String(i).padStart(2, "0")}`);
  it("assigns the palette in sorted order, solid first", () => {
    const c = colorScale(tags);
    expect(c("T00")).toEqual({ color: PALETTE_LIGHT[0], dash: undefined });
    expect(c("T07")).toEqual({ color: PALETTE_LIGHT[7], dash: undefined });
  });
  it("reuses hues dashed past eight countries, then grey", () => {
    const c = colorScale(tags);
    expect(c("T08").color).toBe(PALETTE_LIGHT[0]);
    expect(c("T08").dash).toBeDefined();
    expect(PALETTE_LIGHT).not.toContain(c("T19").color);
  });
  it("is stable regardless of input order and uses dark steps in dark mode", () => {
    expect(colorScale([...tags].reverse())("T03")).toEqual(colorScale(tags)("T03"));
    expect(colorScale(tags, true)("T00").color).toBe(PALETTE_DARK[0]);
  });
});
