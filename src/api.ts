const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function formatApiError(detail: unknown) {
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String(item.msg);
        }
        return String(item);
      })
      .join(". ");
  }

  if (typeof detail === "string") return detail;
  return "Request failed. Please try again.";
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });

  if (!response.ok) {
    let detail: unknown = undefined;
    try {
      const payload = await response.json();
      detail = payload.detail;
    } catch {
      throw new Error("Request failed. Please try again.");
    }
    throw new Error(formatApiError(detail));
  }

  return response.json();
}
