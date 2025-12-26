# Design: Hybrid Telephony & AI Platform

## Architecture Overview - Modular Plugin Design

```
┌─────────────────────────────────────────────────────────────────┐
│                         Manager Browser                          │
│                    (SvelteKit Frontend)                          │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTP/SSE
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SvelteKit Server                             │
│                  (API + Redis Client)                            │
└───────────────────────┬─────────────────────────────────────────┘
                        │ Redis Protocol
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Redis (Message Bus)                     │
│    ┌────────────────┬──────────────┬─────────────────┐         │
│    │ call:* (Hash)  │ calls (ZSET) │ cmd:* (List)    │         │
│    │ agent:* (Hash) │ metrics      │ events (Stream) │         │
│    │ plugins:*      │ pub/sub      │ webhook queue   │         │
│    └────────────────┴──────────────┴─────────────────┘         │
└─────┬─────────────────┬──────────────────┬─────────────────────┘
      │                 │                  │
      ▼                 ▼                  ▼
┌──────────┐  ┌──────────────────┐  ┌──────────────────────┐
│ Core     │  │ Plugin Services  │  │ Optional Plugins     │
│ System   │  │ (Microservices)  │  │ (Can enable/disable) │
└──────────┘  └──────────────────┘  └──────────────────────┘
      │                 │                  │
      ▼                 ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              Python Orchestrator (Main Process)                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ESL Event Listener │ Redis Subscriber │ Command Executor │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────────┬─────────────────────────┬───────────────────────────┘
            │ ESL Protocol             │ Task Enqueue
            ▼                          ▼
┌─────────────────────┐    ┌─────────────────────────────────────┐
│   FreeSWITCH        │    │   Core Dramatiq Workers              │
│   (Docker)          │    │  ┌────────────────────────────────┐ │
│                     │    │  │ CRM Lookup │ Basic Sentiment    │ │
│ ┌───────────────┐   │    │  │ Whisper STT│ Call Summary      │ │
│ │ SIP Profiles  │   │    │  │ Smart Route│ Recording         │ │
│ │ Dialplan      │   │    │  └────────────────────────────────┘ │
│ │ Call Parking  │   │    └─────────────────────────────────────┘
│ │ ESL Interface │   │              │
│ └───────────────┘   │              ▼
└─────────────────────┘    ┌─────────────────────────────────────┐
                            │   Plugin Workers (Optional)          │
                            │  ┌────────────────────────────────┐ │
                            │  │ CSAT Service (standalone)      │ │
                            │  │ Quality Mgmt Service           │ │
                            │  │ Advanced RAG (future)          │ │
                            │  └────────────────────────────────┘ │
                            └─────────────────────────────────────┘
```

## Plugin Architecture Benefits

**Modularity:** Each plugin is a separate Docker container that can be:
- Enabled/disabled via environment variables
- Scaled independently
- Developed and tested in isolation
- Updated without touching core system

**Communication:** All plugins communicate via Redis pub/sub:
- Core publishes events: `PUBLISH call_events {call_data}`
- Plugins subscribe to events they care about
- Plugins publish results back to Redis
- No direct dependencies between services

## System Components

### Core vs Plugin Services

**Core Services (Always Running):**
1. FreeSWITCH - Telephony engine
2. Redis - Message bus & state store
3. Python Orchestrator - ESL event handler
4. SvelteKit - Dashboard UI
5. Dramatiq Workers - CRM, basic sentiment, routing

**Plugin Services (Optional, Can Enable/Disable):**
1. **CSAT Survey Service** - Post-call satisfaction surveys
2. **Quality Management Service** - Call scoring, evaluations
3. **Skills Router Plugin** - Advanced skills-based matching
4. **Workforce Management** (Future) - Forecasting, scheduling
5. **Advanced RAG** (Future) - Deep product knowledge integration

**How Plugins Work:**
```yaml
# docker-compose.yml
services:
  # Core (always on)
  freeswitch:
  redis:
  orchestrator:
  dashboard:
  
  # Plugins (enable via env var)
  csat-service:
    image: freecalls/plugin-csat:latest
    environment:
      - ENABLED=${CSAT_ENABLED:-false}  # Default: disabled
    depends_on: [redis]
  
  quality-mgmt:
    image: freecalls/plugin-quality:latest
    environment:
      - ENABLED=${QM_ENABLED:-false}
    depends_on: [redis]
```

**Plugin Communication Pattern:**
```python
# Core system publishes event
redis.publish('call_events', json.dumps({
    'event': 'call_ended',
    'call_uuid': 'abc123',
    'agent_id': 'agent_5',
    'duration': 180
}))

# CSAT plugin subscribes (if enabled)
if CSAT_ENABLED:
    subscriber = redis.pubsub()
    subscriber.subscribe('call_events')
    for message in subscriber.listen():
        if message['event'] == 'call_ended':
            trigger_csat_survey(message['call_uuid'])
```

---

### 1. FreeSWITCH (Telephony Engine)

**Technology:** FreeSWITCH 1.10.x in Docker  
**Responsibilities:**
- SIP registration and call signaling
- RTP media handling (audio/video streams)
- Call parking and retrieval
- DTMF detection
- Call recording to disk

**Design Decisions:**

#### Docker Setup
```yaml
# docker-compose.yml excerpt
freeswitch:
  image: signalwire/freeswitch:latest
  network_mode: host  # Required for RTP media
  volumes:
    - ./freeswitch/conf:/etc/freeswitch
    - ./freeswitch/recordings:/var/lib/freeswitch/recordings
  environment:
    - ESL_PASSWORD=secure_random_password
```

**Rationale:** `network_mode: host` avoids NAT issues with RTP but requires careful port management.

#### Dialplan Strategy
```xml
<!-- conf/dialplan/default.xml -->
<extension name="inbound_call">
  <condition field="destination_number" expression="^(\d{10})$">
    <action application="park"/>
    <action application="set" data="call_uuid=${uuid}"/>
  </condition>
</extension>
```

**Rationale:** Immediate parking allows Python to take control before any routing decisions.

#### ESL Configuration
- Enable ESL on `localhost:8021`
- Authenticate with secure password
- Subscribe to `CHANNEL_PARK`, `CHANNEL_BRIDGE`, `CHANNEL_HANGUP` events

**Trade-offs:**
- ✅ Pro: ESL provides full programmatic control
- ❌ Con: Requires persistent connection management
- **Decision:** Use ESL despite complexity for flexibility

---

### 2. Python Orchestrator (Control Plane)

**Technology:** Python 3.11 + asyncio + ESL client  
**Responsibilities:**
- Maintain persistent ESL connection to FreeSWITCH
- Listen for call events (park, bridge, hangup)
- Update Redis with call state changes
- Consume commands from Redis and execute via ESL
- Enqueue Dramatiq tasks for heavy processing

**Design Decisions:**

#### Event-Driven Architecture
```python
# orchestrator/main.py
async def event_loop():
    esl = ESLClient('localhost', 8021, password)
    await esl.connect()
    await esl.subscribe(['CHANNEL_PARK', 'CHANNEL_BRIDGE', 'CHANNEL_HANGUP'])
    
    async for event in esl.events():
        await handle_event(event)
```

**Rationale:** Async/await maximizes connection utilization without threads.

#### Call State Machine
```python
States = ['parked', 'lookup_pending', 'assigned', 'active', 'completed']

Transitions:
  parked → lookup_pending (CRM task enqueued)
  lookup_pending → assigned (manager assigns agent)
  assigned → active (ESL bridge executed)
  active → completed (hangup event)
```

**Trade-offs:**
- ✅ Pro: Clear state transitions, easy to audit
- ❌ Con: Must handle race conditions (double-assign)
- **Decision:** Use Redis transactions (WATCH/MULTI/EXEC) for atomic state updates

#### Redis State Schema
```python
# Call metadata
HSET call:{uuid} caller_id "5551234567"
HSET call:{uuid} state "parked"
HSET call:{uuid} parked_at 1703548800
HSET call:{uuid} sentiment_score 0.65
HSET call:{uuid} crm_data "{...}"

# Priority queue for UI display
ZADD calls {timestamp} {uuid}

# Command queue
LPUSH cmd:bridge {uuid}:{agent_id}
```

**Rationale:** Hash for structured data, ZSET for ordering, List for FIFO commands.

#### Error Handling Strategy
```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def execute_bridge(call_uuid, agent_extension):
    try:
        await esl.api(f'uuid_bridge {call_uuid} sofia/internal/{agent_extension}')
    except ESLError as e:
        await redis.hset(f'call:{call_uuid}', 'error', str(e))
        await redis.publish('call_errors', json.dumps({...}))
        raise
```

**Rationale:** Exponential backoff for transient failures, publish errors for monitoring.

---

### 3. Dramatiq Workers (Processing Plane)

**Technology:** Dramatiq + Redis broker  
**Responsibilities:**
- CRM lookups (HubSpot API)
- Real-time audio transcription (Whisper API)
- Sentiment analysis (GPT-4o-mini)
- Post-call summarization (LangChain)
- Smart routing decisions (scikit-learn)

**Design Decisions:**

#### Worker Pool Sizing
```python
# dramatiq workers -p 4 -t 8  # 4 processes, 8 threads each
```

**Rationale:** AI calls are I/O-bound (waiting on API), threads > processes.

#### Task Prioritization
```python
@dramatiq.actor(queue_name='critical', priority=10)
def crm_lookup(caller_id):
    # Executed immediately
    pass

@dramatiq.actor(queue_name='background', priority=1)
def post_call_summary(call_uuid):
    # Can wait
    pass
```

**Rationale:** User-facing lookups get priority, analytics can be deferred.

#### Caching Strategy
```python
@cached(ttl=3600, key=lambda caller_id: f'crm:{caller_id}')
def fetch_hubspot_contact(caller_id):
    # Cache for 1 hour
    pass
```

**Rationale:** CRM data changes infrequently, caching reduces API costs 70%+.

#### AI Service Fallbacks
```python
async def get_sentiment(audio_chunk):
    try:
        return await openai.analyze(audio_chunk)
    except OpenAIError:
        logger.warning("OpenAI failed, using TextBlob fallback")
        return textblob_sentiment(await whisper_transcribe(audio_chunk))
```

**Rationale:** Graceful degradation maintains core functionality.

---

### 4. SvelteKit Dashboard (Presentation Layer)

**Technology:** SvelteKit + Redis adapter + Svelte Stores  
**Responsibilities:**
- Display live call list with auto-refresh
- Drag-and-drop call assignment
- Show call metadata (sentiment, CRM data, wait time)
- Write assignment commands to Redis
- Stream real-time updates via SSE

**Design Decisions:**

#### Server-Side Rendering vs. Client-Side
```javascript
// routes/dashboard/+page.server.js
export async function load({ locals }) {
  const calls = await locals.redis.zrange('calls', 0, -1, 'WITHSCORES');
  return { calls };
}
```

**Rationale:** Initial SSR for fast first paint, then client-side SSE for updates.

#### Real-time Updates
```javascript
// lib/stores/calls.js
export const calls = readable([], (set) => {
  const sse = new EventSource('/api/call-events');
  sse.onmessage = (e) => set(JSON.parse(e.data));
  return () => sse.close();
});
```

**Rationale:** SSE is simpler than WebSockets for one-way updates.

#### Drag-and-Drop State Management
```svelte
<script>
  function onDrop(event, agentId) {
    const callUuid = event.dataTransfer.getData('callUuid');
    fetch('/api/assign', {
      method: 'POST',
      body: JSON.stringify({ callUuid, agentId })
    });
  }
</script>

<div on:drop={onDrop} on:dragover={(e) => e.preventDefault()}>
  Agent {agentId}
</div>
```

**Rationale:** Native HTML5 drag-drop, minimal dependencies.

#### Redis Integration
```javascript
// routes/api/assign/+server.js
export async function POST({ request, locals }) {
  const { callUuid, agentId } = await request.json();
  await locals.redis.lpush('cmd:bridge', `${callUuid}:${agentId}`);
  return json({ success: true });
}
```

**Rationale:** SvelteKit server writes commands, Python reads and executes.

---

### 5. Redis (State Layer)

**Technology:** Redis 7.x with persistence  
**Responsibilities:**
- Single source of truth for call state
- Command queue (Python consumes, Svelte produces)
- Event stream for audit log
- Caching layer for CRM data
- Metrics aggregation

**Design Decisions:**

#### Persistence Configuration
```conf
# redis.conf
save 60 1000
appendonly yes
appendfsync everysec
```

**Rationale:** Balance between durability and performance.

#### Data Expiration
```python
await redis.hset(f'call:{uuid}', mapping=call_data)
await redis.expire(f'call:{uuid}', 86400)  # 24 hours
```

**Rationale:** Prevent unbounded growth, retain for debugging.

#### High Availability
```yaml
# Future: Redis Sentinel for automatic failover
sentinel monitor mymaster redis 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 10000
```

**Trade-offs:**
- ✅ Pro: Automatic failover, no manual intervention
- ❌ Con: Adds complexity, requires 3+ nodes
- **Decision:** Start with single instance, add Sentinel in Phase 6

---

## Data Flow Examples

### Scenario 1: Incoming Call → CRM Lookup → Manager Assigns

```
1. Caller dials → FreeSWITCH receives SIP INVITE
2. FreeSWITCH executes dialplan → parks call
3. FreeSWITCH emits CHANNEL_PARK event → ESL
4. Python receives event:
   - Extract call_uuid, caller_id
   - Write to Redis: HSET call:{uuid} state=parked
   - Enqueue Dramatiq: crm_lookup.send(caller_id)
5. Dramatiq worker:
   - Check Redis cache: GET crm:{caller_id}
   - Cache miss → Call HubSpot API
   - Write to Redis: HSET call:{uuid} crm_data={...}
6. SvelteKit SSE pushes update to browser
7. Manager sees call with CRM data, drags to agent
8. SvelteKit writes: LPUSH cmd:bridge {uuid}:{agent_id}
9. Python command loop:
   - BLPOP cmd:bridge → {uuid}:{agent_id}
   - ESL: uuid_bridge {uuid} sofia/internal/{agent_id}
   - Update Redis: HSET call:{uuid} state=active
10. Call connects, FreeSWITCH records audio
```

### Scenario 2: Real-time Sentiment Analysis

```
1. Call is active (bridged state)
2. Python streams audio chunks via ESL:
   - uuid_record {uuid} /tmp/chunk_{n}.wav
3. Every 5 seconds, enqueue: analyze_sentiment.send(chunk_path)
4. Dramatiq worker:
   - Call Whisper API → transcription
   - Call GPT-4o-mini with prompt: "Analyze sentiment: {text}"
   - Parse response → sentiment_score (0.0-1.0)
   - Write to Redis: HSET call:{uuid} sentiment_score={score}
5. SvelteKit SSE updates dashboard with live sentiment gauge
6. If sentiment < 0.3 (frustrated):
   - Python triggers alert: PUBLISH manager_alerts "{...}"
   - Dashboard shows notification
```

---

---

## Enterprise Features (Five9-Inspired)

### 1. Workforce Management

**Purpose:** Forecast staffing needs and optimize agent schedules to meet service level targets.

**Components:**
```
┌─────────────────────────────────────────────────────────────┐
│               Historical Call Data (Redis)                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ ZADD metrics:calls_by_hour {timestamp} {count}       │  │
│  │ HSET metrics:daily:{date} total_calls {n}            │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│          Forecasting Engine (Python + pandas)                │
│  Methods:                                                    │
│  - Moving Average (7-day, 30-day)                           │
│  - Linear Regression                                         │
│  - Seasonal ARIMA                                            │
│  - Day-of-week patterns                                      │
│  - Holiday adjustments                                       │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│         Schedule Optimizer (OR-Tools / PuLP)                 │
│  Constraints:                                                │
│  - Agent availability windows                                │
│  - Max consecutive hours                                     │
│  - Break requirements (15 min every 2 hours)                │
│  - Skill coverage (at least 2 technical agents per shift)   │
│  Objective: Minimize overstaffing while meeting SLA         │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│           Supervisor Dashboard (/dashboard/wfm)              │
│  - Forecasted call volume chart (hourly, next 7 days)       │
│  - Recommended staffing levels                               │
│  - Current vs required agents (real-time gap)                │
│  - Schedule adherence monitoring                             │
│  - Agent schedule editor (drag-and-drop shifts)              │
└─────────────────────────────────────────────────────────────┘
```

**Implementation Details:**
- Store call volume every hour: `ZADD metrics:calls_by_hour {unix_timestamp} {count}`
- Nightly batch job: Run forecasting model, store predictions for next 7 days
- Real-time adherence: Compare scheduled vs actual agent status
- Alerts: If scheduled agents < required, notify supervisor

**Metrics Tracked:**
- Service Level: % calls answered within 20 seconds
- Average Handle Time (AHT)
- Agent occupancy rate: (talk time + wrap-up) / (total logged-in time)
- Schedule adherence: % time agents follow assigned schedule

---

### 2. Quality Management & Coaching

**Purpose:** Monitor agent performance, provide feedback, and ensure compliance with standards.

**Components:**

#### A. Call Recording & Review
```
┌─────────────────────────────────────────────────────────────┐
│              FreeSWITCH (Recording)                          │
│  - Record to: /recordings/{date}/{call_uuid}.wav            │
│  - Stereo: channel 1 = customer, channel 2 = agent          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│           Recording Storage & Indexing                       │
│  Redis Index:                                                │
│  - ZADD recordings:by_date {timestamp} {uuid}               │
│  - HSET recording:{uuid} path agent_id duration tags        │
│  S3/Object Storage (optional): Upload for long-term storage │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│        Review Interface (/dashboard/recordings)              │
│  - Filterable list: date, agent, duration, tags             │
│  - Inline audio player with waveform visualization          │
│  - Playback controls: play/pause, skip, speed (0.5x-2x)     │
│  - Annotation sidebar: timestamp + note                      │
│  - Tagging: training, escalation, compliance, excellent     │
└─────────────────────────────────────────────────────────────┘
```

#### B. Evaluation Scorecards
```
Evaluation Criteria (stored in Redis):
HSET evaluation:criteria greeting weight=10
HSET evaluation:criteria problem_resolution weight=30
HSET evaluation:criteria tone_empathy weight=20
HSET evaluation:criteria product_knowledge weight=25
HSET evaluation:criteria compliance weight=15

Scoring Process:
1. Supervisor selects recording to evaluate
2. Form displays criteria with 1-5 scale
3. Scores stored: HSET call:{uuid}:evaluation {criterion} {score}
4. Total score calculated: weighted average
5. Feedback provided to agent

Agent Performance Report:
- Average score per criterion (last 30 days)
- Trend chart (weekly average)
- Comparison to team average
- Actionable feedback items
```

#### C. Live Monitoring & Whisper Coaching
```
Supervisor Actions (from live call card):

1. MONITOR (Silent Listen):
   - Redis: LPUSH cmd:monitor {call_uuid}:{supervisor_channel}
   - Python Executor: esl.execute('eavesdrop', agent_channel)
   - Supervisor hears both sides, no audio sent

2. WHISPER (Coach Agent):
   - Redis: LPUSH cmd:whisper {call_uuid}:{supervisor_channel}
   - Python Executor: esl.execute('whisper', agent_channel)
   - Supervisor talks to agent only, customer doesn't hear

3. BARGE (Join Call):
   - Redis: LPUSH cmd:barge {call_uuid}:{supervisor_channel}
   - Python Executor: esl.execute('three_way', agent_channel)
   - Supervisor joins as 3-way participant

UI: Supervisor sidebar with "Monitor", "Whisper", "Barge" buttons
```

**Privacy Controls:**
- Recording pause/resume: Supervisor can pause during PII collection
- Automatic redaction: After 30 days, run STT + NER to anonymize transcripts
- Access logs: Track who listened to which recordings

---

### 3. Screen Pops & Agent Desktop

**Purpose:** Present agents with comprehensive customer context the moment a call arrives.

**Screen Pop Components:**
```
┌─────────────────────────────────────────────────────────────┐
│           Agent Desktop (/dashboard/agent)                   │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           Incoming Call Pop-up (Modal)                  │ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │  Customer: John Smith                             │  │ │
│  │  │  Phone: +1 (555) 123-4567                         │  │ │
│  │  │  Company: Acme Corp (VIP)                         │  │ │
│  │  │  ─────────────────────────────────────────────    │  │ │
│  │  │  Recent Activity:                                 │  │ │
│  │  │  ✓ Purchased Pro Plan (7 days ago)               │  │ │
│  │  │  ✉ Ticket #1234: Billing question (resolved)     │  │ │
│  │  │  📞 Last call: 14 days ago (5 min, satisfied)    │  │ │
│  │  │  ─────────────────────────────────────────────    │  │ │
│  │  │  Sentiment: Neutral → Slightly Frustrated        │  │ │
│  │  │  Wait Time: 2m 34s                               │  │ │
│  │  │  ─────────────────────────────────────────────    │  │ │
│  │  │  Suggested Actions:                               │  │ │
│  │  │  • Check recent billing charges                   │  │ │
│  │  │  • Review onboarding progress                     │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  │  [Accept]  [Transfer]  [Send to Voicemail]            │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           Live Call Panel (Active Call)                 │ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │  [Mute] [Hold] [Transfer] [End Call]             │  │ │
│  │  │  Duration: 3:24                                   │  │ │
│  │  │  ─────────────────────────────────────────────    │  │ │
│  │  │  Live Transcript:                                 │  │ │
│  │  │  Customer: "I was charged twice for the same     │  │ │
│  │  │  invoice. Can you help me understand why?"       │  │ │
│  │  │  ─────────────────────────────────────────────    │  │ │
│  │  │  AI Suggestions:                                  │  │ │
│  │  │  💡 Knowledge Base: "Duplicate Charge Policy"    │  │ │
│  │  │  💡 "Refund typically takes 3-5 business days"   │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │         Customer History Tab (CRM Integration)          │ │
│  │  - All past tickets (clickable)                         │ │
│  │  - Order history with amounts                           │ │
│  │  - Notes from previous agents                           │ │
│  │  - Customer lifetime value (CLV)                        │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Data Flow:**
1. Call parks → Python detects `CHANNEL_PARK` event
2. Extract `caller_id` → Dramatiq task: `crm_lookup.send(caller_id)`
3. Fetch from HubSpot:
   - Contact details (name, company)
   - Recent tickets/notes
   - Purchase history
   - Custom fields (VIP status, CLV)
4. Cache in Redis: `HSET call:{uuid}:crm name company tickets orders`
5. Publish to pub/sub: `PUBLISH call_updates {json}`
6. Agent dashboard receives SSE → Shows screen pop

**AI Agent Assist (Live):**
- Whisper STT transcribes call in real-time
- LLM analyzes transcript + CRM context
- Suggests relevant knowledge base articles
- Highlights potential objections/concerns
- Recommends next best actions

---

### 4. Skills-Based Routing

**Purpose:** Match calls to agents based on required skills and agent proficiency.

**Routing Logic:**
```python
# pseudo-code
def route_call(call_uuid, caller_id):
    # 1. Infer call reason from IVR or CRM history
    reason = llm_infer_call_reason(caller_history, ivr_input)
    # Output: "technical_support", "billing", "sales"
    
    # 2. Determine required skills
    required_skills = skill_map[reason]
    # e.g., "technical_support" → {"technical": 3, "product_knowledge": 4}
    
    # 3. Query available agents with matching skills
    agents = redis.smembers('agents:available')
    scored_agents = []
    for agent_id in agents:
        skill_scores = redis.hgetall(f'agent:{agent_id}:skills')
        # skill_scores = {"technical": 4, "billing": 3, "sales": 2}
        
        match_score = calculate_match(required_skills, skill_scores)
        scored_agents.append((agent_id, match_score))
    
    # 4. Sort by score (highest first), then by longest idle time
    sorted_agents = sorted(scored_agents, key=lambda x: (x[1], agent_idle_time(x[0])), reverse=True)
    
    # 5. Assign to best agent
    best_agent = sorted_agents[0][0]
    bridge_call(call_uuid, best_agent)
```

**Skill Management UI:**
- `/dashboard/agents/{agent_id}/skills`
- Add/remove skills: checkboxes
- Set proficiency: slider (1-5)
- Certifications: upload proof documents
- Auto-update based on performance: agents with high QM scores in "technical" auto-boost proficiency

**Continuous Learning:**
- Log routing decisions: `HSET routing:{call_uuid} agent_id reason outcome`
- Track outcomes: resolution (yes/no), customer satisfaction (CSAT), call duration
- Fine-tune routing model monthly:
  - If certain agent always excels with billing issues → boost billing skill
  - If misroutes detected (e.g., technical call sent to sales agent) → adjust weights

---

### 5. Post-Call Surveys (CSAT)

**Purpose:** Collect customer feedback immediately after calls to measure satisfaction.

**Implementation:**

#### IVR Survey Dialplan
```xml
<extension name="post_call_survey">
  <condition field="${survey_enabled}" expression="^true$">
    <action application="play_and_get_digits" 
            data="1 1 3 5000 # /sounds/survey_intro.wav /sounds/invalid.wav survey_score \d"/>
    <action application="log" data="Survey response: ${survey_score}"/>
    <action application="execute_on_answer" data="redis_publish call_survey ${call_uuid}:${survey_score}"/>
  </condition>
</extension>
```

**Survey Message (TTS):**
> "Thank you for calling. On a scale of 1 to 5, with 5 being very satisfied, how satisfied are you with today's service? Press a number now."

**Data Storage:**
```python
# On DTMF input
survey_score = event['survey_score']  # 1-5
redis.hset(f'call:{call_uuid}', 'csat_score', survey_score)
redis.zadd('metrics:csat_by_date', {call_uuid: time.time()})

# Agent linkage
agent_id = redis.hget(f'call:{call_uuid}', 'agent_id')
redis.lpush(f'agent:{agent_id}:csat_scores', survey_score)
```

**Analytics Dashboard:**
```
┌─────────────────────────────────────────────────────────────┐
│           CSAT Analytics (/dashboard/analytics/csat)         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Overall CSAT: 4.2 / 5.0 (↑ 0.1 vs last week)       │  │
│  │  Response Rate: 68%                                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  CSAT Trend (Last 30 Days)                           │  │
│  │   5.0  ╭─╮                                           │  │
│  │   4.5  │ ╰╮  ╭╮╭─╮                                  │  │
│  │   4.0  │  ╰──╯╰╯ ╰╮                                 │  │
│  │   3.5  │          ╰──                               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  CSAT by Agent (Top 5)                               │  │
│  │  1. Alice Johnson    4.8 (42 surveys)               │  │
│  │  2. Bob Martinez     4.6 (38 surveys)               │  │
│  │  3. Carol Lee        4.5 (51 surveys)               │  │
│  │  4. David Chen       4.3 (29 surveys)               │  │
│  │  5. Emma Wilson      4.2 (45 surveys)               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Alert: Agent "David Chen" CSAT dropped to 3.9 this week   │
│  Action: Schedule coaching session                          │
└─────────────────────────────────────────────────────────────┘
```

**Automated Actions:**
- CSAT < 3: Flag for supervisor review, add to coaching queue
- CSAT = 5: Add to "excellent calls" playlist for training
- CSAT trend down: Alert supervisor, investigate root cause (staffing? system issues?)

---

### 6. Callback Queue Management

**Purpose:** Allow customers to request callbacks instead of waiting on hold, improving satisfaction and reducing abandonment.

**User Flow:**
```
1. Customer calls → IVR detects high queue depth (>5 calls waiting)
2. IVR offers: "Press 1 to request a callback when an agent is available"
3. Customer presses 1 → IVR collects preferred time (now, specific time)
4. System stores callback request with priority
5. When agent becomes available → System originates call to customer
6. After customer answers → Bridge to agent
```

**Implementation:**

#### Data Structure
```python
# Callback request storage (Redis Sorted Set, score = timestamp)
callback_data = {
    'caller_id': '+15551234567',
    'caller_name': 'John Smith',
    'reason': 'billing_inquiry',
    'preferred_time': 1234567890,  # Unix timestamp
    'priority': 'standard',  # or 'vip', 'urgent'
    'attempts': 0,
    'max_attempts': 3
}
redis.zadd('callbacks:scheduled', {json.dumps(callback_data): preferred_time})
```

#### Callback Worker (Dramatiq)
```python
@dramatiq.actor
def process_callbacks():
    while True:
        now = time.time()
        # Get due callbacks
        callbacks = redis.zrangebyscore('callbacks:scheduled', 0, now, start=0, num=10)
        
        for callback_json in callbacks:
            callback = json.loads(callback_json)
            
            # Check available agents
            available = redis.smembers('agents:available')
            if not available:
                continue  # Try again in next cycle
            
            # Originate call to customer
            customer_channel = freeswitch_originate(callback['caller_id'])
            
            if customer_channel:
                # Bridge to agent
                agent_id = list(available)[0]
                bridge_command(customer_channel, agent_id)
                
                # Remove from queue
                redis.zrem('callbacks:scheduled', callback_json)
            else:
                # Failed to reach customer, increment attempts
                callback['attempts'] += 1
                if callback['attempts'] >= callback['max_attempts']:
                    redis.zrem('callbacks:scheduled', callback_json)
                    # Log failed callback
                else:
                    # Reschedule for 5 min later
                    new_time = now + 300
                    redis.zadd('callbacks:scheduled', {json.dumps(callback): new_time})
        
        time.sleep(60)  # Check every minute
```

#### UI Components
```
Manager Dashboard - Callbacks Tab (/dashboard/callbacks)

┌─────────────────────────────────────────────────────────────┐
│  📋 Scheduled Callbacks (12)                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  John Smith  +1555-123-4567  Billing  Today 2:30 PM │  │
│  │  [Call Now]  [Reschedule]  [Cancel]                  │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │  Jane Doe    +1555-987-6543  Technical  Today 3:00 PM│ │
│  │  [Call Now]  [Reschedule]  [Cancel]                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  🔄 In Progress (2)                                         │
│  ✅ Completed Today (8)                                     │
│  ❌ Failed (no answer) (1)                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Security Considerations

1. **ESL Password:** Stored in environment variable, never committed
2. **Redis:** Bind to localhost only, no public exposure
3. **API Keys:** Use secrets manager (AWS SSM, Vault) in production
4. **SIP Security:** Fail2ban for brute-force protection
5. **Data Retention:** Automatically purge PII after 30 days (GDPR)

---

## Scalability Path

### Current (Phase 1-5): Single Server
- 1 FreeSWITCH instance
- 1 Python orchestrator process
- 1 Redis instance
- 4 Dramatiq worker processes
- **Capacity:** ~100 concurrent calls

### Future (Phase 6+): Distributed
- N FreeSWITCH instances behind SIP proxy (Kamailio)
- M Python orchestrators (leader election via Redis)
- Redis Cluster (sharding by call_uuid)
- Auto-scaling Dramatiq workers (Kubernetes HPA)
- **Capacity:** 1000+ concurrent calls

---

## Testing Strategy

1. **Unit Tests:** Mock ESL, Redis, external APIs
2. **Integration Tests:** Docker Compose with test fixtures
3. **Load Tests:** SIPp for call simulation
4. **E2E Tests:** Playwright for dashboard interactions
5. **Chaos Tests:** Randomly kill services, verify recovery

---

## Monitoring & Observability

```python
# Metrics (Prometheus)
calls_parked_total.inc()
call_duration_seconds.observe(duration)

# Logging (structured JSON)
logger.info('call_bridged', extra={'call_uuid': uuid, 'agent_id': agent})

# Tracing (OpenTelemetry)
with tracer.start_span('crm_lookup'):
    fetch_hubspot_contact(caller_id)
```

**Dashboards:**
- Call volume over time
- Average wait time
- CRM cache hit rate
- AI service latency (p50, p95, p99)
- Error rates by component

---

## Open Questions & Future Enhancements

1. **Multi-tenancy:** Should we support multiple organizations?
2. **Agent Status:** Real-time presence (available, busy, offline)?
3. **Call Queuing:** FIFO, priority, skill-based routing?
4. **Video Calls:** FreeSWITCH supports it, but UI needs work
5. **Mobile App:** React Native dashboard for on-the-go management?

---

**This design will be refined during implementation based on real-world feedback.**
