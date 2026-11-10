import { getToken, logout } from "./auth.js";

export const API_BASE = "/api";

const STATUS_MESSAGES = {
  0: "Không kết nối được máy chủ",
  400: "Yêu cầu không hợp lệ",
  401: "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại",
  403: "Bạn không có quyền thực hiện thao tác này",
  404: "Không tìm thấy dữ liệu",
  409: "Dữ liệu bị trùng",
  413: "File quá lớn",
  422: "Dữ liệu không hợp lệ, kiểm tra lại các ô được đánh dấu",
  500: "Lỗi hệ thống, vui lòng thử lại",
};

export class ApiError extends Error {
  constructor(status, message, details = null, code = null) {
    super(message);
    this.status = status;
    this.details = details; // 422: [{ field, message }]
    this.code = code; // 'FORBIDDEN', 'NOT_FOUND', 'VALIDATION_ERROR', ...
  }
}

/**
 * api('/groups')                                  -> GET /api/groups (tự gắn Bearer token)
 * api('/groups', { method: 'POST', body: {...} })
 * api('/receipts', { method: 'POST', formData })  -> upload file
 */
export async function api(
  path,
  { method = "GET", body, formData, auth = true } = {},
) {
  const headers = { Accept: "application/json" };
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (formData) {
    payload = formData; // upload file: không tự đặt Content-Type
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(API_BASE + path, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, STATUS_MESSAGES[0]);
  }

  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (res.ok) return data;

  const err = data?.error;
  // 401 ở /auth/login, /auth/register là sai mật khẩu, không phải hết phiên
  if (res.status === 401 && !path.startsWith("/auth/")) {
    logout();
    throw new ApiError(401, STATUS_MESSAGES[401], null, "UNAUTHORIZED");
  }
  throw new ApiError(
    res.status,
    err?.message ??
      STATUS_MESSAGES[res.status] ??
      `Có lỗi xảy ra (${res.status})`,
    err?.details ?? null,
    err?.code ?? null,
  );
}

export const get = (p) => api(p);
export const post = (p, body) => api(p, { method: "POST", body });
export const put = (p, body) => api(p, { method: "PUT", body });
export const patch = (p, body) => api(p, { method: "PATCH", body });
export const del = (p) => api(p, { method: "DELETE" });
export const upload = (p, formData) => api(p, { method: "POST", formData });
