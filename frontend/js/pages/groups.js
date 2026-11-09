import { get, post } from "../api.js";
import { formatDate } from "../format.js";
import {
  dataTable,
  esc,
  field,
  formValues,
  handleFormError,
  renderState,
  toast,
  validateRequired,
  withBusy,
} from "../ui.js";

export function render(el) {
  el.innerHTML = `<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
      <h2 class="mb-0">Nhóm</h2>
    </div>
    <form id="group-form" class="row g-2 align-items-start mb-3" novalidate>
      <div class="col-sm-8 col-md-6">${field({ label: "Tên nhóm mới", name: "name", required: true, placeholder: "VD: Đi Đà Lạt" })}</div>
      <div class="col-sm-4 col-md-3 pt-sm-4 mt-sm-2"><button class="btn btn-primary w-100" type="submit">Tạo nhóm</button></div>
    </form>
    <div id="list"></div>`;

  const list = el.querySelector("#list");
  const cols = [
    {
      key: "name",
      title: "Tên nhóm",
      render: (v, r) => `<a href="#/groups/${r.id}">${esc(v)}</a>`,
    },
    {
      key: "my_role",
      title: "Vai trò",
      render: (v) =>
        v === "LEADER"
          ? '<span class="badge text-bg-primary">Trưởng nhóm</span>'
          : "Thành viên",
    },
    { key: "member_count", title: "Thành viên", align: "end" },
    { key: "created_at", title: "Ngày tạo", render: (v) => formatDate(v) },
  ];
  const load = () =>
    renderState(
      list,
      () => get("/groups"),
      (c, rows) => {
        c.innerHTML = dataTable(cols, rows);
      },
      {
        isEmpty: (d) => d.length === 0,
        emptyText: "Bạn chưa ở nhóm nào. Tạo nhóm đầu tiên ở ô phía trên.",
      },
    );

  const form = el.querySelector("#group-form");
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    if (!validateRequired(form)) return;
    try {
      await withBusy(form.querySelector("button"), () =>
        post("/groups", formValues(form)),
      );
      toast.success("Đã tạo nhóm");
      form.reset();
      load();
    } catch (e) {
      handleFormError(form, e);
    }
  };
  load();
}

export function renderDetail(el, { id }) {
  el.innerHTML = `<a href="#/groups" class="d-inline-block mb-2">‹ Danh sách nhóm</a><div id="detail"></div>`;
  renderState(
    el.querySelector("#detail"),
    () => get(`/groups/${encodeURIComponent(id)}`),
    (box, g) => {
      box.innerHTML = `<h2>${esc(g.name)}</h2>
      <p class="text-muted">${g.member_count} thành viên, tạo ngày ${formatDate(g.created_at)}</p>
      ${dataTable(
        [
          { key: "full_name", title: "Họ tên" },
          { key: "email", title: "Email" },
          {
            key: "role",
            title: "Vai trò",
            render: (v) => (v === "LEADER" ? "Trưởng nhóm" : "Thành viên"),
          },
        ],
        g.members.filter((m) => m.status === "ACTIVE"),
      )}
      <a class="btn btn-outline-primary" href="#/receipts?group=${g.id}">Xem hóa đơn của nhóm</a>`;
    },
  );
}
