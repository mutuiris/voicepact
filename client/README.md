####markdown
# VoicePact Client (Frontend)

Rich, multi-surface web client for the VoicePact platform.

> Status: ACTIVE DEVELOPMENT (alpha). Core backend contract + payment workflows are implemented; this client is rapidly evolving. Expect breaking changes until first tagged release (v0.1.0-alpha).

## Purpose
The client provides real-time visibility, interaction, and verification flows for spoken-to-digital contracts created through the VoicePact backend. It focuses on inclusivity (low bandwidth + mobile friendly), transparency (live state updates), and trust (clear signing + escrow status cues).

## Key Frontend Capabilities (Planned & Implemented)
- Contract lifecycle UI: recording → transcription → extraction → party confirmations → escrow → settlement.
- Live status streaming via WebSocket (contract, payment, signature events).
- Multi-modal party verification entry points (deep link from SMS / USSD code hint display / manual ID entry).
- Secure OTP confirmation & signature capture surfaces.
- Escrow & payment timeline visualization.
- Accessibility & low-data mode (progressive enhancement, image-light variant, skeleton states, offline hints).
- Internationalization scaffolding (i18n) (planned).
- Role-aware dashboard (buyer / seller / agent / auditor) (incremental rollout).
- Incident / dispute initiation flow (planned).

## Technology Stack
- Framework: Next.js (App Router) + TypeScript.
- Styling: (Planned) Tailwind CSS + CSS Modules; currently using default styles while scaffolding.
- State / Data: React Server Components + client-side SWR (planned) + WebSockets for live channels.
- Auth Context: Phone-based session tokens retrieved from backend OTP flow (integration pending).
- Build & Deploy: Vercel (preview branches) → Production.
- Testing: Jest / React Testing Library (unit), Playwright (E2E planned), Lighthouse CI (performance & a11y planned).

## Directory Structure (Target Layout)
```
client/
  app/
    (marketing)/
    dashboard/
      contracts/
      payments/
      disputes/
    api/ (Next.js route handlers for proxy helpers if needed)
    layout.tsx
    page.tsx (landing / login gateway)
  components/
    contracts/
    payments/
    shared/
    forms/
    charts/
  hooks/
  lib/
    api.ts (REST + WebSocket helpers)
    config.ts
    formatters.ts
    websocket.ts
  styles/
  public/
  tests/
    unit/
    e2e/ (Playwright)
  scripts/
```
(Existing files will gradually migrate into this structure as features land.)

## Environment Configuration
Create `client/.env.local` (NOT committed):
```
# Core API endpoints
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_WEBSOCKET_BASE=ws://localhost:8000

# Feature flags (string 'true'/'false')
NEXT_PUBLIC_FEATURE_LOW_DATA_MODE=true
NEXT_PUBLIC_FEATURE_ESCROW_TIMELINE=true
NEXT_PUBLIC_FEATURE_ROLE_AWARE_DASHBOARD=false
NEXT_PUBLIC_FEATURE_I18N=false

# Analytics / monitoring (future)
NEXT_PUBLIC_SENTRY_DSN=
```

## Local Development
1. Ensure backend is running (see root README: FastAPI on :8000).
2. Install dependencies:
   ```bash
   cd client
   npm install
   ```
3. Run dev server:
   ```bash
   npm run dev
   ```
4. Visit http://localhost:3000.
5. (Optional) Run with profiling: `ANALYZE=true npm run build` then `npm start`.

### Useful Scripts
```bash
npm run dev          # Start dev server
npm run build        # Production build
npm start            # Start built app
npm run lint         # ESLint
npm run type-check   # TypeScript only check
npm test             # Jest unit tests (add --watch)
```

## API Integration Layer
A thin wrapper (lib/api.ts) will expose typed functions:
```ts
export async function fetchContract(id: string) {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/contracts/${id}`);
  if (!res.ok) throw new Error('Failed contract fetch');
  return res.json() as Promise<ContractDTO>;
}
```
WebSocket helper (lib/websocket.ts) manages auto-reconnect + exponential backoff.

### Event Channels (Planned Mapping)
| Channel | Event Types | Purpose |
|---------|-------------|---------|
| contracts/{id}/live | contract_updated, contract_confirmed, signature_added | Real-time contract state |
| payments/{id}/live  | payment_status, escrow_released | Escrow + settlement updates |

## State & Caching Strategy
- RSC for SSR-friendly initial hydration of dashboards.
- SWR (or TanStack Query evaluation) for client caching; still under assessment.
- WebSocket pushes trigger cache invalidation via a lightweight event bus.

## UI / UX Guidelines
- Color semantics: Status-driven badges (draft / processing / awaiting-party / escrow / released / disputed).
- Low bandwidth: Avoid large third-party bundles; defer charts / heavy visualizations.
- Progressive enhancement: Core contract reading & confirmation works without JS (goal) – forms fallback.
- Accessibility: Semantic landmarks, focus management on route changes, alt text & ARIA for dynamic statuses.

## Security Considerations
- Never store private keys in client.
- Only store short-lived session token (HTTP-only cookie preferred) – integration to be aligned with backend.
- Phone number masking on UI except final 4 digits in shared contexts.
- All WebSocket connections upgraded over wss:// in production.

## Testing Strategy
Current minimal tests; roadmap:
- Unit: Pure utility + component logic (formatters, computation helpers).
- Component Snapshot + Interaction: Contract status badge, escrow progress bar.
- E2E (Playwright): Contract creation happy path (after stable API mocks), signature flow, payment release.
- Performance Budgets: Lighthouse CI thresholds (First Contentful Paint, CLS, total JS size < 250KB initial target).

### Example Jest Test Skeleton
```ts
import { formatContractStatus } from '@/lib/formatters';

describe('formatContractStatus', () => {
  it('maps internal code to human label', () => {
    expect(formatContractStatus('awaiting_party')).toBe('Awaiting Party Confirmation');
  });
});
```

## Roadmap (Client-Specific)
- [x] Initial Next.js scaffold
- [ ] Unified API helper + error boundary surfaces
- [ ] Contract detail view with streaming updates
- [ ] Signature / OTP modal workflow
- [ ] Escrow timeline visualization
- [ ] Role-aware dashboard segmentation
- [ ] Dispute initiation wizard
- [ ] Low-data mode toggle + heuristics
- [ ] Offline caching (service worker phase 1)
- [ ] i18n (EN/FR/SWA baseline)
- [ ] PWA install & push notifications (milestone after stable flows)

## Contributing (Frontend)
1. Branch from `client/` aligned main: `git checkout -b feat/client-contract-view`.
2. Keep PRs small & feature-scoped.
3. Add/Update tests for new logic.
4. Run lint & type checks before push:
   ```bash
   npm run lint && npm run type-check
   ```
5. Provide screenshots / short clip for complex UI in PR description.

### Code Style
- ESLint + Prettier (config incoming; will enforce import grouping + no unused exports).
- Prefer function components + hooks.
- Avoid heavy global state; colocate where possible.

## Communication with Backend
Important divergence: Backend currently lists DB as SQLite (dev) & may expose endpoints described in root README. Any endpoint mismatches should be surfaced via a GitHub Issue tagged `api-contract`.

### Temporary Mocking
While some endpoints finalize, you can:
```bash
npm install msw --save-dev
```
Add mock handlers in `tests/mocks/handlers.ts` to simulate responses for rapid UI iteration.

## Deployment
Preview: Automatic Vercel deploy on PR (link appears in PR checks).
Production: Merge to `main` triggers production deployment.
Environment variables in Vercel must mirror `.env.local` without secrets you do not need.

## Monitoring (Planned)
- Basic console error boundary logging → Sentry (feature flag gate).
- Web Vitals export to analytics endpoint for performance regression tracking.

## Known Gaps / Open Questions
- Auth handshake finalization (session token issuance path).
- Role mapping & authorization boundaries in UI components.
- Payment event normalization vs separate channels.
- Dispute evidence upload flow (will require backend media endpoint + storage policy alignment).

If you are touching any area above, please open or link an Issue before large refactors.

## License
Inherits root project MIT License.

## Acknowledgements
Part of the VoicePact platform – bridging verbal agreements & digital contract + escrow automation across African markets.

---

Nairobi, Kenya - 2025 (Client Alpha)