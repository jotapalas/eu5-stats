import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, del, errorMessage, get, post, query } from "./client";

function mockFetch(status: number, body?: unknown) {
  const fn = vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), { status, statusText: "X" }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("prefixes /api and parses JSON", async () => {
    const fetch = mockFetch(200, [{ id: 1 }]);
    await expect(get("/campaigns")).resolves.toEqual([{ id: 1 }]);
    expect(fetch.mock.calls[0][0]).toBe("/api/campaigns");
  });

  it("sends JSON bodies", async () => {
    const fetch = mockFetch(201, { id: 2 });
    await post("/campaigns", { name: "x" });
    const init = fetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"name":"x"}');
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
  });

  it("handles 204", async () => {
    mockFetch(204);
    await expect(del("/sessions/1")).resolves.toBeUndefined();
  });

  it("raises ApiError with the FastAPI detail", async () => {
    mockFetch(409, { detail: "Campaign has sessions; delete them first" });
    const err: ApiError = await get<never>("/x").catch((e: ApiError) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.message).toBe("Campaign has sessions; delete them first");
  });
});

describe("helpers", () => {
  it("joins validation errors", () =>
    expect(errorMessage({ detail: [{ msg: "a" }, { msg: "b" }] }, "f")).toBe("a; b"));
  it("falls back", () => expect(errorMessage(null, "f")).toBe("f"));
  it("builds query strings skipping empty values", () => {
    expect(query({ metric: "gold", tag: null, session: undefined })).toBe("?metric=gold");
    expect(query({})).toBe("");
  });
});
