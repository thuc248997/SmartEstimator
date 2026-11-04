# Data dictionary (đợt 1)

| Bảng | Trường chính | Ghi chú |
|---|---|---|
| `catalog_sourcedocument` | issuer, number, title, url, sha256, issued_on, effective_from/to, errata_status, needs_review_errata | Văn bản gốc mọi dữ liệu truy về |
| `catalog_datasetrelease` | kind (NORM/PRICE/RULE), name, version, region, effective_from, status (draft/reviewed/published), source, **is_sample** | Khóa ngoại của định mức/giá gắn release, không chỉ mã |
| `catalog_resource` | code (unique), kind (MATERIAL/LABOR/MACHINE), name, unit, spec, labor_group, labor_grade | Khóa dùng chung định mức ↔ giá |
| `catalog_workitem` | release, code, name, unit, group_code, notes | unique (release, code) |
| `catalog_normcomponent` | work_item, resource, kind, quantity (18,6), is_other_pct, condition | is_other_pct = dòng "VL khác/M khác %" → K^vl/K^mtc |
| `pricebook_priceobservation` | release, resource, region, period, price (18,2), unit, source_kind (OFFICIAL/QUOTE/SURVEY/MANUAL), status (pending/approved/rejected) | unique (release, resource, region, period) |
| `regulations_costrulepack` | code, version, title, source, effective_from, data (JSON), is_approved | Nội dung: `fixtures/rule_pack_tt36_2026.json` |
| `projects_project` | name, region, price_period, construction_type, overhead_basis, labor_overhead_row, is_remote_area, is_linear, is_feasibility_report_only, approved_construction_cost_bn, rule_pack, norm_release, price_release, vat_rate | Tham số chọn bảng tỷ lệ |
| `projects_estimaterevision` | project, number, status (draft/review/approved/issued), snapshot (JSON), content_hash, approved_run/by/at | Khóa khi approved |
| `projects_projectitem` | revision, order, name | Hạng mục |
| `projects_estimateline` | item, order, work_item / custom_code, name, unit, quantity_expr, quantity (18,6), k_nc, k_m, note, version | version = optimistic lock |
| `projects_resourceoverride` | revision, resource, price, reason, created_by | Giá nhập tay, không ghi đè gốc |
| `calculation_calculationrun` | revision, status, engine_version, input_hash, output_hash, snapshot, result (summary + resource_totals), warnings, error | Tái lập: cùng snapshot + engine → cùng output_hash |
| `calculation_calculationline` | run, line, quantity, unit_vl/nc/m, vl, nc, m, direct, breakdown (JSON), warnings | breakdown = cây giải trình |
| `reports_reportartifact` | revision, run, template, template_version, file, sha256, created_by | Excel đã xuất |
| `audit_auditevent` | actor, action, target_type, target_id, diff, reason, at | Append-only |

Tiền và hệ số: `NUMERIC`, không `float`. Múi giờ `Asia/Ho_Chi_Minh`.
