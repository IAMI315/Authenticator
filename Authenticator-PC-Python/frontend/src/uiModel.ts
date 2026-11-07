import type { SortState } from "./types";

export function nextSort(current: SortState, field: string): SortState {
  if (current.field !== field) {
    return { field, direction: field === "created" ? "descending" : "ascending" };
  }
  return {
    field,
    direction: current.direction === "ascending" ? "descending" : "ascending",
  };
}

export function toggleRowSelection(selected: string[], id: string, additive: boolean): string[] {
  if (!additive) return [id];
  return selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id];
}

export function selectAllRows(selected: string[], visibleIds: string[]): string[] {
  return selected.length === visibleIds.length ? [] : visibleIds;
}

export interface VirtualRowRange {
  start: number;
  end: number;
}

/**
 * Return the slice of a fixed-height list which should exist in the DOM.
 * The buffer keeps fast wheel scrolling from showing a blank frame while
 * ensuring that large vaults do not create hundreds of MUI table rows.
 */
export function virtualRowRange(
  count: number,
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
  buffer = 8,
): VirtualRowRange {
  if (count <= 0 || rowHeight <= 0) return { start: 0, end: 0 };
  const first = Math.max(0, Math.floor(Math.max(0, scrollTop) / rowHeight) - buffer);
  const visible = Math.max(1, Math.ceil(Math.max(0, viewportHeight) / rowHeight));
  return {
    start: first,
    end: Math.min(count, first + visible + buffer * 2),
  };
}
