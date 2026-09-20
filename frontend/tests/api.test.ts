import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../src/services/api";

function mockFetchOnce(body: unknown, init: { status?: number; ok?: boolean } = {}) {
  const status = init.status ?? 200;
  global.fetch = vi.fn().mockResolvedValue({
    ok: init.ok ?? status < 400,
    status,
    statusText: "error",
    json: async () => body,
  } as Response);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    mockFetchOnce([{ id: 1, name: "Gateway" }]);
    const targets = await api.listTargets();
    expect(targets).toEqual([{ id: 1, name: "Gateway" }]);
  });

  it("throws ApiError with the backend detail message on failure", async () => {
    mockFetchOnce({ detail: "Target not found" }, { status: 404, ok: false });
    await expect(api.deleteTarget(999)).rejects.toMatchObject({
      status: 404,
      message: expect.stringContaining("Target not found"),
    });
  });

  it("wraps network failures in an ApiError with status 0", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("network error"));
    await expect(api.getStatus()).rejects.toBeInstanceOf(ApiError);
    await expect(api.getStatus()).rejects.toMatchObject({ status: 0 });
  });

  it("builds query strings only from defined params", async () => {
    mockFetchOnce([]);
    await api.listMeasurements({ target_id: 3, start: undefined, limit: 50 });
    const calledUrl = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(calledUrl).toContain("target_id=3");
    expect(calledUrl).toContain("limit=50");
    expect(calledUrl).not.toContain("start=");
  });

  it("sends no body for a 204 delete response", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => ({}) } as Response);
    await expect(api.deleteTarget(1)).resolves.toBeUndefined();
  });
});
