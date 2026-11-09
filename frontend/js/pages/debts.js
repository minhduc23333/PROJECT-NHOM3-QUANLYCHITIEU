import { emptyHTML } from "../ui.js";

export function render(el) {
  el.innerHTML = `<h2 class="mb-3">Công nợ</h2>
    ${emptyHTML("Công nợ sẽ hiện ở đây sau khi hóa đơn được chia tiền.")}`;
}
