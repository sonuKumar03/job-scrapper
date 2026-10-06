let sessionToken = "";

export function setSessionToken(token) {
  sessionToken = token;
}

export function getSessionToken() {
  return sessionToken;
}

export async function fetchApi(path, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };

  if (options.method && options.method.toUpperCase() !== "GET" && options.method.toUpperCase() !== "HEAD") {
    if (sessionToken) {
      headers["X-Scrape-Token"] = sessionToken;
    }
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
