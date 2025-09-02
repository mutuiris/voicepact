# VoicePact

**Voice powered contract automation & escrow platform for African markets**

VoicePact converts spoken business agreements into structured, verifiable digital contracts with automated mobile money escrow, multi‑modal party verification (Voice, SMS, USSD, OTP), and transparent lifecycle tracking.

> Status
> - Backend: Early alpha – core recording → processing → confirmation → escrow flow under active build.
> - Client (Web Dashboard): ACTIVE DEVELOPMENT (alpha) – rapid iteration; breaking changes possible until `v0.1.0-alpha`.
> - API Surface: Subject to refinement; treat undocumented endpoints as unstable.

---

## 1. Overview

Millions of verbal agreements across African informal and SME sectors remain unenforced or disputed due to lack of timely contract formalization, trusted payment holding, and accessible verification channels. VoicePact bridges this gap by turning real-time spoken negotiations into structured contracts, securing funds via escrow, and enabling confirmations across both feature phones and smartphones.

## 2. Problem & Opportunity

| Challenge | Impact | VoicePact Approach |
|-----------|--------|--------------------|
| Verbal deals not documented | Disputes, lost trust | Immediate voice capture → transcription → structured contract |
| Limited digital access | Exclusion of feature phone users | Voice + SMS + USSD multi-modal flows |
| Payment risk & mistrust | Delivery/payment disputes | Conditional escrow with event-based release |
| High friction legal processes | Abandonment | Lightweight, AI-assisted term extraction & simplified signature |
| Lack of auditability | Hard to resolve disputes | Immutable event logs + cryptographic signatures |

## 3. Key Features

Implemented / In Progress
- Voice Contract Generation (speech → text → structured terms)
- Multi-Modal Verification (SMS confirmations, planned USSD)
- Automated Escrow Integration (mobile money via Africa's Talking Payments)
- Cryptographic Integrity (Ed25519 signatures; audit event trail)
- Real-Time Status Streaming (WebSocket channels)
- Inclusive Design (feature phone & smartphone flows)

Planned Enhancements
- Dispute filing & evidence attachment
- Role-based dashboards (buyer, seller, agent, auditor)
- Multi-language support (EN / SWA)
- Offline-friendly PWA & low-data assets
- Contract templating library & clause recommender

## 4. Architecture

High-Level Diagram
```
┌─────────────────┐    ┌──────────────────┐    ┌────────────────────┐    ┌──────────────────┐
│  Voice Capture  │───▶│  AI Processing   │───▶│  Contract Assembly │───▶│  Persistence      │
│ (AT Voice API)  │    │ (Whisper + NLP)  │    │  + Validation      │    │ (SQLite dev /     │
└─────────────────┘    └──────────────────┘    └────────────────────┘    │ PostgreSQL prod)  │
        │                      │                     │                    └──────────────────┘
        ▼                      │                     ▼
┌─────────────────┐            │           ┌─────────────────┐
│  SMS / USSD     │◀───────────┼──────────▶  Verification   │
│  Confirmations  │            │           │  & Signatures   │
└─────────────────┘            │           └─────────────────┘
        │                      │                     │
        ▼                      ▼                     ▼
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ Escrow Payments │    │ Event Streaming  │    │ Client Dashboard │
│ (AT Payments)   │    │ (WebSockets)     │    │ (Next.js)        │
└─────────────────┘    └──────────────────┘    └──────────────────┘
```

## 5. Technology Stack

Backend
- FastAPI (async I/O)
- Speech Processing: Whisper (local)
- NLP / Term Extraction: (initial rule-based + LLM hybrid pipeline)
- Data: SQLite (dev), PostgreSQL (production target)
- Cache / Sessions: Redis
- Crypto: Ed25519 signatures (python-cryptography)

Frontend (Client –> in development)
- Next.js (App Router) + TypeScript
- WebSocket live channels
- Planned: Tailwind CSS, SWR / TanStack Query, Playwright tests

External Integrations
- Africa's Talking: Voice, SMS, USSD, Payments
- Mobile Money Rails: M-Pesa, Airtel (through AT)
- PDF Contract Generation (planned)
- Future: Object storage (audio + evidence artifacts)

## 6. Data & Processing Flow

1. Initiate Voice Conference (two+ parties).
2. Record & Store Audio (temporary staging).
3. Transcribe & Segment Speakers.
4. Extract Contract Terms (parties, commodity/service, quantity, pricing, delivery, dates).
5. Generate Draft Contract (JSON + human-readable PDF/summary).
6. Dispatch Multi-Channel Confirmations (SMS codes / USSD menu).
7. Collect Confirmations + Signatures (cryptographic + OTP).
8. Initiate Escrow Hold (conditional on confirmations).
9. Track Delivery / Release Conditions.
10. Escrow Release Event → Funds distributed & contract archived.

## 7. Security Model

Principles
- Least privilege separation between processing steps.
- No private keys in frontend – signatures are server-side.
- Audio encryption at rest (planned envelope encryption).
- Ed25519 signatures for contract canonical form hash.
- Immutable event log (append-only table) for evidentiary chain.

Controls (Current / Planned)
- OTP-backed phone identity binding.
- Rate limiting: SMS / USSD confirmation attempts.
- Integrity hashing of audio + transcript bundles.
- Secure webhook verification (HMAC headers – planned).
- PII minimization: Partial phone masking in UI.

## 8. Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Redis server
- Africa's Talking Sandbox Account
- ngrok for local Voice/SMS/USSD callbacks

### Clone
```bash
git clone https://github.com/mutuiris/voicepact.git
cd voicepact
```

### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill credentials
uvicorn main:app --reload --port 8000
```

### Client (Web Dashboard) Setup
```bash
cd client
npm install
cp .env.local.example .env.local  # create if missing
npm run dev
```

Visit: http://localhost:3000

### Local Webhooks
```bash
ngrok http 8000
# Update WEBHOOK_BASE_URL in backend .env with generated https URL
```

## 9. Environment Configuration

Backend `.env`
```env
AT_USERNAME=sandbox
AT_API_KEY=your_api_key_here
AT_VOICE_NUMBER=+254XXXXXXXXX

DATABASE_URL=sqlite:///./voicepact.db
REDIS_URL=redis://localhost:6379

SECRET_KEY=your_secret_key
SIGNATURE_PRIVATE_KEY=your_ed25519_private_key

WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok.io
```

Client `.env.local`
```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_WEBSOCKET_BASE=ws://localhost:8000
NEXT_PUBLIC_FEATURE_LOW_DATA_MODE=true
NEXT_PUBLIC_FEATURE_ESCROW_TIMELINE=true
NEXT_PUBLIC_FEATURE_ROLE_AWARE_DASHBOARD=false
```

## 10. API Reference

### POST /voice/conference/create
Initiate multi-party recording session.

Request
```json
{
  "parties": ["+254712345678", "+254798765432"],
  "contract_type": "agricultural_supply",
  "expected_duration": 600
}
```

Response
```json
{
  "conference_id": "conf_1234567890",
  "recording_url": "https://voice.africastalking.com/recording/abc123",
  "status": "active",
  "webhook_url": "https://yourapp.com/voice/webhook"
}
```

### POST /contracts/process
Convert recorded audio to structured contract.
```json
{
  "audio_url": "https://voice.africastalking.com/recording/abc123",
  "parties": [
    {"phone": "+254712345678", "role": "seller"},
    {"phone": "+254798765432", "role": "buyer"}
  ]
}
```

### POST /sms/webhook
Inbound SMS confirmation handler.

### POST /ussd/webhook
USSD session state machine entry point.


## 11. Usage Examples

Voice Conference + Processing (Python)
```python
import requests, json, websocket

base = "http://localhost:8000"

r = requests.post(f"{base}/voice/conference/create", json={
    "parties": ["+254712345678", "+254798765432"],
    "contract_type": "agricultural_supply"
})
conference_id = r.json()["conference_id"]

contract_r = requests.post(f"{base}/contracts/process", json={
    "audio_url": f"https://voice.africastalking.com/recording/{conference_id}",
    "parties": [
        {"phone": "+254712345678", "role": "seller"},
        {"phone": "+254798765432", "role": "buyer"}
    ]
})
contract_id = contract_r.json()["contract_id"]

def on_message(ws, message):
    data = json.loads(message)
    if data.get("type") == "contract_confirmed":
        print("Confirmed:", data["contract_id"])

ws = websocket.WebSocketApp(f"ws://localhost:8000/contracts/{contract_id}/live",
                            on_message=on_message)
ws.run_forever()
```

USSD Flow
```
User dials: *483#
┌───────────────────────────────┐
│ VoicePact                     │
│ 1. View My Contracts          │
│ 2. Confirm Delivery           │
│ 3. Check Payments             │
│ 4. Report Issue               │
└───────────────────────────────┘
```

## 12. Performance & Optimization

Benchmarks (Targets)
- Voice Processing (10 min audio): 3–5s (post-transcription pipeline)
- Contract Generation: < 1s
- SMS Delivery: 2–3s average
- Payment Escrow Trigger: 10–15s (mobile money network variability)
- USSD Response: < 2s menu navigation

Optimization Features
- Local Whisper inference (removes external latency)
- Redis caching of frequent contract lookups
- Async non-blocking I/O for external API calls
- Connection pooling for Africa's Talking endpoints


## 13. Frontend (Client) Status

Located in `/client` directory (Next.js). Current focus:
- Contract detail real-time panel
- OTP & signature capture modal
- Escrow timeline visualization
- Role‑aware dashboards (in design)


## 14. Roadmap

Short Term
- [ ] Stabilize contract processing endpoint
- [ ] WebSocket event schema versioning
- [ ] USSD confirmation flow finalization
- [ ] Escrow release conditions engine
- [ ] Basic dispute initiation endpoint

Mid Term
- [ ] Multi-language
- [ ] PWA offline caching (service worker)
- [ ] Evidence file storage integration
- [ ] Advanced analytics (contract completion metrics)

Long Term
- [ ] Clause recommendation model fine-tuning
- [ ] On-device / edge speech inference optimization
- [ ] Federated deployment support (multi-tenancy)
- [ ] Regulatory compliance modules (jurisdictional templates)


## 15. License

MIT – see [LICENSE](LICENSE).



## Acknowledgements

Built for Africa's Talking Open Hackathon: Billing & Payment Solutions  
Nairobi, Kenya – August 2025

---

> NOTE: Frontend client is in active development; API contracts may adjust.
