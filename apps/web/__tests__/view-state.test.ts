import { describe, expect, it } from "vitest";
import { parseViewState, serializeViewState } from "@/lib/view-state";

describe("workspace URL state", () => {
  it("normalizes malformed values and preserves committed evidence state", () => {
    const parsed = parseViewState(
      new URLSearchParams(
        "sort=not-real&page=-8&selected=a&selected=b&evidence=fork-2",
      ),
    );
    expect(parsed.sort).toBe("maintained_successor");
    expect(parsed.page).toBe(1);
    expect(parsed.selected).toEqual([]);
    expect(parsed.evidence).toBe("");
  });

  it("serializes stable shareable graph and fork controls", () => {
    const state = parseViewState(new URLSearchParams());
    const query = serializeViewState({
      ...state,
      q: "maintained",
      selected: ["fork-a", "fork-b"],
      evidence: "fork-a",
      graphMode: "cluster",
      lowSignal: true,
      cursor: "opaque-cursor",
    });
    expect(query.get("q")).toBe("maintained");
    expect(query.getAll("selected")).toEqual(["fork-a", "fork-b"]);
    expect(query.get("graphMode")).toBe("cluster");
    expect(query.get("cursor")).toBe("opaque-cursor");
  });
});
