import { themeQuartz } from "ag-grid-community";

// Excel-like look: tight rows, visible gridlines, gray headers, green accent.
export const xlTheme = themeQuartz.withParams({
  fontFamily: ['"Segoe UI"', "Calibri", "system-ui", "sans-serif"],
  fontSize: 13,
  headerFontSize: 12,
  headerFontWeight: 600,
  rowHeight: 24,
  headerHeight: 26,
  spacing: 4,
  cellHorizontalPadding: 6,
  accentColor: "#217346",
  foregroundColor: "#1f1f1f",
  backgroundColor: "#ffffff",
  headerBackgroundColor: "#f2f2f2",
  headerTextColor: "#3b3b3b",
  borderColor: "#d4d4d4",
  rowBorder: { color: "#e1e1e1", width: 1, style: "solid" },
  columnBorder: { color: "#e1e1e1", width: 1, style: "solid" },
  headerColumnBorder: { color: "#c8c8c8", width: 1, style: "solid" },
  wrapperBorderRadius: 0,
  borderRadius: 0,
  selectedRowBackgroundColor: "#e9f5ee",
  rowHoverColor: "#f4faf6",
  oddRowBackgroundColor: "#ffffff",
  rangeSelectionBorderColor: "#217346",
  inputFocusBorder: { color: "#217346", width: 2, style: "solid" },
});

export const COL_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
