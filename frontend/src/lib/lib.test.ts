import { describe, expect, it } from "vitest";

import { colorDistance, colorScale, PALETTE_DARK, PALETTE_LIGHT, SIMILAR_DISTANCE } from "./colors";
import { hasVassalVariant, parseScope, resolveMetric, scopeQuery } from "./vassals";
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
  const game = (hex: string, light: string | null = null, dark: string | null = null) => ({ game: hex, light, dark });

  it("uses the game colour, and the override of the current theme", () => {
    const colors = { HAB: game("#ffffff", "#000000"), FRA: game("#1e3cb4") };
    expect(colorScale(["HAB", "FRA"], false, colors)("HAB")).toEqual({ color: "#000000", dash: undefined });
    expect(colorScale(["HAB", "FRA"], true, colors)("HAB")).toEqual({ color: "#ffffff", dash: undefined });
    expect(colorScale(["HAB", "FRA"], true, colors)("FRA").color).toBe("#1e3cb4");
  });
  it("dashes the second of equal or similar colours, in sorted tag order", () => {
    const colors = { PAP: game("#ffffff"), HAB: game("#f4f4f4"), KOJ: game("#ffffff"), ENG: game("#c8102e") };
    const c = colorScale(["PAP", "KOJ", "HAB", "ENG"], false, colors);
    expect(c("HAB").dash).toBeUndefined();
    expect(c("KOJ").dash).toBeDefined();
    expect(c("PAP").dash).toBeDefined();
    expect(c("PAP").dash).not.toBe(c("KOJ").dash);
    expect(c("ENG").dash).toBeUndefined();
  });
  it("lets an override remove the clash", () => {
    const colors = { HAB: game("#ffffff", "#000000"), PAP: game("#ffffff") };
    expect(colorScale(["HAB", "PAP"], false, colors)("PAP").dash).toBeUndefined();
    expect(colorScale(["HAB", "PAP"], true, colors)("PAP").dash).toBeDefined();
  });
  it("falls back to the palette without a game colour, stable regardless of input order", () => {
    const tags = ["T00", "T01", "T02"];
    expect(colorScale(tags)("T00")).toEqual({ color: PALETTE_LIGHT[0], dash: undefined });
    expect(colorScale(tags, true)("T01").color).toBe(PALETTE_DARK[1]);
    expect(colorScale([...tags].reverse())("T02")).toEqual(colorScale(tags)("T02"));
  });
  it("measures colour distance", () => {
    expect(colorDistance("#ffffff", "#FFFFFF")).toBe(0);
    expect(colorDistance("#ffffff", "#f4f4f4")).toBeLessThan(SIMILAR_DISTANCE);
    expect(colorDistance("#ff0000", "#0000ff")).toBeGreaterThan(SIMILAR_DISTANCE);
    expect(colorDistance("#ff0000", "red")).toBe(Infinity);
  });
});

describe("vassal scope", () => {
  const vm = { population: { direct: "population__vassals", all: "population__all_vassals" } };
  it("parses the URL param", () => {
    expect(parseScope(null)).toBe("none");
    expect(parseScope("direct")).toBe("direct");
    expect(parseScope("all")).toBe("all");
    expect(parseScope("bogus")).toBe("none");
  });
  it("resolves stored metric names", () => {
    expect(resolveMetric(vm, "population", "none")).toBe("population");
    expect(resolveMetric(vm, "population", "direct")).toBe("population__vassals");
    expect(resolveMetric(vm, "population", "all")).toBe("population__all_vassals");
    expect(resolveMetric(vm, "gold", "all")).toBe("gold");
    expect(resolveMetric(undefined, "population", "all")).toBe("population");
  });
  it("knows which metrics have variants", () => {
    expect(hasVassalVariant(vm, "population")).toBe(true);
    expect(hasVassalVariant(vm, "gold")).toBe(false);
  });
  it("builds link queries", () => {
    expect(scopeQuery("none")).toBe("");
    expect(scopeQuery("all")).toBe("&vassals=all");
    expect(scopeQuery("direct", "?")).toBe("?vassals=direct");
  });
});
