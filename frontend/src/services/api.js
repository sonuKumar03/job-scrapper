import { getToken, clearToken } from "./auth";

export async function fetchApi(path, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };

  const token = getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (options.method && options.method.toUpperCase() !== "GET" && options.method.toUpperCase() !== "HEAD") {
    if (!headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
  }

  const baseUrl = import.meta.env.VITE_API_URL || "";
  const res = await fetch(`${baseUrl}/api/${path}`, {
    ...options,
    headers,
  });

  const data = await res.json().catch(() => null);

  if (res.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error("Session expired. Please log in again.");
  }

  if (!res.ok) {
    let errorMsg = "An error occurred while fetching data";
    if (data && data.detail) {
      if (typeof data.detail === "string") {
        errorMsg = data.detail;
      } else if (Array.isArray(data.detail)) {
        errorMsg = data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
      }
    }
    throw new Error(errorMsg);
  }

  return data;
}

export async function loginApi(email, password) {
  const baseUrl = import.meta.env.VITE_API_URL || "";
  const res = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.detail || "Login failed");
  }
  return data;
}
