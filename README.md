# FreeCalls - Cloud Contact Center Platform

Modern, scalable contact center platform built with FreeSWITCH, Redis, TimescaleDB, and SvelteKit. Features real-time call analytics, conference calling, supervisor monitoring, and async background processing.

## Features

- 🎯 **Real-time Call Orchestration** - FreeSWITCH ESL integration with drag-and-drop call assignment
- 📊 **Analytics Dashboard** - Live metrics, call volumes, agent performance tracking
- 👥 **Conference Calling** - Multi-party conferences with supervisor eavesdrop/whisper
- 🔄 **Background Workers** - Dramatiq-based async processing for analytics and CRM sync
- 💾 **State Management** - Redis-based ephemeral state with automatic TTL cleanup
- 📈 **Time-Series Analytics** - TimescaleDB for historical call data and reporting
- 🎨 **Modern UI** - SvelteKit dashboard with real-time updates

## Architecture

```
┌─────────────────┐
│ SvelteKit UI    │ ← Real-time dashboard with analytics
└────────┬────────┘
         │ HTTP/REST
┌────────▼────────┐
│ Redis           │ ← Call state, agent status (5min TTL)
└────────┬────────┘
         │
┌────────▼────────┐     ┌──────────────┐
│ Python          │◄────┤ FreeSWITCH   │ SIP/RTP telephony
│ Orchestrator    │ ESL │              │
└────────┬────────┘     └──────────────┘
         │
         ├─► Dramatiq Workers (async)
         │   └─► TimescaleDB (analytics)
         │   └─► CRM Sync
         │
         └─► TimescaleDB (hypertables)
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- SIP phone or softphone (Zoiper, Linphone, etc.)
- 4GB RAM minimum

### Setup

1. **Clone and start:**
```bash
git clone https://github.com/misua/freecalls.git
cd freecalls
docker-compose up -d
```

2. **Register SIP extensions:**
- Server: `localhost:5060`
- Extensions: `1000-1004` (agents), `1005-1010` (customers)
- Password: `1234`

3. **Access dashboard:**
```bash
open http://localhost:3000
```

4. **Make test calls:**
- Call `5000` from any extension to enter queue
- Drag & drop call cards to agent cards to assign
- Add third party to conference with agent

## Features Walkthrough

### Call Management
- **Incoming calls** appear as draggable cards
- **Drag to agent** to assign call
- **Conference button** to add third party
- **Eavesdrop** for supervisors to listen in

### Analytics Dashboard
Navigate to `/dashboard/analytics` to see:
- **Summary metrics**: Total calls, avg duration, wait time, abandon rate
- **Volume charts**: Calls over time by hour/day
- **Agent performance**: Top agents by call volume
- **Recent calls**: Last 20 calls with full metadata

### Conference Calling
1. Agent answers call
2. Click "Conference" button
3. Select target agent/extension
4. All parties joined in conference room
5. Supervisor can eavesdrop from dashboard

## Project Structure

```
freecalls/
├── docker-compose.yml          # Container orchestration
├── freeswitch/
│   └── conf/                   # FreeSWITCH config (SIP, dialplan, conferences)
├── python/
│   ├── orchestrator/
│   │   ├── main.py            # ESL event handler & call orchestration
│   │   └── db.py              # TimescaleDB connection pool
│   └── workers/
│       └── tasks.py           # Dramatiq actors (analytics, CRM sync)
├── sveltekit/
│   └── src/
│       ├── routes/
│       │   ├── +page.svelte               # Main dashboard
│       │   └── dashboard/analytics/       # Analytics page
│       └── lib/components/                # Call/Agent cards, charts
└── docker/
    └── timescaledb/init.sql   # Database schema with hypertables
```

## Configuration

### Environment Variables
```bash
# FreeSWITCH
FREESWITCH_HOST=localhost
ESL_PASSWORD=ClueCon

# Redis
REDIS_URL=redis://localhost:6379

# TimescaleDB
DATABASE_URL=postgresql://freecalls:freecalls_secure_password@localhost:5432/freecalls

# CRM Integration (optional)
HUBSPOT_API_KEY=your_key_here
```

### SIP Extensions
- **1000-1004**: Agent extensions
- **1005-1010**: Customer/test extensions
- **5000**: Queue entry point

## API Endpoints

### Call Control
- `POST /api/assign` - Assign call to agent
- `POST /api/call-control` - Hold/unhold/hangup
- `POST /api/eavesdrop` - Supervisor listen/whisper
- `GET /api/call-events` - SSE stream of call events

### Analytics
- `GET /api/analytics/summary` - Overall metrics
- `GET /api/analytics/volume` - Call volume over time
- `GET /api/analytics/agents` - Agent performance
- `GET /api/analytics/recent` - Recent calls list

## Technology Stack

- **Telephony**: FreeSWITCH 1.10+ (SIP, RTP, ESL)
- **Backend**: Python 3.11+ with FreeSWITCH ESL, Dramatiq
- **State**: Redis 7 (ephemeral state with TTL)
- **Database**: TimescaleDB (PostgreSQL 16 + timescaledb extension)
- **Frontend**: SvelteKit 2 + TailwindCSS
- **Infrastructure**: Docker Compose

## Development

### Running in Dev Mode

```bash
# Start infrastructure only
docker-compose up -d freeswitch redis timescaledb

# Run orchestrator locally
cd python
pip install -r requirements.txt
python orchestrator/main.py

# Run workers locally
dramatiq workers.tasks --processes 2

# Run SvelteKit dev server
cd sveltekit
npm install
npm run dev
```

### Database Schema

TimescaleDB with hypertable on `calls` table:
- Partitioned by `ended_at` timestamp
- Composite primary key: `(call_uuid, ended_at)`
- Tracks: duration, wait_time, status, agent, conference participants, supervisor

### Background Workers

Dramatiq actors in `workers/tasks.py`:
- `store_call_analytics` - Persist call data to TimescaleDB
- `sync_call_to_crm` - Push call events to external CRM

## Monitoring

```bash
# View orchestrator logs
docker logs -f freecalls-orchestrator

# View worker logs
docker logs -f freecalls-worker

# View dashboard logs
docker logs -f freecalls-dashboard

# Check Redis state
docker exec -it freecalls-redis redis-cli
> KEYS call:*
> HGETALL call:<uuid>

# Query analytics
docker exec -it freecalls-timescaledb psql -U freecalls -d freecalls
> SELECT * FROM calls ORDER BY ended_at DESC LIMIT 10;
```

## License

MIT
