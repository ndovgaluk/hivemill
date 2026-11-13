import { describe, expect, it } from "vitest";

import { fmtCost, fmtCount, fmtDuration, fmtTokens, UNKNOWN } from "../format";

describe("format", () => {
  it("durations", () => {
    expect(fmtDuration(7380)).toBe("2h 03m");
    expect(fmtDuration(88)).toBe("1m 28s");
    expect(fmtDuration(35)).toBe("35s");
    expect(fmtDuration(0)).toBe("0s");
    expect(fmtDuration(null)).toBe(UNKNOWN);
  });

  it("tokens and money", () => {
    expect(fmtCount(5330357)).toBe("5,330,357");
    expect(fmtTokens(1_200_000)).toBe("1.20M");
    expect(fmtTokens(43042)).toBe("43.0k");
    expect(fmtCost(0.98)).toBe("$0.98");
    for (const f of [fmtCount, fmtTokens, fmtCost]) expect(f(null)).toBe(UNKNOWN);
  });
});
