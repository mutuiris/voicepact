# VoicePact

**Voice powered contract automation platform for African markets**

VoicePact transforms spoken business agreements into legally binding digital contracts with automated billing, escrow payments, and multi-modal verification using Africa's Talking APIs.

## Overview

VoicePact addresses the critical gap between verbal business agreements and formal contract execution in African markets. By leveraging voice AI, mobile money integration, and multi-modal communication channels, it enables inclusive contract automation that works for users across all literacy levels and device types.

### Key Features

- **Voice Contract Generation**: AI powered speech to text and contract term extraction
- **Multi-Modal Verification**: SMS confirmations, USSD feature phone access, OTP security
- **Automated Escrow**: Mobile money integration with conditional payment releases
- **Cryptographic Security**: Digital signatures and audit trails without blockchain complexity
- **Real-Time Dashboard**: Live contract status updates and payment tracking
- **Inclusive Design**: Works on smartphones, feature phones, and web interfaces

## Architecture

### Technology Stack

**Backend**
- FastAPI with async request handling
- SQLite with WAL mode for data persistence
- Redis for caching and session management
- OpenAI Whisper for local speech-to-text processing
- Python cryptography library for digital signatures

**Frontend**
- Next.js with TypeScript
- Real-time updates via WebSocket connections
- Responsive design for mobile and desktop
- Progressive Web App capabilities

**External Integrations**
- Africa's Talking Voice, SMS, USSD, Payments, and OTP APIs
- M-Pesa and Airtel Money via AT Payments
- PDF generation for legal compliance

### System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Voice Call    │───▶│  AI Processing   │───▶│   Contract DB   │
│ (AT Voice API)  │    │ (Whisper + GPT)  │    │  (PostgreSQL)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ SMS/USSD Confirm│    │ Payment Escrow   │    │ Real-time UI    │
│ (AT SMS/USSD)   │    │ (AT Payments)    │    │   (WebSocket)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Redis server
- Africa's Talking developer account
- ngrok for local webhook testing

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/mutuiris/voicepact.git
   cd voicepact
   ```

2. **Backend setup**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Frontend setup**
   ```bash
   cd frontend
   npm install
   ```

4. **Environment configuration**
   ```bash
   cp .env.example .env
   # Configure your Africa's Talking credentials and other settings
   ```

### Environment Variables

Create `.env` file in the backend directory:

```env
# Africa's Talking Configuration
AT_USERNAME=sandbox
AT_API_KEY=your_api_key_here
AT_VOICE_NUMBER=+254XXXXXXXXX

# Database Configuration
DATABASE_URL=sqlite:///./voicepact.db
REDIS_URL=redis://localhost:6379

# Security
SECRET_KEY=your_secret_key
SIGNATURE_PRIVATE_KEY=your_ed25519_private_key

# External Services
WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok.io
```

### Development Server

1. **Start Redis server**
   ```bash
   redis-server
   ```

2. **Start backend**
   ```bash
   cd backend
   uvicorn main:app --reload --port 8000
   ```

3. **Start frontend**
   ```bash
   cd frontend
   npm run dev
   ```

4. **Setup webhooks**
   ```bash
   ngrok http 8000
   # Update WEBHOOK_BASE_URL in .env with ngrok URL
   ```

Visit `http://localhost:3000` to access the dashboard.

## API Documentation

### Voice Contract Creation

**POST** `/voice/conference/create`

Create a new voice conference for contract recording.

```json
{
  "parties": ["+254712345678", "+254798765432"],
  "contract_type": "agricultural_supply",
  "expected_duration": 600
}
```

**Response:**
```json
{
  "conference_id": "conf_1234567890",
  "recording_url": "https://voice.africastalking.com/recording/abc123",
  "status": "active",
  "webhook_url": "https://yourapp.com/voice/webhook"
}
```

### Contract Processing

**POST** `/contracts/process`

Process recorded voice conversation into structured contract.

```json
{
  "audio_url": "https://voice.africastalking.com/recording/abc123",
  "parties": [
    {"phone": "+254712345678", "role": "seller"},
    {"phone": "+254798765432", "role": "buyer"}
  ]
}
```

### SMS Confirmation

**POST** `/sms/webhook`

Handle incoming SMS confirmations and contract signatures.

```json
{
  "from": "+254712345678",
  "text": "YES-VC-MAZ-240815-001",
  "linkId": "12345",
  "date": "2025-08-15T10:30:00Z"
}
```

### USSD Integration

**POST** `/ussd/webhook`

Handle USSD session interactions for feature phone users.

```json
{
  "sessionId": "ATUid_session123",
  "phoneNumber": "+254712345678",
  "text": "1*2*VC-MAZ-240815-001",
  "serviceCode": "*483#"
}
```

## Usage Examples

### Agricultural Supply Contract

```python
# Example: Creating a maize supply contract
import requests

# 1. Initiate voice conference
response = requests.post("http://localhost:8000/voice/conference/create", json={
    "parties": ["+254712345678", "+254798765432"],
    "contract_type": "agricultural_supply"
})

conference_id = response.json()["conference_id"]

# 2. After voice recording completes, process contract
contract_response = requests.post("http://localhost:8000/contracts/process", json={
    "audio_url": f"https://voice.africastalking.com/recording/{conference_id}",
    "parties": [
        {"phone": "+254712345678", "role": "seller"},
        {"phone": "+254798765432", "role": "buyer"}
    ]
})

contract_id = contract_response.json()["contract_id"]

# 3. Monitor contract status via WebSocket
import websocket

def on_message(ws, message):
    data = json.loads(message)
    if data["type"] == "contract_confirmed":
        print(f"Contract {data['contract_id']} confirmed by all parties")

ws = websocket.WebSocketApp(f"ws://localhost:8000/contracts/{contract_id}/live")
ws.on_message = on_message
ws.run_forever()
```

### USSD Delivery Confirmation Flow

```
User dials: *483#
┌─────────────────────────────────────────┐
│ Welcome to VoicePact                    │
│ 1. View My Contracts                    │
│ 2. Confirm Delivery                     │
│ 3. Check Payments                       │
│ 4. Report Issue                         │
└─────────────────────────────────────────┘

User selects: 2
┌─────────────────────────────────────────┐
│ Enter Contract ID:                      │
│ VC-MAZ-240815-001                       │
└─────────────────────────────────────────┘

System displays:
┌─────────────────────────────────────────┐
│ Contract: 100 bags Grade A Maize        │
│ Value: KES 320,000                      │
│ Buyer: Grace Wanjiku                    │
│ 1. Confirm Full Delivery                │
│ 2. Partial Delivery                     │
│ 3. Cancel                               │
└─────────────────────────────────────────┘
```

## Deployment

### Production Deployment (Railway)

1. **Connect Repository**
   ```bash
   # Railway CLI deployment
   railway login
   railway link
   railway up
   ```

2. **Environment Setup**
   ```bash
   # Set production environment variables
   railway variables set AT_USERNAME=your_production_username
   railway variables set AT_API_KEY=your_production_api_key
   railway variables set DATABASE_URL=postgresql://user:pass@host:port/db
   ```

3. **Database Migration**
   ```bash
   railway run python migrate.py
   ```

### Frontend Deployment (Vercel)

```bash
cd frontend
vercel --prod
```

## Testing

### Unit Tests

```bash
# Backend tests
cd backend
pytest tests/ -v

# Frontend tests  
cd frontend
npm test
```

### Integration Tests

```bash
# Test Africa's Talking API integration
pytest tests/integration/test_at_apis.py

# Test voice processing pipeline
pytest tests/integration/test_voice_pipeline.py

# Test payment flows
pytest tests/integration/test_payments.py
```

### Load Testing

```bash
# Test concurrent voice processing
python scripts/load_test_voice.py --concurrent=10 --duration=60

# Test SMS delivery performance
python scripts/load_test_sms.py --messages=100
```

## Contributing

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/new-feature`
3. Make changes and add tests
4. Run test suite: `pytest` and `npm test`
5. Submit pull request with detailed description

### Code Style

- **Backend**: Black formatter, isort imports, flake8 linting
- **Frontend**: Prettier formatting, ESLint rules
- **Commit Messages**: Conventional Commits format

### Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
```

## Security

### Security Measures

- **Cryptographic Signatures**: Ed25519 digital signatures for contract integrity
- **Audio Encryption**: Voice recordings encrypted at rest and in transit
- **Access Control**: Phone number-based authentication with OTP verification
- **Audit Logging**: Comprehensive logging of all contract operations
- **Data Protection**: GDPR-compliant data handling and user consent

## Performance

### Benchmarks

- **Voice Processing**: 3-5 seconds for 10-minute audio
- **Contract Generation**: Sub-second term extraction
- **SMS Delivery**: 2-3 seconds average delivery time
- **Payment Processing**: 10-15 seconds for M-Pesa transactions
- **USSD Response**: Sub-2 second menu navigation

### Optimization Features

- **Local AI Models**: No external API dependencies for core processing
- **Redis Caching**: Aggressive caching for frequently accessed data
- **Connection Pooling**: Optimized HTTP client for Africa's Talking APIs
- **Async Processing**: Non-blocking operations for concurrent requests

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

### Community

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Community Q&A and ideas
- **Africa's Talking Community**: Integration support and best practices


---

**Built for Africa's Talking Open Hackathon: Billing & Payment Solutions**

Nairobi, Kenya - August 2025
