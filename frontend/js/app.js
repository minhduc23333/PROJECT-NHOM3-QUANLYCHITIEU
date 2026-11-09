import { get } from "./api.js";
import { esc } from "./ui.js";
import { getUser, isLoggedIn, logout, setUser } from "./auth.js";
import {
  addRoute,
  currentPath,
  currentPathname,
  match,
  navigate,
} from "./router.js";
import * as login from "./pages/login.js";
import * as register from "./pages/register.js";
import * as dashboard from "./pages/dashboard.js";
import * as groups from "./pages/groups.js";
import * as receipts from "./pages/receipts.js";
import * as debts from "./pages/debts.js";
import * as notFound from "./pages/notfound.js";
import * as uiDemo from "./pages/ui-demo.js";

addRoute("/login", login.render, { isPublic: true });
addRoute("/register", register.render, { isPublic: true });
addRoute("/", dashboard.render);
addRoute("/groups", groups.render);
addRoute("/groups/:id", groups.renderDetail);
addRoute("/receipts", receipts.render);
addRoute("/debts", debts.render);
addRoute("/dev/ui", uiDemo.render);

let renderSeq = 0;

async function route() {
  const found = match(currentPath()) ?? {
    render: notFound.render,
    isPublic: false,
    params: {},
  };
  if (!found.isPublic && !isLoggedIn()) {
    // route guard
    if (currentPath() !== "/")
      sessionStorage.setItem("after_login", currentPath()); // quay lại đúng trang sau khi đăng nhập
    return navigate("/login");
  }
  if (found.isPublic && isLoggedIn()) return navigate("/");

  document.body.classList.toggle("public", found.isPublic);
  document.getElementById("user-name").textContent = getUser()?.full_name ?? "";
  const path = currentPathname();
  document.querySelectorAll("#menu a, #mobile-menu a").forEach((a) => {
    const r = a.dataset.route;
    a.classList.toggle("active", r === "/" ? path === "/" : path.startsWith(r));
  });

  const seq = ++renderSeq;
  const view = document.getElementById("view");
  // Chuyển qua lại đăng nhập <-> đăng ký: giữ nguyên khung (hóa đơn, nền) để không chạy lại hiệu ứng
  const keepAuthShell = found.isPublic && view.querySelector(".auth-page");
  if (!keepAuthShell) view.innerHTML = "";
  window.scrollTo(0, 0);
  try {
    await found.render(view, found.params);
  } catch (e) {
    if (seq === renderSeq)
      view.innerHTML = `<div class="alert alert-danger">${esc(e.message ?? "Có lỗi xảy ra")}</div>`;
  }
}

// Mở lại trang khi đã có token: lấy lại thông tin user mới nhất (token hỏng -> api tự logout)
async function boot() {
  if (isLoggedIn()) {
    try {
      setUser(await get("/auth/me"));
    } catch {
      /* 401 đã được xử lý trong api.js */
    }
  }
  route();
}

document.getElementById("btn-logout").onclick = logout;
window.addEventListener("hashchange", route);
boot();
