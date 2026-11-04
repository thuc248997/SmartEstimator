import { Equipment, fmt, Project, Revision, Run, vndWords } from "../api";

/** TH chi phí xây dựng (G8: "TH Chi Phí XD"): từng hạng mục — trước thuế, VAT, sau thuế; tổng bằng số và bằng chữ. */
export default function TongHopChiPhiXD({ project, revision, run }: { project: Project; revision: Revision; run: Run | null }) {
  if (!run?.result) return <div className="sheet-pad">Chưa có kết quả tính. Bấm <strong>Tính lại (F9)</strong>.</div>;
  const s = run.result.summary;
  const order = new Map(revision.items.map((i) => [String(i.id), i.order * 1e6 + i.id]));
  const items = [...(s.items ?? [])].sort((a, b) => (order.get(a.item_id) ?? 0) - (order.get(b.item_id) ?? 0));
  const sum = (k: string) => items.reduce((t, it) => t + Number(it.values[k] ?? 0), 0);
  const eq = sumEquipment(revision.equipment ?? []);
  const lt = Number(s.values.LT_SAU_THUE ?? 0);
  const grand = Number(s.values.GXD) + lt + eq.after;
  return (
    <div className="sheet-pad">
      <p className="doc-title">Bảng tổng hợp chi phí xây dựng</p>
      <p className="doc-sub">Công trình: <strong>{project.name}</strong>{project.location ? ` · Địa điểm: ${project.location}` : ""} · Đơn vị tính: đồng</p>
      <table className="xl">
        <thead><tr><th style={{ width: 50 }}>STT</th><th>HẠNG MỤC</th><th style={{ width: 150 }}>CHI PHÍ TRỰC TIẾP</th><th style={{ width: 150 }}>GIÁN TIẾP + TNCT</th>
          <th style={{ width: 160 }}>TRƯỚC THUẾ</th><th style={{ width: 140 }}>THUẾ GTGT</th><th style={{ width: 160 }}>SAU THUẾ</th></tr></thead>
        <tbody>
          {items.map((it, i) => (
            <tr key={it.item_id}>
              <td style={{ textAlign: "center" }}>{i + 1}</td><td>{it.name} <small style={{ color: "#616161" }}>({it.lines} công tác)</small></td>
              <td className="num">{fmt.money(it.values.T)}</td>
              <td className="num">{fmt.money(Number(it.values.GT) + Number(it.values.TL))}</td>
              <td className="num">{fmt.money(it.values.GXDTT)}</td><td className="num">{fmt.money(it.values.GTGT)}</td>
              <td className="num"><b>{fmt.money(it.values.GXD)}</b></td>
            </tr>
          ))}
          <tr className="b"><td /><td>Cộng các hạng mục</td><td className="num">{fmt.money(sum("T"))}</td><td className="num">{fmt.money(sum("GT") + sum("TL"))}</td>
            <td className="num">{fmt.money(sum("GXDTT"))}</td><td className="num">{fmt.money(sum("GTGT"))}</td><td className="num">{fmt.money(sum("GXD"))}</td></tr>
          <tr className="b"><td>A</td><td>Chi phí xây dựng toàn công trình (Bảng 3.8)</td><td className="num">{fmt.money(s.values.T)}</td>
            <td className="num">{fmt.money(Number(s.values.GT) + Number(s.values.TL))}</td><td className="num">{fmt.money(s.values.GXDTT)}</td>
            <td className="num">{fmt.money(s.values.GTGT)}</td><td className="num">{fmt.money(s.values.GXD)}</td></tr>
          <tr><td>B</td><td>Chi phí nhà tạm để ở và điều hành thi công</td><td /><td /><td className="num">{fmt.money(s.values.LT)}</td>
            <td className="num">{fmt.money(s.values.LT_GTGT)}</td><td className="num">{fmt.money(lt)}</td></tr>
          <tr><td>C</td><td>Chi phí thiết bị (sheet Chi phí thiết bị)</td><td /><td /><td className="num">{fmt.money(eq.before)}</td>
            <td className="num">{fmt.money(eq.vat)}</td><td className="num">{fmt.money(eq.after)}</td></tr>
          <tr className="grand"><td /><td>TỔNG CỘNG (A + B + C)</td><td /><td /><td className="num">{fmt.money(Number(s.values.GXDTT) + Number(s.values.LT) + eq.before)}</td>
            <td className="num">{fmt.money(Number(s.values.GTGT) + Number(s.values.LT_GTGT) + eq.vat)}</td><td className="num">{fmt.money(grand)}</td></tr>
        </tbody>
      </table>
      <p className="words"><b>Bằng chữ:</b> {vndWords(grand)}.</p>
      <p className="doc-sub" style={{ maxWidth: 900 }}>
        Tỷ lệ chi phí chung, TNCT tính trước… chọn theo quy mô cả công trình rồi áp cho từng hạng mục. Do làm tròn từng bước,
        dòng “Cộng các hạng mục” có thể lệch vài đồng so với dòng toàn công trình (A).
      </p>
    </div>
  );
}

export function sumEquipment(list: Equipment[]) {
  return list.reduce((t, e) => ({ before: t.before + Number(e.amount), vat: t.vat + Number(e.vat), after: t.after + Number(e.amount_after_tax) }), { before: 0, vat: 0, after: 0 });
}
