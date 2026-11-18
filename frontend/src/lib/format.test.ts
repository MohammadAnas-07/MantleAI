import { describe, expect, it } from "vitest";

import {
  formatBytes,
  formatCost,
  formatDateTime,
  formatTokens,
  lineRange,
  sumCosts,
} from "./format";

describe("format helpers", () => {
  it("formats costs from decimal strings", () => {
    expect(formatCost("0.000493")).toBe("$0.0005");
    expect(formatCost("1.5")).toBe("$1.50");
    expect(formatCost("0")).toBe("$0");
    expect(formatCost(null)).toBe("n/a");
    expect(formatCost("abc")).toBe("n/a");
    expect(formatCost(2)).toBe("$2.00");
  });

  it("formats token counts", () => {
    expect(formatTokens(999)).toBe("999");
    expect(formatTokens(1000)).toBe("1k");
    expect(formatTokens(1536)).toBe("1.5k");
    expect(formatTokens(1_048_576)).toBe("1.0M");
    expect(formatTokens(2_000_000)).toBe("2M");
  });

  it("formats bytes, ranges and sums", () => {
    expect(formatBytes(10)).toBe("10 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
    expect(lineRange(3, 3)).toBe("3");
    expect(lineRange(3, 9)).toBe("3-9");
    expect(sumCosts(["0.1", null, "0.2", "x"])).toBeCloseTo(0.3);
  });

  it("formats dates and handles missing ones", () => {
    expect(formatDateTime(null)).toBe("never");
    expect(formatDateTime("not a date")).toBe("");
    expect(formatDateTime("2026-11-18T10:00:00Z")).not.toBe("");
  });
});
