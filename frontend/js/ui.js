// Điểm nhập chung của các component dùng chung (T05E166).
// Mọi trang import từ "../ui.js" như cũ; code thật nằm trong thư mục components/.
//   components/state.js  : đang tải, trống, lỗi, thành công, renderState()
//   components/toast.js  : thông báo nổi (thành công / lỗi)
//   components/form.js   : form field, ô tiền VND, kiểm tra & hiển thị lỗi, withBusy()
//   components/table.js  : bảng dữ liệu
//   components/modal.js  : hộp thoại xác nhận
// Xem trực tiếp tất cả tại #/dev/ui; hướng dẫn dùng: frontend/COMPONENTS.md
export { esc } from "./components/dom.js";
export * from "./components/state.js";
export * from "./components/toast.js";
export * from "./components/form.js";
export * from "./components/table.js";
export * from "./components/modal.js";
