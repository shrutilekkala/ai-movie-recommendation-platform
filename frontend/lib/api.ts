import {
  AgentResponse,
  AuthResponse,
  CatalogStatus,
  HomeFeed,
  LibraryItem,
  Recommendation,
  RecommendationStatus,
  User,
} from "./types";

const browserApi = () =>
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000/api/v1";

const serverApi = () =>
  process.env.INTERNAL_API_URL ??
  "http://backend:8000/api/v1";

export async function getHomeFeed(): Promise<HomeFeed> {
  const response = await fetch(
    `${
      typeof window === "undefined"
        ? serverApi()
        : browserApi()
    }/content/feed`,
    {
      cache: "no-store",
    }
  );

  if (!response.ok) {
    throw new Error(`NEXUS API returned ${response.status}`);
  }

  return response.json();
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  token?: string
): Promise<T> {
  const headers = new Headers(init.headers);

  headers.set("Content-Type", "application/json");

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${browserApi()}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let message = "Request failed";

    try {
      const body = await response.json();

      message =
        body.detail ??
        body.message ??
        message;
    } catch {
      // Ignore non-JSON error bodies.
    }

    throw new Error(message);
  }

  return response.json();
}

/* =========================================================
   AUTH
   ========================================================= */

export const login = (
  email: string,
  password: string
) =>
  request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
    }),
  });

export const register = (
  email: string,
  display_name: string,
  password: string
) =>
  request<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email,
      display_name,
      password,
    }),
  });

export const me = (token: string) =>
  request<User>("/auth/me", {}, token);

/* =========================================================
   USER STATE
   ========================================================= */

export const getLibrary = (token: string) =>
  request<LibraryItem[]>("/me/library", {}, token);

export const patchState = (
  token: string,
  id: number,
  data: object
) =>
  request<any>(
    `/me/content/${id}`,
    {
      method: "PATCH",
      body: JSON.stringify(data),
    },
    token
  );

export const recordEvent = (
  token: string,
  data: object
) =>
  request<any>(
    "/me/events",
    {
      method: "POST",
      body: JSON.stringify(data),
    },
    token
  );

/* =========================================================
   RECOMMENDATIONS
   ========================================================= */

export const getRecommendationStatus = () =>
  request<RecommendationStatus>("/recommendations/status");

export const getMyRecommendations = (
  token: string,
  limit = 12
) =>
  request<Recommendation[]>(
    `/recommendations/me?limit=${limit}`,
    {},
    token
  );

export const getMovieLensUserRecommendations = (
  userId: number,
  limit = 10
) =>
  request<Recommendation[]>(
    `/recommendations/movielens/${userId}?limit=${limit}`
  );

/* =========================================================
   REALTIME
   ========================================================= */

export const getRealtimeSession = (token: string) =>
  request<any>("/realtime/session", {}, token);

/* =========================================================
   PHASE 5 SEMANTIC ENDPOINTS
   Retained for System Lab / debugging.
   ========================================================= */

export const semanticSearch = (
  query: string,
  token?: string,
  limit = 12,
  source: "text" | "voice" = "text",
  language: "all" | "en" | "te" = "all"
) =>
  request<any>(
    `/discovery/search?q=${encodeURIComponent(
      query
    )}&limit=${limit}&source=${source}&language=${language}`,
    {},
    token
  );

export const debugSemanticSearch = (
  query: string,
  token?: string,
  limit = 12,
  language: "all" | "en" | "te" = "all"
) =>
  request<any>(
    `/discovery/debug?q=${encodeURIComponent(
      query
    )}&limit=${limit}&language=${language}`,
    {},
    token
  );

export const getSemanticStatus = () =>
  request<any>("/discovery/status");

export const getCatalogStatus = () =>
  request<CatalogStatus>("/discovery/catalog-status");

/* =========================================================
   PHASE 6 AGENT
   ========================================================= */

export const runAgent = (
  query: string,
  token?: string,
  limit = 5
) =>
  request<AgentResponse>(
    `/agent/run?query=${encodeURIComponent(
      query
    )}&limit=${limit}`,
    {},
    token
  );

export const parseAgentIntent = (query: string) =>
  request<any>(
    `/agent/intent?query=${encodeURIComponent(query)}`
  );