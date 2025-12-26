# Hybrid Telephony & AI Platform

Enterprise contact center platform with AI-powered call routing and local LLM integration.

## Architecture

```
Manager Browser (SvelteKit) 
    ↓ HTTP/SSE
Redis (State & Message Bus)
    ↓
Python Orchestrator ← ESL → FreeSWITCH (Telephony)
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- SIP phone or softphone (Zoiper, Linphone, etc.)

### Setup

1. **Clone and configure:**
```bash
cp .env.example .env
# Edit .env and set ESL_PASSWORD
```

2. **Start services:**
```bash
docker-compose up -d
```

3. **Register SIP phone:**
- Server: `localhost:5060`
- Username: `1000` (or any extension 1000-1019)
- Password: `1234`

4. **Test call parking:**
- Call extension `5000` from your SIP phone
- Call should park with music on hold

5. **Open dashboard:**
```bash
open http://localhost:3000
```

## Project Structure

```
freecalls/
├── docker-compose.yml       # Multi-container orchestration
├── freeswitch/
│   ├── conf/                # FreeSWITCH configuration
│   │   ├── dialplan/        # Call routing rules
│   │   ├── sip_profiles/    # SIP settings
│   │   └── autoload_configs/
│   └── recordings/          # Call recordings (gitignored)
├── python/
│   └── orchestrator/        # ESL event listener & command executor
├── sveltekit/               # Dashboard UI
└── redis-data/              # Redis persistence (gitignored)
```

## Implementation Status

- [x] Phase 1: Foundation & FreeSWITCH Setup
- [ ] Phase 2: Command Executor
- [ ] Phase 3: Dashboard UI
- [ ] Phase 4: Drag-and-Drop Assignment
- [ ] Phase 5: AI Intelligence
- [ ] Phase 6: Production Hardening

## Development

See [OpenSpec proposal](./openspec/changes/implement-hybrid-telephony-ai-platform/) for full implementation plan.

## License

MIT
