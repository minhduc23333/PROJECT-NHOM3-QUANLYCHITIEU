const TOKEN_KEY = "smartsplit_token";
const USER_KEY = "smartsplit_user";

export const getToken = () => localStorage.getItem(TOKEN_KEY);

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY));
  } catch {
    return null;
  }
}

export function setUser(u) {
  localStorage.setItem(USER_KEY, JSON.stringify(u));
}

// Đọc hạn (exp) trong JWT để chặn route sớm, không cần gọi server
function tokenExpired(token) {
  try {
    const b64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const { exp } = JSON.parse(atob(b64));
    return exp ? exp * 1000 <= Date.now() : false;
  } catch {
    return true;
  }
}

export function isLoggedIn() {
  const t = getToken();
  if (!t) return false;
  if (tokenExpired(t)) {
    clearSession();
    return false;
  }
  return true;
}

export function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  setUser(user);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function logout() {
  clearSession();
  if (location.hash !== "#/login") location.hash = "#/login";
}
