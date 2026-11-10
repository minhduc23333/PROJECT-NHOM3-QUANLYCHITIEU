// Trang thử component dùng chung (chỉ cho dev): #/dev/ui
import { formatVND } from "../format.js";
import { confirmDialog, dataTable, renderState, toast } from "../ui.js";

export function render(el) {
  el.innerHTML = `<h2>Thử component</h2>
    <div class="d-flex gap-2 mb-3 flex-wrap">
      <button class="btn btn-outline-secondary" data-mode="data">Dữ liệu</button>
      <button class="btn btn-outline-secondary" data-mode="empty">Trống</button>
      <button class="btn btn-outline-secondary" data-mode="error">Lỗi</button>
      <button class="btn btn-success" id="b-ok">Toast thành công</button>
      <button class="btn btn-danger" id="b-err">Toast lỗi</button>
      <button class="btn btn-warning" id="b-confirm">Hộp xác nhận</button>
    </div>
    <div id="box"></div>`;

  const box = el.querySelector("#box");
  const cols = [
    { key: "name", title: "Món" },
    { key: "amount", title: "Tiền", align: "end", render: (v) => formatVND(v) },
  ];
  const load = (mode) =>
    renderState(
      box,
      async () => {
        await new Promise((r) => setTimeout(r, 400));
        if (mode === "error") throw new Error("Không tải được dữ liệu");
        return mode === "empty"
          ? []
          : [
              { name: "Phở", amount: 90000 },
              { name: "Trà đá", amount: 5000 },
            ];
      },
      (c, rows) => {
        c.innerHTML = dataTable(cols, rows);
      },
      { isEmpty: (d) => d.length === 0, emptyText: "Chưa có hóa đơn" },
    );

  el.querySelectorAll("[data-mode]").forEach((b) => {
    b.onclick = () => load(b.dataset.mode);
  });
  el.querySelector("#b-ok").onclick = () => toast.success("Đã lưu");
  el.querySelector("#b-err").onclick = () => toast.error("Có lỗi xảy ra");
  el.querySelector("#b-confirm").onclick = async () => {
    if (
      await confirmDialog({
        title: "Xóa hóa đơn?",
        message: "Thao tác này không hoàn tác được.",
        okText: "Xóa",
        danger: true,
      })
    ) {
      toast.success("Đã xóa");
    }
  };
  load("data");
}
