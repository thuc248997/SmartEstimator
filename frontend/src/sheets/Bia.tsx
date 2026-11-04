import { fmt, Project, Revision, Run, vndWords } from "../api";
import { sumEquipment } from "./TongHopChiPhiXD";

const STATUS: Record<string, string> = { draft: "Bản nháp", review: "Đang thẩm định", approved: "Đã phê duyệt", issued: "Đã phát hành" };

/** Bìa hồ sơ dự toán (G8: sheet "Bìa"). Thông tin lấy từ "Thông tin công trình". In bằng Ctrl+P. */
export default function Bia({ project, revision, run, total, onEdit }: { project: Project; revision: Revision; run: Run | null; total: number | null; onEdit(): void }) {
  return (
    <div className="sheet-pad" style={{ background: "#f3f3f3" }}>
      <div style={{ maxWidth: 820, margin: "0 auto 8px", display: "flex", gap: 8 }}>
        <button className="btn" onClick={onEdit}>✏️ Sửa thông tin công trình</button>
        <button className="btn" onClick={() => window.print()}>🖨️ In bìa (Ctrl+P)</button>
      </div>
      <div className="cover">
        <div className="top">
          {project.investor && <div>Chủ đầu tư: {project.investor}</div>}
          {project.consultant && <div>Đơn vị lập: {project.consultant}</div>}
        </div>
        <h1>HỒ SƠ DỰ TOÁN XÂY DỰNG</h1>
        <div className="sub">{revision.title || `Dự toán lần ${revision.number}`} — {STATUS[revision.status]}</div>
        <dl>
          <dt>Công trình</dt><dd><b>{project.name}</b></dd>
          {project.code && <><dt>Mã công trình</dt><dd>{project.code}</dd></>}
          <dt>Địa điểm xây dựng</dt><dd>{project.location || "—"}</dd>
          <dt>Chủ đầu tư</dt><dd>{project.investor || "—"}</dd>
          <dt>Đơn vị lập dự toán</dt><dd>{project.consultant || "—"}</dd>
          {total == null || !run ? <><dt>Giá trị dự toán</dt><dd>Chưa tính</dd></> : (() => {
            const eq = sumEquipment(revision.equipment ?? []).after;
            return <>
              <dt>Chi phí xây dựng</dt><dd>{fmt.money(total)} đồng <small>(sau thuế, kể cả nhà tạm)</small></dd>
              {eq > 0 && <><dt>Chi phí thiết bị</dt><dd>{fmt.money(eq)} đồng <small>(sau thuế)</small></dd></>}
              <dt>Giá trị dự toán</dt><dd><b>{fmt.money(total + eq)} đồng</b><div className="words">({vndWords(total + eq)})</div></dd>
            </>;
          })()}
        </dl>
        <div className="sign">
          <div>NGƯỜI LẬP<span>{project.preparer}</span></div>
          <div>NGƯỜI KIỂM TRA / CHỦ TRÌ<span>{project.checker}</span></div>
        </div>
      </div>
    </div>
  );
}
