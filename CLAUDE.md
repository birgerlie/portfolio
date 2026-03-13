# Glass Box Fund — Portfolio Web App

## Overview

Investment club dashboard for a small fund ("Glass Box Fund"). Members can view fund performance, invest/redeem, and vote on the investment universe. Admins manage members, view fees, and have emergency controls.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | Next.js 16 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS v4 |
| Animation | Framer Motion |
| Charts | Recharts |
| Auth | Supabase (magic link OTP) |
| Database | PostgreSQL via Prisma |
| Payments | Stripe (manual capture) |
| Trading | Alpaca API (paper/live) |
| Deployment | Vercel |

## Project Structure

```
web/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── page.tsx            # Dashboard (hero, chart, stats, engine analysis, positions)
│   │   ├── admin/page.tsx      # Admin dashboard (fund overview, fees, members, liquidation)
│   │   ├── journal/page.tsx    # Daily engine analysis + belief state
│   │   ├── reports/page.tsx    # Weekly performance tables
│   │   ├── universe/page.tsx   # Investment universe voting
│   │   ├── invest/page.tsx     # Stripe payment flow
│   │   ├── redeem/page.tsx     # Redemption requests
│   │   ├── settings/page.tsx   # User profile
│   │   ├── login/page.tsx      # Magic link login
│   │   └── api/                # API routes
│   │       ├── admin/          # stats, members, invite, liquidate
│   │       ├── webhooks/stripe # Stripe webhook handler
│   │       └── create-payment-intent
│   ├── components/             # Shared components
│   │   ├── nav-bar.tsx         # Top navigation (server component)
│   │   ├── engine-status.tsx   # Real-time engine indicator (Supabase realtime)
│   │   ├── hero.tsx            # Animated portfolio value
│   │   ├── nav-chart.tsx       # NAV area chart
│   │   ├── position-list.tsx   # Holdings table
│   │   ├── activity-rings.tsx  # SVG progress rings
│   │   ├── constellation.tsx   # Position scatter plot
│   │   ├── benchmark-race.tsx  # Horizontal bar race
│   │   ├── timeline.tsx        # Event timeline
│   │   └── narrative.tsx       # Animated blockquote
│   └── lib/                    # Shared utilities
│       ├── admin.ts            # requireAdmin() auth helper
│       ├── prisma.ts           # Prisma client
│       ├── stripe.ts           # Stripe client
│       ├── supabase-server.ts  # Server-side Supabase (SSR cookies)
│       └── supabase-client.ts  # Browser-side Supabase
├── prisma/schema.prisma        # Database schema
└── package.json
src/                            # Python trading engine (separate)
tests/                          # Python tests
```

## Design System (Linear-inspired)

The UI follows a refined dark theme inspired by Linear.app:

| Element | Value |
|---------|-------|
| Background | `#0a0a0a` (not pure black) |
| Text primary | `#f5f5f5` |
| Text secondary | `text-white/65` |
| Text tertiary | `text-white/40` |
| Text muted | `text-white/30` |
| Borders | `border-white/[0.06]` |
| Row dividers | `border-white/[0.03]` |
| Surface hover | `bg-white/[0.02]` |
| Surface subtle | `bg-white/[0.06]` |
| Green (positive) | `#3dd68c` |
| Red (negative) | `#f76e6e` |
| Border radius | `rounded-lg` (8px) |
| Labels | `text-[11px] uppercase tracking-[0.05em] text-white/40 font-medium` |
| Values | `text-xl font-medium tracking-tight` |
| Body text | `text-[13px]` |
| Page titles | `text-2xl font-medium tracking-tight` |
| Buttons (primary) | `bg-white text-[#0a0a0a] rounded-lg text-[13px] font-medium` |
| Inputs | `bg-white/[0.03] border-white/[0.06] rounded-lg text-[13px]` |
| Stat grids | `gap-px bg-white/[0.04]` divider pattern (no card backgrounds) |
| Tables | Wrapped in `border border-white/[0.06] rounded-lg overflow-hidden` |

**Key principles:**
- Text hierarchy via white opacity, not zinc color scale
- No card backgrounds for stat grids — use 1px divider lines
- Tight padding (p-4, py-2.5) and smaller radii (8px not 12px)
- Negative letter-spacing on values (`tracking-tight`)
- 11px uppercase labels with 0.05em tracking

## Auth Architecture

- **Middleware** (`src/middleware.ts`): Redirects unauthenticated users to `/login`. Skips if Supabase env vars not configured (build safety).
- **Admin auth**: `requireAdmin()` in `lib/admin.ts` — checks Supabase user + Prisma member role or hardcoded admin emails.
- **All admin endpoints** require `requireAdmin()` for both GET and mutating operations.
- Login via Supabase magic link OTP.

## Key Patterns

- Server Components for data fetching, Client Components for interactivity
- `export const dynamic = "force-dynamic"` on data pages
- Prisma for all DB access
- Supabase realtime for engine heartbeat status
- Stripe manual capture for investment payments
- Webhook at `/api/webhooks/stripe` handles `payment_intent.succeeded` and `payment_intent.payment_failed`

## Environment Variables

```
# Supabase
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Database
DATABASE_URL=

# Stripe
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# Alpaca (trading)
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_PAPER=true
```

## Running

```bash
cd web
npm install
npx prisma generate
npm run dev          # http://localhost:3000
```

## Building

```bash
cd web
npm run build        # prisma generate + next build
```

## Engine Integration

The dashboard reads from a Python trading engine that writes to the same Postgres DB:
- `engine_heartbeat` — real-time status (Supabase realtime subscription)
- `fund_snapshots` — NAV, cash, positions count
- `positions` — current holdings
- `journals` — daily analysis with regime, trades, SiliconDB epistemology data
- `weekly_nav` — weekly performance history

The engine is a separate Python process in `src/` — not part of the web build.
