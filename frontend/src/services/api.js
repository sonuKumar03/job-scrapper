let sessionToken = "";
let sessionRefresh = null;

export function setSessionToken(token) {
  sessionToken = token;
}

export function getSessionToken() {
  return sessionToken;
}

export async function fetchApi(path, options = {}, retrySession = true) {
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

  if (res.status === 403 && retrySession && headers["X-Scrape-Token"] &&
      data?.detail === "Valid X-Scrape-Token header required. Fetch from /api/session first.") {
    if (!sessionRefresh) {
      sessionRefresh = fetchApi("session")
        .then((session) => setSessionToken(session.token))
        .finally(() => { sessionRefresh = null; });
    }
    await sessionRefresh;
    return fetchApi(path, options, false);
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
