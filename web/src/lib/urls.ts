/**
 * Resolves the production site URL for use in redirects and magic links.
 * Priority: NEXT_PUBLIC_SITE_URL > VERCEL_PROJECT_PRODUCTION_URL > fallback
 */
export function getSiteUrl(fallback?: string): string {
  if (process.env.NEXT_PUBLIC_SITE_URL) {
    return process.env.NEXT_PUBLIC_SITE_URL;
  }
  if (process.env.VERCEL_PROJECT_PRODUCTION_URL) {
    return `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`;
  }
  return fallback || "http://localhost:3000";
}

/**
 * Returns the full auth callback URL for magic link redirects.
 */
export function getAuthCallbackUrl(fallback?: string): string {
  return `${getSiteUrl(fallback)}/auth/callback`;
}
