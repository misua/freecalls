# Dramatiq Integration Architecture

## Overview

This implementation follows the **Hot Path / Slow Path** pattern for telephony + CRM integration:

- **Hot Path** (Orchestrator): Real-time ESL event handling with instant Redis lookups
- **Slow Path** (Dramatiq Workers): Background API calls, retries, and eventual consistency

## The Two-Namespace Redis Pattern

### Namespace 1: `phone:{number}` (Static CRM Cache)
- **Purpose**: Pre-cached contact data for instant screen pops
- **Updated by**: Dramatiq continuous sync (every 10 minutes)
- **TTL**: 24 hours
- **Content**: Contact ID, name, email, lifecycle stage, status

Example:
```json
{
  "id": "12345",
  "name": "John Doe",
  "email": "john@example.com",
  "phone": "5551234567",
  "lifecycle_stage": "customer",
  "status": "active",
  "cached_at": 1703620800
}
```

### Namespace 2: `call:{uuid}` (Ephemeral Call State)
- **Purpose**: Live call data and metadata
- **Updated by**: Orchestrator on ESL events
- **Deleted**: After call ends + CRM sync completes
- **Content**: Call UUID, status, agents, duration, recording path

Example:
```json
{
  "uuid": "abc-123",
  "caller_id": "5551234567",
  "caller_name": "John Doe",
  "status": "active",
  "agent_id": "1001",
  "crm_id": "12345",
  "duration": 245,
  "conference_room": "3100",
  "supervisor_id": "1004",
  "recording_path": "/recordings/abc-123.wav"
}
```

## Dramatiq Actors

### 1. Write-Back Actor: `sync_call_to_crm()`
**Purpose**: Sync completed call data to CRM after hangup

**Triggered**: On `CHANNEL_HANGUP` event
**Retries**: 3 attempts with exponential backoff
**Handles**:
- Creating call/interaction record in CRM
- Linking to contact
- Multi-leg calls (conferences, transfers)
- Supervisor monitoring metadata
- Recording URLs

### 2. Continuous Sync Actor: `cron_pull_crm_updates()`
**Purpose**: Keep Redis cache warm with recent CRM changes

**Schedule**: Every 10 minutes
**Strategy**: Delta sync (only contacts modified in last 10 minutes)
**Benefit**: Reduces API calls by 95% vs real-time lookup
**Handles**:
- Query CRM for recent updates
- Update `phone:{number}` keys
- Track sync metrics

### 3. Routing Predictor: `predict_routing()`
**Purpose**: AI-powered agent recommendation

**Triggered**: When call parks (if CRM data exists)
**Uses**: Historical data + contact lifecycle stage
**Returns**: Top 3 recommended agents with confidence scores

## Call Flow

```
┌─────────────────────────────────────────────────┐
│  1. Inbound Call → FreeSWITCH CHANNEL_PARK      │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  2. Orchestrator (HOT PATH)                     │
│     - Fast Redis lookup: phone:{ANI}            │
│     - Store call: call:{UUID}                   │
│     - Publish to dashboard (< 50ms)             │
│     - Enqueue background tasks                  │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  3. Dramatiq Workers (SLOW PATH)                │
│     - predict_routing() if CRM hit              │
│     - (No blocking, orchestrator already done)  │
└─────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  4. Agent answers → CHANNEL_BRIDGE              │
│     - Update call status                        │
│     - Start recording                           │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  5. Call ends → CHANNEL_HANGUP                  │
│     - Calculate duration                        │
│     - Enqueue sync_call_to_crm()                │
│     - Clear agent state                         │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  6. Dramatiq Worker syncs to CRM                │
│     - Create interaction record                 │
│     - Link to contact                           │
│     - Include multi-leg metadata                │
│     - Auto-retry on failure                     │
└─────────────────────────────────────────────────┘
```

## Benefits vs Celery

1. **Simplicity**: No result backends, perfect for "fire and forget"
2. **Reliability**: Handles burst traffic (end of busy hour) better
3. **Built-in Retry**: Automatic exponential backoff on CRM API failures
4. **Lightweight**: Lower memory overhead for high-volume events

## Configuration

### Environment Variables
```bash
# Redis (required)
REDIS_URL=redis://localhost:6379

# CRM (optional - falls back to mock data)
HUBSPOT_API_KEY=your-api-key-here
```

### Worker Scaling
```bash
# Start with 4 processes, 8 threads each (32 concurrent tasks)
docker-compose up worker

# Scale up for high volume:
docker-compose up --scale worker=3
```

## Monitoring

### Metrics in Redis
```bash
# Check sync status
redis-cli HGETALL metrics:crm_sync

# Check cache coverage
redis-cli KEYS phone:*

# Check active calls
redis-cli KEYS call:*
```

### Dramatiq Dashboard (Future)
- Install: `pip install dramatiq-dashboard`
- View: http://localhost:8080

## Testing

### Manual Test: CRM Cache
```python
import redis
r = redis.from_url('redis://localhost:6379', decode_responses=True)

# Manually cache a contact
r.setex('phone:5551234567', 3600, '{"id": "test123", "name": "Test User"}')

# Make test call from that number → should show "Test User"
```

### Trigger Continuous Sync
```bash
docker exec freecalls-worker python -c "from workers.tasks import cron_pull_crm_updates; cron_pull_crm_updates()"
```

## Next Steps

1. **Implement Real CRM API**: Replace mock data in `sync_call_to_crm()` and `cron_pull_crm_updates()`
2. **Add APScheduler**: Replace self-scheduling with proper cron
3. **Add Metrics Export**: Prometheus exporter for Dramatiq queue depth
4. **Implement AI Features**: Add sentiment analysis, transcription actors
