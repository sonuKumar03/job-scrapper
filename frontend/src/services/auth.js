const TOKEN_KEY = "auth_token";
const USER_KEY = "auth_user";

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function setToken(token) {
  try { localStorage.setItem(TOKEN_KEY, token); } catch {}
}

export function clearToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch {}
}

export function getUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export function setUser(user) {
  try { localStorage.setItem(USER_KEY, JSON.stringify(user)); } catch {}
}

export function isAdmin() {
  return getUser()?.role === "admin";
}

export function logout() {
  clearToken();
  try { localStorage.removeItem(USER_KEY); } catch {}
  window.location.hash = "";
  window.location.reload();
}
