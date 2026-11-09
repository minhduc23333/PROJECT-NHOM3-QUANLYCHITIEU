import { get } from "../api.js";
import { formatDate, formatVND } from "../format.js";
import { dataTable, emptyHTML, esc, renderState, selectField } from "../ui.js";

const STATUS = {
  DRAFT: '<span class="badge text-bg-secondary">Nháp</span>',
  VERIFIED: '<span class="badge text-bg-primary">Đã xác nhận</span>',
  SETTLED: '<span class="badge text-bg-success">Đã chốt</span>',
};

export function render(el, params) {
  el.innerHTML = `<h2 class="mb-3">Hóa đơn</h2><div id="picker"></div><div id="list"></div>`;
  const list = el.querySelector("#list");

  const cols = [
    {
      key: "receipt_date",
      title: "Ngày",
      render: (v, r) => formatDate(v ?? r.created_at),
    },
    { key: "merchant_name", title: "Cửa hàng" },
    {
      key: "total_amount",
      title: "Tổng tiền",
      align: "end",
      render: (v) => formatVND(v),
    },
    { key: "status", title: "Trạng thái", render: (v) => STATUS[v] ?? esc(v) },
  ];
  const loadReceipts = (groupId) =>
    renderState(
      list,
      () => get(`/groups/${groupId}/receipts`),
      (c, rows) => {
        c.innerHTML = dataTable(cols, rows);
      },
      {
        isEmpty: (d) => d.length === 0,
        emptyText: "Nhóm này chưa có hóa đơn",
      },
    );

  renderState(
    el.querySelector("#picker"),
    () => get("/groups"),
    (box, groups) => {
      if (!groups.length) {
        box.innerHTML = emptyHTML("Bạn cần tham gia hoặc tạo một nhóm trước");
        return;
      }
      const selected = params.group ?? groups[0].id;
      box.innerHTML = `<div style="max-width:360px">${selectField({
        label: "Nhóm",
        name: "group",
        value: selected,
        options: groups.map((g) => ({ value: g.id, text: g.name })),
      })}</div>`;
      box.querySelector("select").onchange = (e) =>
        loadReceipts(e.target.value);
      loadReceipts(selected);
    },
  );
}
