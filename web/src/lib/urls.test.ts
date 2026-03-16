import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { getSiteUrl, getAuthCallbackUrl } from "./urls";

describe("getSiteUrl", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv };
    delete process.env.NEXT_PUBLIC_SITE_URL;
    delete process.env.VERCEL_PROJECT_PRODUCTION_URL;
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it("prefers NEXT_PUBLIC_SITE_URL when set", () => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://myapp.vercel.app";
    process.env.VERCEL_PROJECT_PRODUCTION_URL = "other.vercel.app";
    expect(getSiteUrl()).toBe("https://myapp.vercel.app");
  });

  it("falls back to VERCEL_PROJECT_PRODUCTION_URL with https", () => {
    process.env.VERCEL_PROJECT_PRODUCTION_URL = "myapp.vercel.app";
    expect(getSiteUrl()).toBe("https://myapp.vercel.app");
  });

  it("uses explicit fallback when no env vars set", () => {
    expect(getSiteUrl("https://fallback.com")).toBe("https://fallback.com");
  });

  it("defaults to localhost when nothing is set", () => {
    expect(getSiteUrl()).toBe("http://localhost:3000");
  });

  it("never returns localhost when NEXT_PUBLIC_SITE_URL is set", () => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://prod.example.com";
    expect(getSiteUrl()).not.toContain("localhost");
  });

  it("never returns localhost when VERCEL_PROJECT_PRODUCTION_URL is set", () => {
    process.env.VERCEL_PROJECT_PRODUCTION_URL = "prod.vercel.app";
    expect(getSiteUrl()).not.toContain("localhost");
  });
});

describe("getAuthCallbackUrl", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv };
    delete process.env.NEXT_PUBLIC_SITE_URL;
    delete process.env.VERCEL_PROJECT_PRODUCTION_URL;
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it("appends /auth/callback to site URL", () => {
    process.env.NEXT_PUBLIC_SITE_URL = "https://myapp.vercel.app";
    expect(getAuthCallbackUrl()).toBe("https://myapp.vercel.app/auth/callback");
  });

  it("never produces a localhost callback URL in production", () => {
    process.env.VERCEL_PROJECT_PRODUCTION_URL = "myapp.vercel.app";
    const url = getAuthCallbackUrl();
    expect(url).not.toContain("localhost");
    expect(url).toBe("https://myapp.vercel.app/auth/callback");
  });

  it("uses fallback for callback URL", () => {
    const url = getAuthCallbackUrl("https://fallback.com");
    expect(url).toBe("https://fallback.com/auth/callback");
  });
});
