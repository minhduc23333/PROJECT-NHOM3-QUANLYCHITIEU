// Test cho component dùng chung (T05E166). Chạy: node --test frontend/tests/
// Chỉ test phần tạo HTML và định dạng, không cần trình duyệt.
import assert from "node:assert/strict";
import { test } from "node:test";

import { formatDate, formatNumber, formatVND, formatVNDShort, parseVND } from "../js/format.js";
import { dataTable, emptyHTML, errorHTML, esc, field, loadingHTML, moneyField, selectField, successHTML } from "../js/ui.js";

const plain = (s) => s.replace(/\u00a0|\u202f/g, " "); // Intl dùng khoảng trắng không ngắt

test("formatVND: số, chuỗi số, giá trị trống", () => {
  assert.equal(plain(formatVND(90000)), "90.000 ₫");
  assert.equal(plain(formatVND("1250000.00")), "1.250.000 ₫");
  assert.equal(plain(formatVND(0)), "0 ₫");
  assert.equal(formatVND(null), "—");
  assert.equal(formatVND(""), "—");
  assert.equal(formatVND("abc"), "—");
});

test("formatVNDShort, formatNumber, parseVND", () => {
  assert.equal(formatVNDShort(1500000), "1,5 tr");
  assert.equal(formatVNDShort(85000), "85k");
  assert.equal(formatNumber(1234567), "1.234.567");
  assert.equal(parseVND("1.234.567 ₫"), 1234567);
  assert.equal(parseVND(""), 0);
});

test("formatDate theo kiểu Việt Nam", () => {
  assert.equal(formatDate("2026-11-13"), "13/11/2026");
  assert.equal(formatDate(null), "—");
});

test("esc chặn chèn HTML", () => {
  assert.equal(esc('<img src=x onerror="a">'), "&lt;img src=x onerror=&quot;a&quot;&gt;");
});

test("trạng thái: loading, trống (có nút), lỗi (có/không Thử lại), thành công", () => {
  assert.match(loadingHTML(), /spinner-border/);
  assert.match(loadingHTML(), /role="status"/);
  const empty = emptyHTML("Chưa có nhóm", { actionText: "Tạo nhóm", actionHref: "#/groups" });
  assert.match(empty, /Chưa có nhóm/);
  assert.match(empty, /href="#\/groups"/);
  assert.match(errorHTML("Mất mạng"), /data-retry/);
  assert.doesNotMatch(errorHTML("Không có quyền", false), /data-retry/);
  assert.match(errorHTML("x"), /role="alert"/);
  assert.match(successHTML("Đã lưu"), /Đã lưu/);
  assert.match(emptyHTML("<b>"), /&lt;b&gt;/);
});

test("form field: nhãn, bắt buộc, chỗ hiện lỗi", () => {
  const h = field({ label: "Email", name: "email", type: "email", required: true });
  assert.match(h, /for="f-email"/);
  assert.match(h, /required/);
  assert.match(h, /invalid-feedback/);
  const s = selectField({ label: "Nhóm", name: "g", options: [{ value: 1, text: "A" }, { value: 2, text: "B" }], value: 2 });
  assert.match(s, /<option value="2" selected>B<\/option>/);
  const m = moneyField({ label: "Tổng tiền", name: "total", value: 90000 });
  assert.match(m, /value="90.000"/);
  assert.match(m, /₫/);
});

test("dataTable: canh phải cột tiền, dòng tổng, trạng thái trống", () => {
  const cols = [{ key: "name", title: "Món" }, { key: "amount", title: "Tiền", align: "end", render: (v) => formatVND(v) }];
  const html = dataTable(cols, [{ name: "Phở <b>", amount: 65000 }], { footer: { name: "Tổng", amount: "65.000 ₫" } });
  assert.match(html, /<th scope="col" class="text-end text-nowrap">Tiền<\/th>/);
  assert.match(html, /Phở &lt;b&gt;/);
  assert.match(html, /<tfoot>/);
  assert.match(dataTable(cols, [], { emptyText: "Chưa có món" }), /Chưa có món/);
});
