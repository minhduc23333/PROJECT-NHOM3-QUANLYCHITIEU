// Trạng thái UI: đang tải / dữ liệu trống / lỗi / thành công, và renderState() nối cả 4 lại.
import { ICONS, esc } from "./dom.js";

/** Đang tải. loadingHTML() hoặc loadingHTML("Đang tải hóa đơn...") */
export const loadingHTML = (text = "Đang tải...") =>
  `<div class="ui-state ui-loading" role="status" aria-live="polite">
     <div class="spinner-border" aria-hidden="true"></div>
     <div class="ui-state-text">${esc(text)}</div>
   </div>`;

/** Khung xương (skeleton) cho bảng/danh sách đang tải: skeletonHTML(4) */
export const skeletonHTML = (rows = 3) =>
  `<div class="ui-skeleton" role="status" aria-label="Đang tải">
     ${Array.from({ length: rows }, () => '<div class="ui-skeleton-row"></div>').join("")}
   </div>`;

/**
 * Dữ liệu trống, có thể kèm nút hành động.
 * emptyHTML("Chưa có nhóm") | emptyHTML("Chưa có nhóm", { actionText: "Tạo nhóm", actionHref: "#/groups" })
 */
export const emptyHTML = (text = "Chưa có dữ liệu", { actionText, actionHref } = {}) =>
  `<div class="ui-state ui-empty">
     <span class="ui-state-icon">${ICONS.empty}</span>
     <div class="ui-state-text">${esc(text)}</div>
     ${actionText && actionHref ? `<a class="btn btn-primary btn-sm mt-2" href="${esc(actionHref)}">${esc(actionText)}</a>` : ""}
   </div>`;

/** Lỗi, mặc định có nút "Thử lại" (gắn bằng thuộc tính data-retry). */
export const errorHTML = (msg = "Có lỗi xảy ra", retry = true) =>
  `<div class="ui-state ui-error" role="alert">
     <span class="ui-state-icon">${ICONS.error}</span>
     <div class="ui-state-text">${esc(msg)}</div>
     ${retry ? '<button type="button" class="btn btn-sm btn-outline-danger mt-2" data-retry>Thử lại</button>' : ""}
   </div>`;

/** Thông báo thành công nằm trong trang (khác với toast nổi ở góc). */
export const successHTML = (msg = "Thành công") =>
  `<div class="ui-state ui-success" role="status">
     <span class="ui-state-icon">${ICONS.success}</span>
     <div class="ui-state-text">${esc(msg)}</div>
   </div>`;

/**
 * Hiện loading -> gọi loader() -> trống / lỗi / dữ liệu.
 * renderState(el, () => get("/groups"), (el, data) => {...}, {
 *   isEmpty: (d) => d.length === 0, emptyText: "Chưa có nhóm",
 *   emptyAction: { actionText: "Tạo nhóm", actionHref: "#/groups" },
 *   loading: "skeleton",   // hoặc chuỗi chữ cho spinner
 * })
 * Lỗi 403/404/422 không hiện nút "Thử lại" vì thử lại cũng ra kết quả như cũ.
 */
export async function renderState(container, loader, renderFn, opts = {}) {
  const { isEmpty = () => false, emptyText, emptyAction, loading } = opts;
  container.innerHTML = loading === "skeleton" ? skeletonHTML() : loadingHTML(loading);
  container.setAttribute("aria-busy", "true");
  try {
    const data = await loader();
    if (isEmpty(data)) container.innerHTML = emptyHTML(emptyText, emptyAction);
    else renderFn(container, data);
  } catch (e) {
    const retry = ![403, 404, 422].includes(e?.status);
    container.innerHTML = errorHTML(e?.message ?? "Có lỗi xảy ra", retry);
    if (retry)
      container.querySelector("[data-retry]").onclick = () =>
        renderState(container, loader, renderFn, opts);
  } finally {
    container.removeAttribute("aria-busy");
  }
}
