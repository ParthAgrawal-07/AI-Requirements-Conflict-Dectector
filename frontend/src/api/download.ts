// File downloads (Pranshu — US-41, US-59, US-61, US-18). Exports need the bearer token, which
// lives in memory only (US-19), so a plain <a href> cannot fetch them: download through fetch, then
// hand the browser a temporary object URL.

import { ApiError, apiUrl, getAccessToken, type RequestOptions } from "./client";

export async function apiDownload(
  path: string,
  filename: string,
  query?: RequestOptions["query"],
): Promise<void> {
  const token = getAccessToken();
  const response = await fetch(apiUrl(path, query), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    let message = "The download failed";
    try {
      const body = (await response.json()) as { error?: { message?: string; code?: string } };
      message = body.error?.message ?? message;
      throw new ApiError(response.status, body.error?.code ?? "http_error", message);
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(response.status, "http_error", message);
    }
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
