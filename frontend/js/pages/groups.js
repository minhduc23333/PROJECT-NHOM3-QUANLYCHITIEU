// UI-05: Quản lý nhóm
// - #/groups      : danh sách nhóm của tôi + tạo nhóm
// - #/groups/:id  : thông tin nhóm, danh sách thành viên + vai trò, thêm thành viên theo email (chỉ Trưởng nhóm)
import { get, post } from "../api.js";
import { getUser } from "../auth.js";
import { formatDate } from "../format.js";
import { navigate } from "../router.js";
import {
  clearFieldErrors,
  emptyHTML,
  esc,
  field,
  formValues,
  handleFormError,
  renderState,
  showFieldErrors,
  toast,
  withBusy,
} from "../ui.js";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const roleBadge = (role) =>
  role === "LEADER"
    ? '<span class="badge rounded-pill role-leader">Trưởng nhóm</span>'
    : '<span class="badge rounded-pill role-member">Thành viên</span>';

// "Nguyễn Văn An" -> "NA", "An" -> "A"
function initials(name = "") {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

// Bảng màu pastel cố định: cùng một người / một nhóm luôn ra cùng một màu
const TONES = 6;
function tone(key = "") {
  let h = 0;
  for (const ch of String(key)) h = (h * 31 + ch.codePointAt(0)) >>> 0;
  return h % TONES;
}

const avatar = (name, key = name) =>
  `<span class="avatar tone-${tone(key)}" aria-hidden="true">${esc(initials(name))}</span>`;

/* ================== Danh sách nhóm ================== */

export function render(el) {
  el.innerHTML = `<div class="page-groups">
    <div class="page-head d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
      <div class="d-flex align-items-center gap-3">
        <span class="page-title-ico" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5a6.5 6.5 0 0 1 3.5 5.5"/></svg></span>
        <div>
          <h2 class="page-title mb-0">Nhóm của tôi</h2>
          <div class="text-muted">Các nhóm bạn đang tham gia chia tiền</div>
        </div>
      </div>
      <button class="btn btn-primary" id="btn-new-group" aria-expanded="false" aria-controls="new-group">+ Tạo nhóm</button>
    </div>

    <div class="card mb-4 d-none" id="new-group">
      <div class="card-body">
        <h5 class="card-title mb-3">Tạo nhóm mới</h5>
        <form id="group-form" novalidate>
          ${field({ label: "Tên nhóm", name: "name", required: true, placeholder: "VD: Đi Đà Lạt, Phòng 302", attrs: 'maxlength="100" autocomplete="off"' })}
          <p class="text-muted small mb-3">Bạn sẽ là Trưởng nhóm và có thể thêm thành viên bằng email sau khi tạo.</p>
          <div class="d-flex gap-2">
            <button class="btn btn-primary" type="submit">Tạo nhóm</button>
            <button class="btn btn-outline-secondary" type="button" id="btn-cancel">Hủy</button>
          </div>
        </form>
      </div>
    </div>

    <div id="list"></div>
  </div>`;

  const panel = el.querySelector("#new-group");
  const form = el.querySelector("#group-form");
  const openBtn = el.querySelector("#btn-new-group");
  const list = el.querySelector("#list");

  const togglePanel = (open) => {
    panel.classList.toggle("d-none", !open);
    openBtn.setAttribute("aria-expanded", String(open));
    if (open) form.elements.name.focus();
    else {
      form.reset();
      clearFieldErrors(form);
    }
  };
  openBtn.onclick = () => togglePanel(panel.classList.contains("d-none"));
  el.querySelector("#btn-cancel").onclick = () => togglePanel(false);

  const card = (g) => `
    <div class="col-sm-6 col-xl-4">
      <a class="card group-card tone-${tone(g.id)} h-100 text-decoration-none" href="#/groups/${g.id}">
        <div class="card-body d-flex gap-3 align-items-start">
          ${avatar(g.name, g.id)}
          <div class="flex-grow-1 min-w-0">
            <div class="d-flex justify-content-between align-items-start gap-2 mb-1">
              <h5 class="card-title mb-0 text-body text-truncate">${esc(g.name)}</h5>
              ${roleBadge(g.my_role)}
            </div>
            <div class="text-muted small">${g.member_count ?? 0} thành viên · tạo ngày ${formatDate(g.created_at)}</div>
          </div>
        </div>
      </a>
    </div>`;

  const load = () =>
    renderState(
      list,
      () => get("/groups"),
      (c, groups) => {
        c.innerHTML = `<div class="row g-3">${groups.map(card).join("")}</div>`;
      },
      {
        isEmpty: (d) => d.length === 0,
        emptyText: "Bạn chưa ở nhóm nào. Bấm “+ Tạo nhóm” để bắt đầu.",
      },
    );

  form.onsubmit = async (ev) => {
    ev.preventDefault();
    clearFieldErrors(form);
    const name = form.elements.name.value.trim();
    if (!name) {
      showFieldErrors(form, [{ field: "name", message: "Nhập tên nhóm" }]);
      form.elements.name.focus();
      return;
    }
    try {
      const g = await withBusy(form.querySelector("[type=submit]"), () =>
        post("/groups", { name }),
      );
      toast.success(`Đã tạo nhóm “${g.name}”`);
      navigate(`/groups/${g.id}`); // vào luôn trang nhóm để thêm thành viên
    } catch (e) {
      handleFormError(form, e);
    }
  };

  load();
}

/* ================== Chi tiết nhóm ================== */

export function renderDetail(el, { id }) {
  el.innerHTML = `<div class="page-groups"><a href="#/groups" class="back-link d-inline-block mb-2">‹ Danh sách nhóm</a><div id="detail"></div></div>`;
  const box = el.querySelector("#detail");
  const me = getUser();

  renderState(
    box,
    () => get(`/groups/${encodeURIComponent(id)}`),
    (c, g) => {
      const isLeader = g.my_role === "LEADER";
      c.innerHTML = `
        <div class="group-hero tone-${tone(g.id)} d-flex justify-content-between align-items-center flex-wrap gap-3 mb-4">
          <div class="d-flex align-items-center gap-3 min-w-0">
            ${avatar(g.name, g.id)}
            <div class="min-w-0">
              <h2 class="mb-1 text-truncate">${esc(g.name)}</h2>
              <div class="small">Tạo ngày ${formatDate(g.created_at)} · Vai trò của bạn: ${roleBadge(g.my_role)}</div>
            </div>
          </div>
          <a class="btn btn-outline-primary bg-white" href="#/receipts?group=${g.id}">Xem hóa đơn của nhóm</a>
        </div>

        <div class="row g-4">
          <div class="${isLeader ? "col-lg-7" : "col-12"}">
            <div class="card h-100">
              <div class="card-body">
                <h5 class="card-title">Thành viên <span class="text-muted fw-normal" id="member-count"></span></h5>
                <div id="members"></div>
              </div>
            </div>
          </div>
          ${isLeader ? addMemberCard() : ""}
        </div>
        ${isLeader ? "" : '<p class="leader-note small mt-3 mb-0">Chỉ Trưởng nhóm mới thêm được thành viên.</p>'}`;

      const membersBox = c.querySelector("#members");
      let members = g.members.filter((m) => m.status === "ACTIVE");
      const paint = () => {
        c.querySelector("#member-count").textContent = `(${members.length})`;
        membersBox.innerHTML = members.length
          ? memberList(members, me?.id)
          : emptyHTML("Nhóm chưa có thành viên");
      };
      paint();

      if (isLeader) {
        wireAddMember(c.querySelector("#add-member-form"), g.id, (m) => {
          members = [...members.filter((x) => x.user_id !== m.user_id), m];
          paint();
        });
      }
    },
  );
}

function memberList(members, myId) {
  // Trưởng nhóm lên đầu, sau đó theo tên
  const sorted = [...members].sort(
    (a, b) =>
      (a.role === "LEADER" ? 0 : 1) - (b.role === "LEADER" ? 0 : 1) ||
      a.full_name.localeCompare(b.full_name, "vi"),
  );
  return `<ul class="list-unstyled member-list mb-0">
    ${sorted
      .map(
        (m) => `<li class="d-flex align-items-center gap-3">
          ${avatar(m.full_name, m.email)}
          <div class="flex-grow-1 min-w-0">
            <div class="fw-semibold text-truncate">${esc(m.full_name)}${m.user_id === myId ? ' <span class="text-muted fw-normal">(bạn)</span>' : ""}</div>
            <div class="text-muted small text-truncate">${esc(m.email)}</div>
          </div>
          ${roleBadge(m.role)}
        </li>`,
      )
      .join("")}
  </ul>`;
}

const addMemberCard = () => `
  <div class="col-lg-5">
    <div class="card h-100">
      <div class="card-body">
        <h5 class="card-title">Thêm thành viên</h5>
        <p class="text-muted small">Người được thêm cần đã có tài khoản SmartSplit. Nhập email họ dùng để đăng ký.</p>
        <form id="add-member-form" novalidate>
          ${field({ label: "Email thành viên", name: "email", type: "email", required: true, placeholder: "ban@gmail.com", attrs: 'autocomplete="off" spellcheck="false" autocapitalize="off"' })}
          <button class="btn btn-primary w-100" type="submit">Thêm vào nhóm</button>
        </form>
      </div>
    </div>
  </div>`;

function wireAddMember(form, groupId, onAdded) {
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    clearFieldErrors(form);
    const email = formValues(form).email.trim();
    const bad = (message) => {
      showFieldErrors(form, [{ field: "email", message }]);
      form.elements.email.focus();
    };
    if (!email) return bad("Nhập email thành viên");
    if (!EMAIL_RE.test(email)) return bad("Email chưa đúng định dạng, ví dụ ban@gmail.com");

    try {
      const m = await withBusy(form.querySelector("[type=submit]"), () =>
        post(`/groups/${groupId}/members`, { email }),
      );
      onAdded(m);
      form.reset();
      toast.success(`Đã thêm ${m.full_name} vào nhóm`);
      form.elements.email.focus();
    } catch (e) {
      // 404: chưa có tài khoản, 409: đã ở trong nhóm -> báo ngay dưới ô email
      if (e.status === 404 || e.status === 409) bad(e.message);
      else handleFormError(form, e);
    }
  };
}
