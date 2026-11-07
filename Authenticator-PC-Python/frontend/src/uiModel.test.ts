import { describe, expect, it } from "vitest";

import { nextSort, selectAllRows, toggleRowSelection, virtualRowRange } from "./uiModel";

describe("desktop list interaction state", () => {
  it("keeps creation time newest-first on first selection and toggles thereafter", () => {
    expect(nextSort({ field: "service", direction: "ascending" }, "created")).toEqual({
      field: "created",
      direction: "descending",
    });
    expect(nextSort({ field: "created", direction: "descending" }, "created")).toEqual({
      field: "created",
      direction: "ascending",
    });
  });

  it("adds direct checkbox selections without losing prior rows", () => {
    expect(toggleRowSelection(["one"], "two", true)).toEqual(["one", "two"]);
    expect(toggleRowSelection(["one", "two"], "one", true)).toEqual(["two"]);
    expect(toggleRowSelection(["one", "two"], "three", false)).toEqual(["three"]);
    expect(selectAllRows(["one"], ["one", "two"])).toEqual(["one", "two"]);
    expect(selectAllRows(["one", "two"], ["one", "two"])).toEqual([]);
  });

  it("keeps a large table's DOM window close to the viewport", () => {
    expect(virtualRowRange(800, 0, 348, 64)).toEqual({ start: 0, end: 22 });
    expect(virtualRowRange(800, 64 * 400, 348, 64)).toEqual({ start: 392, end: 414 });
    expect(virtualRowRange(800, 64 * 790, 348, 64)).toEqual({ start: 782, end: 800 });
  });
});
