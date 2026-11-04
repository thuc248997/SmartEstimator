import { useEffect, useRef, useState } from "react";
import type { CustomCellEditorProps } from "ag-grid-react";

/** Inline text editor. Typing a key replaces content (Excel); F2/double-click edits the existing text,
 *  which can differ from the displayed value (e.g. "=2*(3,5+4,2)" behind a computed quantity). */
export default function TextEditor(props: CustomCellEditorProps & { getInitial?: (data: unknown) => string }) {
  const typed = props.eventKey && props.eventKey.length === 1 ? props.eventKey : null;
  const initial = typed ?? (props.getInitial ? props.getInitial(props.data) : props.value == null ? "" : String(props.value));
  const [text, setText] = useState(initial);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    props.onValueChange(initial);
    const el = ref.current;
    if (el) { el.focus(); if (!typed) el.select(); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <input ref={ref} className="ag-input-field-input ag-text-field-input" style={{ width: "100%", height: "100%", border: 0, padding: "0 6px", outline: "2px solid #217346", outlineOffset: -2, fontFamily: "Consolas, monospace" }}
      value={text} onChange={(e) => { setText(e.target.value); props.onValueChange(e.target.value); }} />
  );
}
