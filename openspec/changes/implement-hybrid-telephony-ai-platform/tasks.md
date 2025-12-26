# Implementation Tasks: Hybrid Telephony & AI Platform

**Change ID:** `implement-hybrid-telephony-ai-platform`

This document breaks down the implementation into ordered, verifiable tasks. Complete each task sequentially, checking off items as they're done. Each task should result in user-visible progress or verified functionality.

---

## Phase 1: Foundation & FreeSWITCH Setup

### Task 1.1: Project Structure Setup
- [ ] Create root directory structure: `docker/`, `freeswitch/`, `python/`, `sveltekit/`
- [ ] Initialize Git repository with `.gitignore` (ignore recordings, logs, `.env`)
- [ ] Create `docker-compose.yml` at project root
- [ ] Add `README.md` with architecture diagram and setup instructions
- [ ] Create `.env.example` with required environment variables

**Validation:** `ls -la` shows directory structure, `git status` confirms repository initialized.

---

### Task 1.2: FreeSWITCH Docker Configuration
- [ ] Create `docker/freeswitch/Dockerfile` based on `signalwire/freeswitch:latest`
- [ ] Configure `docker-compose.yml` with freeswitch service:
  - Use `network_mode: host`
  - Mount `./freeswitch/conf:/etc/freeswitch`
  - Mount `./freeswitch/recordings:/var/lib/freeswitch/recordings`
  - Set environment variable `ESL_PASSWORD`
- [ ] Create `freeswitch/conf/autoload_configs/event_socket.conf.xml` enabling ESL on port 8021
- [ ] Create `freeswitch/conf/sip_profiles/internal.xml` for agent registrations
- [ ] Create `freeswitch/conf/dialplan/default.xml` with basic park extension

**Validation:** `docker-compose up freeswitch` starts successfully, ESL accessible on port 8021.

---

### Task 1.3: FreeSWITCH Dialplan for Call Parking
- [ ] Define inbound extension matching pattern `^\d{10}$` (10-digit numbers)
- [ ] Add `park()` application as first action
- [ ] Set channel variables: `call_uuid=${uuid}`, `effective_caller_id_number=${caller_id_number}`
- [ ] Configure hold music: `local_stream://moh` (music on hold)
- [ ] Test dialplan syntax: `docker exec freeswitch fs_cli -x "reloadxml"`

**Validation:** Call from SIP client parks successfully, hear hold music, FreeSWITCH logs show `CHANNEL_PARK` event.

---

### Task 1.4: Redis Docker Setup
- [ ] Add `redis` service to `docker-compose.yml`:
  - Use `redis:7-alpine` image
  - Expose port 6379 on localhost only
  - Mount volume for persistence: `./redis-data:/data`
- [ ] Create `docker/redis/redis.conf` with settings:
  - `save 60 1000` (snapshot every 60s if 1000+ writes)
  - `appendonly yes` (AOF enabled)
  - `appendfsync everysec` (fsync every second)
  - `maxmemory 2gb`
  - `maxmemory-policy volatile-lru`
- [ ] Mount config: `./docker/redis/redis.conf:/usr/local/etc/redis/redis.conf`

**Validation:** `docker-compose up redis`, connect with `redis-cli ping` returns `PONG`.

---

### Task 1.5: Python Environment Setup
- [ ] Create `python/requirements.txt` with dependencies:
  - `redis>=5.0.0`
  - `dramatiq[redis]>=1.15.0`
  - `python-esl>=0.1.0` (or appropriate ESL client library)
  - `asyncio`
  - `python-dotenv`
- [ ] Create `python/Dockerfile`:
  - Base: `python:3.11-slim`
  - Install system dependencies if needed
  - Copy requirements and install packages
- [ ] Create `python/.env.example` with: `REDIS_URL`, `FREESWITCH_HOST`, `FREESWITCH_ESL_PASSWORD`
- [ ] Add Python service to `docker-compose.yml` with `depends_on: [redis, freeswitch]`

**Validation:** `docker-compose build python` succeeds, container starts without errors.

---

### Task 1.6: Basic ESL Connection from Python
- [ ] Create `python/orchestrator/esl_client.py` with `ESLClient` class
- [ ] Implement `connect()` method: connect to `localhost:8021` with password
- [ ] Implement `subscribe(events)` method: subscribe to `CHANNEL_PARK`, `CHANNEL_BRIDGE`, `CHANNEL_HANGUP`
- [ ] Implement `event_loop()` async generator yielding events
- [ ] Create `python/orchestrator/main.py` entry point:
  - Load environment variables
  - Initialize ESL client
  - Log each event received
- [ ] Test: Park a call, confirm Python logs show `CHANNEL_PARK` event with call_uuid

**Validation:** Python logs display: `Received CHANNEL_PARK: uuid=abc-123, caller_id=5551234567`

---

### Task 1.7: Redis State Management - Call Creation
- [ ] Create `python/orchestrator/redis_client.py` with `RedisClient` class wrapping redis-py
- [ ] Implement `create_call(call_uuid, caller_id, caller_name)` method:
  - `HSET call:{uuid} state parked caller_id {id} caller_name {name} parked_at {timestamp}`
  - `ZADD calls {timestamp} {uuid}`
  - `EXPIRE call:{uuid} 86400`
- [ ] In `main.py`, on `CHANNEL_PARK` event, call `redis_client.create_call()`
- [ ] Test: Park call, verify with `redis-cli HGETALL call:{uuid}` shows correct data

**Validation:** Redis contains call data, `ZRANGE calls 0 -1` shows call_uuid.

---

### Task 1.8: End-to-End Phase 1 Test
- [ ] Start all services: `docker-compose up -d`
- [ ] Register SIP softphone to FreeSWITCH internal profile
- [ ] Make test call to trigger park
- [ ] Verify FreeSWITCH parks call (hold music plays)
- [ ] Verify Python logs show event received
- [ ] Verify Redis contains call state: `redis-cli HGETALL call:{uuid}`
- [ ] Document any issues encountered and resolutions in `docs/setup.md`

**Validation:** All services running, call parks, state appears in Redis within 2 seconds.

---

## Phase 2: Python Orchestrator & AI Trigger

### Task 2.1: Dramatiq Worker Setup
- [ ] Add to `requirements.txt`: `dramatiq[redis]`, `hubspot-api-client`, `openai`, `requests`
- [ ] Create `python/workers/__init__.py` with Dramatiq broker configuration:
  - Redis broker: `RedisBroker(url=REDIS_URL)`
- [ ] Create `python/workers/tasks.py` with stub tasks:
  - `@dramatiq.actor def crm_lookup(caller_id): pass`
  - `@dramatiq.actor def analyze_sentiment(call_uuid, audio_chunk): pass`
  - `@dramatiq.actor def generate_summary(call_uuid): pass`
- [ ] Add worker command to `docker-compose.yml`: `command: dramatiq python.workers.tasks -p 4 -t 8`

**Validation:** `docker-compose logs worker` shows: "Dramatiq worker started with 4 processes, 8 threads each"

---

### Task 2.2: CRM Lookup Task Implementation
- [ ] Implement `crm_lookup(caller_id)` in `workers/tasks.py`:
  - Check cache: `redis.get(f'crm:{caller_id}')`
  - If miss, call HubSpot API: `hubspot.crm.contacts.basic_api.get_by_id(caller_id)`
  - Store in cache: `redis.setex(f'crm:{caller_id}', 3600, json.dumps(data))`
  - Return contact data
- [ ] Add error handling:
  - Retry on transient errors (3 attempts, exponential backoff)
  - On failure, return `{status: 'unavailable'}`
- [ ] Update `main.py` to enqueue task on `CHANNEL_PARK`: `crm_lookup.send(caller_id)`

**Validation:** Mock HubSpot call, verify cache hit on second call, check `redis-cli GET crm:{number}`.

---

### Task 2.3: Call State Machine Implementation
- [ ] Create `python/orchestrator/state_machine.py` with states: `parked`, `lookup_pending`, `assigned`, `active`, `completed`
- [ ] Implement `transition(call_uuid, from_state, to_state)` method:
  - Use Redis transaction (WATCH/MULTI/EXEC) for atomic updates
  - Publish state change: `redis.publish('call_updates', json.dumps({...}))`
- [ ] Update `main.py`:
  - On park: transition to `lookup_pending`, enqueue CRM task
  - On CRM complete: transition to `parked` (ready for assignment)
- [ ] Add logging for all state transitions

**Validation:** State transitions logged correctly, Redis `call:{uuid}.state` updates atomically.

---

### Task 2.4: Audio Streaming for Sentiment Analysis (Stub)
- [ ] Create `python/orchestrator/audio_streamer.py` with `stream_audio(call_uuid)` function
- [ ] On `CHANNEL_BRIDGE` event, start background task to record 5-second chunks
- [ ] Use ESL command: `uuid_record {uuid} /tmp/chunk_{timestamp}.wav 5`
- [ ] Every 5 seconds, enqueue: `analyze_sentiment.send(call_uuid, chunk_path)`
- [ ] For now, sentiment task just logs receipt (real AI integration in Phase 5)

**Validation:** Python logs show: "Recording chunk 1 for call abc-123", "Enqueued sentiment task"

---

### Task 2.5: Redis Command Queue Consumer
- [ ] Create `python/orchestrator/command_executor.py` with `consume_commands()` async function
- [ ] Implement blocking pop: `command = redis.brpop('cmd:bridge', timeout=1)`
- [ ] Parse command: `call_uuid, agent_id = command.split(':')`
- [ ] Execute via ESL: `esl.api(f'uuid_bridge {call_uuid} sofia/internal/{agent_id}')`
- [ ] Publish result: `redis.publish(f'cmd:result:{call_uuid}', json.dumps({success: True}))`
- [ ] Run consumer in separate asyncio task in `main.py`

**Validation:** Manually `LPUSH cmd:bridge "test-uuid:1001"`, Python logs: "Executing bridge for test-uuid to 1001"

---

### Task 2.6: Call Recording on Bridge
- [ ] Update `CHANNEL_BRIDGE` event handler in `main.py`:
  - Extract call_uuid and agent_id from event
  - Generate recording path: `/recordings/{uuid}_{timestamp}.wav`
  - Execute: `esl.api(f'uuid_record {uuid} {recording_path}')`
  - Store path: `redis.hset(f'call:{uuid}', 'recording_path', recording_path)`
- [ ] On `CHANNEL_HANGUP`, log recording finalized

**Validation:** After bridged call ends, recording file exists at expected path, playable audio.

---

### Task 2.7: Error Handling and Reconnection Logic
- [ ] Implement ESL reconnection in `esl_client.py`:
  - Detect connection loss (timeout or exception)
  - Retry with exponential backoff: 1s, 2s, 4s, 8s, max 30s
  - Log all reconnection attempts
- [ ] Add health check endpoint in Python (future HTTP server): `/health` returns ESL and Redis status
- [ ] Add graceful shutdown handler: close ESL, drain command queue, stop worker

**Validation:** Kill FreeSWITCH, Python logs reconnection attempts, successfully reconnects when FreeSWITCH restarts.

---

### Task 2.8: End-to-End Phase 2 Test
- [ ] Start all services including Dramatiq worker
- [ ] Park call → verify CRM lookup task executes
- [ ] Manually enqueue bridge command: `redis-cli LPUSH cmd:bridge "uuid:1001"`
- [ ] Verify call bridges to agent extension 1001
- [ ] Verify recording starts and file is created
- [ ] Check Redis for complete call record with CRM data

**Validation:** Call lifecycle from park → CRM lookup → manual bridge → recording works end-to-end.

---

## Phase 3: SvelteKit Real-time Dashboard

### Task 3.1: SvelteKit Project Initialization
- [ ] Run `npm create svelte@latest sveltekit` with options: skeleton, TypeScript, ESLint, Prettier
- [ ] Install dependencies: `npm install ioredis`
- [ ] Create `sveltekit/.env` with `REDIS_URL=redis://localhost:6379`
- [ ] Create `src/lib/server/redis.ts` exporting Redis client singleton
- [ ] Test Redis connection in `src/routes/+layout.server.ts`

**Validation:** `npm run dev` starts SvelteKit, accessing any route doesn't crash, Redis client connects.

---

### Task 3.2: Call List Page with SSR
- [ ] Create `src/routes/dashboard/+page.server.ts`:
  - `load()` function queries Redis: `ZRANGE calls 0 -1 WITHSCORES`
  - For each uuid, `HGETALL call:{uuid}`
  - Return `{ calls: [...] }`
- [ ] Create `src/routes/dashboard/+page.svelte`:
  - Display list of calls with caller_id, caller_name, wait_time
  - Use `{#each calls as call}` loop
  - Style with basic CSS (or Tailwind if preferred)

**Validation:** Navigate to `/dashboard`, see list of parked calls from Redis.

---

### Task 3.3: Server-Sent Events for Real-time Updates
- [ ] Create `src/routes/api/call-events/+server.ts`:
  - Return `Response` with headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`
  - Subscribe to Redis: `subscriber.subscribe('call_updates')`
  - On message, write SSE format: `data: {json}\n\n`
- [ ] Create `src/lib/stores/calls.ts`:
  - `readable` store that opens EventSource to `/api/call-events`
  - Update store on each SSE message
- [ ] Update `+page.svelte` to use reactive store instead of static load data

**Validation:** Open dashboard, park call from FreeSWITCH, call appears in UI without refresh.

---

### Task 3.4: Drag-and-Drop UI Implementation (Five9-Inspired)
- [ ] Create `src/lib/components/CallCard.svelte`:
  - Render call info with `draggable="true"`
  - On `dragstart`, set `event.dataTransfer.setData('callUuid', call.uuid)`
  - Apply drag styles (opacity, cursor)
  - Show screen pop preview on hover with CRM data
- [ ] Create `src/lib/components/AgentCard.svelte`:
  - Render agent info with drop zone
  - On `dragover`, prevent default and highlight
  - On `drop`, extract `callUuid`, call assignment API
  - Show agent skills badges (technical, billing, sales)
  - Display current AHT (Average Handle Time) metric
- [ ] Create `src/routes/dashboard/agents/+page.server.ts`:
  - Load agent list from Redis: `SMEMBERS agents:available`, `HGETALL agent:{id}`
  - Load agent skills and performance metrics

**Validation:** Drag call card to agent card, visual feedback shows drop target, skills visible.

---

### Task 3.5: Call Assignment API Endpoint
- [ ] Create `src/routes/api/assign/+server.ts`:
  - Parse POST body: `{callUuid, agentId}`
  - Validate: call exists, agent available
  - Write command: `redis.lpush('cmd:bridge', \`${callUuid}:${agentId}\`)`
  - Return JSON: `{success: true}`
- [ ] Update `AgentCard.svelte` to call API on drop:
  - `fetch('/api/assign', {method: 'POST', body: JSON.stringify({...})})`
  - Show loading state while request pending
  - Update UI optimistically

**Validation:** Drag-drop call to agent, network tab shows POST to `/api/assign`, Python logs execute bridge.

---

### Task 3.6: Call Metadata Display (Enhanced Screen Pops)
- [ ] Update `CallCard.svelte` to show:
  - Caller name (large, bold)
  - Phone number (formatted with libphonenumber-js)
  - Company name from CRM data (if available)
  - Recent interaction history (last 3 tickets/calls)
  - Wait time countdown timer (updates every second)
  - Placeholder for sentiment gauge (Phase 5)
  - Customer lifetime value (CLV) indicator
  - Priority badge (VIP, Standard, Follow-up)
- [ ] Add CSS for card styling: shadow, border, hover effects
- [ ] Add color coding: green (< 1 min wait), yellow (1-3 min), red (> 3 min)
- [ ] Create expandable detail view with full customer history

**Validation:** Dashboard shows rich call cards with CRM screen pop data and live wait time.

---

### Task 3.7: Agent Status Indicators
- [ ] Update `AgentCard.svelte` to show:
  - Agent name and extension
  - Status badge: Available (green), Busy (red), Offline (gray)
  - Current call info if busy (caller name, duration)
  - Drop zone visual (dashed border when idle)
- [ ] Subscribe to `agent_updates` pub/sub in SSE endpoint
- [ ] Update agent store reactively when status changes

**Validation:** When call bridges, agent card changes from "Available" to "Busy" in real-time.

---

### Task 3.8: End-to-End Phase 3 Test
- [ ] Start full stack: FreeSWITCH, Redis, Python, Dramatiq, SvelteKit
- [ ] Open dashboard in browser
- [ ] Park call from SIP phone → call appears in dashboard within 500ms
- [ ] Drag call to agent → call bridges successfully
- [ ] Agent status updates to "Busy"
- [ ] End call → agent status updates to "Available"
- [ ] Test with multiple calls and agents simultaneously

**Validation:** Full user workflow from call parking to drag-drop assignment works smoothly.

---

## Phase 4: Python Command Executor (Already Integrated)

**Note:** Most Phase 4 work was completed in Phase 2 (Task 2.5, 2.6). Remaining items:

### Task 4.1: Command Result Feedback
- [ ] Update command executor to publish detailed results:
  - Success: `{success: true, bridged_at: timestamp}`
  - Error: `{success: false, error: "Agent busy", code: "USER_BUSY"}`
- [ ] Create SSE endpoint in SvelteKit: `/api/command-results/{callUuid}`
- [ ] Update `AgentCard.svelte` to wait for result and show error toast if failed

**Validation:** Drop call on busy agent, UI shows toast: "Agent is busy, please try another."

---

### Task 4.2: Command Timeout and Retry
- [ ] In SvelteKit assignment API, implement 10-second timeout:
  - Wait for result on `cmd:result:{callUuid}` channel
  - If timeout, check call state: `redis.hget(\`call:${callUuid}\`, 'state')`
  - If still "assigned", retry once
  - If second timeout, return error to UI
- [ ] Add logging for timeout cases

**Validation:** Simulate slow command execution, verify retry logic kicks in.

---

### Task 4.3: Multiple Command Types
- [ ] Extend command queue to support: `cmd:bridge`, `cmd:transfer`, `cmd:hangup`
- [ ] Update command executor to route based on command type
- [ ] Implement `uuid_transfer` for transferring active calls
- [ ] Implement `uuid_kill` for manager-initiated hangup
- [ ] Add UI buttons in dashboard for these actions

**Validation:** Manager can transfer call to different agent or end call from UI.

---

## Phase 5: AI Feature Integration (Local LLM + Product Knowledge)

### Task 5.1: Local LLM Infrastructure Setup
- [ ] Add Ollama service to `docker-compose.yml`:
  - Use `ollama/ollama:latest` image
  - Mount models volume: `./ollama-models:/root/.ollama`
  - Expose API on port 11434
  - Optional: GPU passthrough with `deploy.resources.reservations.devices`
- [ ] Pull base model: `docker exec ollama ollama pull llama3.1:8b` (or mistral, phi-3)
- [ ] Add to `requirements.txt`: `ollama-python>=0.1.0`, `faster-whisper>=0.10.0`
- [ ] Configure environment: `OLLAMA_HOST=http://localhost:11434`
- [ ] Test API: `curl http://localhost:11434/api/generate -d '{"model":"llama3.1:8b","prompt":"Hello"}'`

**Validation:** Ollama responds to API calls, model generates text locally.

---

### Task 5.2: Product Knowledge Base Setup
- [ ] Create `knowledge/` directory structure:
  - `knowledge/products/` - Product documentation (markdown/PDF)
  - `knowledge/faqs/` - Common questions and answers
  - `knowledge/troubleshooting/` - Issue resolution guides
  - `knowledge/scripts/` - Call handling scripts and templates
- [ ] Add to `requirements.txt`: `chromadb>=0.4.0`, `sentence-transformers>=2.2.0`, `pypdf>=3.0.0`
- [ ] Create `python/ml/setup_knowledge_base.py`:
  - Load documents from `knowledge/` directory (markdown, PDF, txt)
  - Split into chunks (500 tokens with 50 token overlap)
  - Generate embeddings with `sentence-transformers/all-MiniLM-L6-v2`
  - Store in ChromaDB collection: `product_knowledge`
  - Persist to `./chromadb-data`
- [ ] Seed with sample product docs (minimum 5-10 documents)
- [ ] Add to Docker: mount ChromaDB volume

**Validation:** Query ChromaDB returns relevant chunks for test product questions.

---

### Task 5.3: Local Whisper Transcription
- [ ] Implement local Whisper in `workers/tasks.py`:
  - Initialize `faster-whisper` model: `WhisperModel("base", device="cpu")` (or "cuda" if GPU)
  - Cache model instance to avoid reloading
  - Read audio chunk from disk
  - Transcribe: `segments, info = model.transcribe(audio_path, language="en")`
  - Combine segments into full transcript with timestamps
  - Return transcript text
- [ ] Add error handling for corrupted audio files
- [ ] Test with sample WAV files (various qualities: noisy, clear, accents)

**Validation:** Transcribe test audio locally in < 3 seconds, accuracy comparable to OpenAI Whisper.

---

### Task 5.4: Basic Sentiment Analysis (Simplified)
- [ ] Implement `analyze_sentiment(call_uuid, chunk_path)` with local LLM:
  - Call local Whisper to get transcript
  - Prompt local LLM via Ollama (simple analysis):
    ```
    Analyze sentiment (0.0=very negative, 1.0=very positive):
    
    Transcript: "{transcript}"
    
    Respond with: score|emotion
    Example: 0.3|frustrated
    ```
  - Parse score and emotion from response
  - Update Redis: `HSET call:{uuid} sentiment_score {score}, emotion "{emotion}"`
- [ ] Add TextBlob fallback if LLM is slow
- [ ] **[OPTIONAL - DEFER TO PHASE 7]:** Add RAG enhancement:
  - Query ChromaDB when specific issues detected
  - This adds complexity - skip for MVP

**Validation:** Sentiment score appears in Redis, dashboard shows emotion badge.

---

### Task 5.5: Sentiment Gauge in Dashboard
- [ ] Create `src/lib/components/SentimentGauge.svelte`:
  - Display circular gauge or progress bar
  - Color: red (< 0.4), yellow (0.4-0.7), green (> 0.7)
  - Show emotion label (frustrated, neutral, happy, etc.)
  - Show latest transcript snippet below gauge
- [ ] Integrate into `CallCard.svelte`
- [ ] Update when SSE receives sentiment updates

**Validation:** Active call shows live sentiment gauge updating every 5 seconds.

---

### Task 5.6: Manager Alerts for Low Sentiment
- [ ] In Python, after updating sentiment, check if score < 0.3
- [ ] If true, publish: `redis.publish('manager_alerts', json.dumps({type: 'frustrated', ...}))`
- [ ] Create SvelteKit SSE endpoint: `/api/alerts`
- [ ] In dashboard, subscribe and show desktop notification + banner
- [ ] Add browser notification permission request on page load

**Validation:** Low sentiment triggers desktop notification: "Caller is frustrated!"

---

### Task 5.7: Product-Aware Call Summarization with Local LLM
- [ ] Add to `requirements.txt`: `langchain>=0.1.0`, `langchain-community>=0.1.0`
- [ ] Implement `generate_summary(call_uuid, recording_path)`:
  - Transcribe full recording with local Whisper
  - Extract key topics and product mentions from transcript
  - Query ChromaDB for relevant product documentation
  - Use LangChain with Ollama for summarization:
    ```
    Summarize this customer support call in under 200 words:
    
    Transcript: {full_transcript}
    Product Context: {relevant_docs_from_chromadb}
    
    Include: issue discussed, resolution provided, customer satisfaction, action items
    ```
  - Store: `HSET call:{uuid} summary "{text}"`
- [ ] Trigger on `CHANNEL_HANGUP` for bridged calls (background priority)
- [ ] Add to dashboard history view

**Validation:** After call ends, product-aware summary appears in call history within 30 seconds.

---

### Task 5.8: Intelligent Action Items Extraction
- [ ] Extend `generate_summary` task:
  - After summary, prompt local LLM:
    ```
    Extract action items from this call summary:
    {summary}
    
    Format as JSON array:
    [{"task": "...", "priority": "high|medium|low", "owner": "agent|customer"}]
    ```
  - Parse JSON response with list of actions
  - Store: `HSET call:{uuid} action_items "[...]"`
- [ ] Display in dashboard history with checkboxes
- [ ] Optional: Create HubSpot tasks via API

**Validation:** Call with actions ("send quote", "schedule demo") shows in UI as checklist.

---

### Task 5.9: Smart Routing with Fine-Tuned Local LLM
- [ ] Create `python/ml/prepare_routing_data.py`:
  - Query Redis for historical calls: `ZRANGE calls:completed 0 -1`
  - Extract features: sentiment, issue keywords, caller lifecycle, time of day, agent specialties
  - Export training data as JSONL:
    ```jsonl
    {"prompt": "Customer frustrated about billing, lifecycle: customer", "completion": " agent_id:1002"}
    {"prompt": "New lead asking about features, lifecycle: lead", "completion": " agent_id:1003"}
    ```
- [ ] Create `python/ml/finetune_routing.py`:
  - Fine-tune Llama model: `ollama create routing-model -f Modelfile`
  - Modelfile includes training adapter
  - Evaluate accuracy on test set
- [ ] Schedule training weekly (cron or manual)

**Validation:** Fine-tuned routing model achieves >75% accuracy on agent prediction.

---

### Task 5.10: Real-time Routing Prediction with Product Context
- [ ] Create `workers/tasks.py` task: `predict_routing(call_uuid)`
- [ ] Load fine-tuned routing model from Ollama
- [ ] Extract features from Redis call data + transcript keywords
- [ ] Query ChromaDB for issue category based on caller's words
- [ ] Prompt routing model:
  ```
  Recommend top 3 agents for this call:
  
  Sentiment: {score}, Issue: {category}
  CRM stage: {stage}, Time: {hour}
  Available agents: {agent_list_with_specialties}
  
  Format: agent_id:confidence (one per line)
  ```
- [ ] Parse top 3 agents with confidence scores
- [ ] Store: `HSET call:{uuid} recommended_agents "[...]"`
- [ ] Display in dashboard UI with "⭐ Recommended" badges

**Validation:** New call shows product-aware agent recommendations in UI.

---

### Task 5.11: AI-Powered IVR with Local TTS/STT
- [ ] Add to `requirements.txt`: `TTS>=0.13.0` (Coqui TTS for local voice synthesis)
- [ ] Implement IVR flow in `orchestrator/ivr_handler.py`:
  - Generate greeting with Coqui TTS: "Hello, how can I help you today?"
  - Save audio to `/tmp/ivr_greeting.wav`
  - Play via ESL: `uuid_broadcast {uuid} /tmp/ivr_greeting.wav both`
  - Record response (5 seconds max or silence detection)
  - Transcribe with local Whisper
  - Use local LLM to understand intent:
    ```
    Customer said: "{transcript}"
    Determine intent: billing|technical|sales|general
    Extract product mentioned: {product_name}
    ```
  - Query ChromaDB for relevant FAQ
  - Generate response with LLM + TTS, or route to specialized agent
- [ ] Trigger IVR for calls without CRM match

**Validation:** Unknown caller hears natural greeting, system understands intent, routes appropriately.

---

### Task 5.12: VIP and Product Expert Detection
- [ ] Schedule to run nightly (cron or manual for now)

**Validation:** Script runs without errors, model file created, accuracy > 75%.

---

### Task 5.8: Smart Routing Prediction in Real-time
- [ ] Create `workers/tasks.py` task: `predict_routing(call_uuid)`
- [ ] Load model from disk (cache in memory after first load)
- [ ] Extract features from Redis call data
- [ ] Predict top 3 agents with confidence scores
- [ ] Store: `HSET call:{uuid} recommended_agents "[...]"`
- [ ] Display in dashboard UI as badges: "⭐ Recommended"

**Validation:** New call shows recommended agents in UI, assignment to recommended agent is prioritized.

---

### Task 5.9: Voice Interaction IVR (Basic TTS/STT)
- [ ] Add to `requirements.txt`: `elevenlabs`, `deepgram-sdk`
- [ ] Implement IVR flow in `orchestrator/ivr_handler.py`:
  - Generate greeting with ElevenLabs TTS
  - Play via ESL: `uuid_broadcast {uuid} {audio_url}`
  - Record response, send to Deepgram STT
  - Extract name or intent
  - Store in Redis
- [ ] Trigger IVR for calls without CRM match

**Validation:** Unknown caller hears natural greeting, system understands intent, routes appropriately.

---

### Task 5.12: VIP and Product Expert Detection
- [ ] In `crm_lookup` task, check contact fields:
  - `lifecycle_stage == 'customer'`
  - `annual_value > 100000`
- [ ] If true, set: `HSET call:{uuid} vip true`
- [ ] Publish alert: `redis.publish('manager_alerts', {type: 'vip', ...})`
- [ ] Display gold badge in dashboard UI
- [ ] Query ChromaDB for caller's previous issues/products
- [ ] Pass historical context to agent when call connects

**Validation:** VIP customer call triggers alert, dashboard shows gold "VIP" badge with context.

---

### Task 5.13: Continuous Learning from Call Outcomes
- [ ] Create `python/ml/update_knowledge_base.py`:
  - Extract successful resolutions from completed calls
  - Parse agent responses that resolved issues
  - Add to ChromaDB as new knowledge documents:
    ```
    Issue: {extracted_problem}
    Solution: {successful_resolution}
    Product: {mentioned_product}
    Source: Call {uuid} on {date}
    ```
  - Re-embed and update vector database
- [ ] Schedule to run daily with manual review queue
- [ ] Dashboard shows "Add to knowledge base" button for quality calls

**Validation:** Successful call resolutions become searchable product knowledge for future calls.

---

### Task 5.14: End-to-End Phase 5 Test with Local AI Stack
- [ ] Make test calls with various scenarios:
  - Happy customer (high sentiment)
  - Frustrated customer (low sentiment, triggers alert)
  - VIP customer (triggers VIP alert)
  - Unknown caller (triggers IVR with product questions)
  - Product-specific technical issue (tests knowledge base)
- [ ] Verify all AI features work locally:
  - Sentiment analysis updates live (no OpenAI API calls)
  - Post-call summary generates with product context
  - Smart routing recommends correct specialist agent
  - Action items extracted accurately
  - IVR understands intent and routes properly
- [ ] Measure costs: $0 for AI inference (only infrastructure)
- [ ] Check ChromaDB query performance (< 100ms)
- [ ] Monitor Ollama resource usage (RAM, GPU if available)

**Validation:** All AI features integrated and functional using 100% local LLM stack with product knowledge.

---

## Phase 6: Production Hardening

### Task 6.1: Comprehensive Error Handling
- [ ] Audit all Python code for unhandled exceptions
- [ ] Wrap critical sections with try/except and log errors
- [ ] Implement circuit breaker for external APIs (HubSpot only - AI is local now):
  - After 5 failures in 1 minute, stop calling for 5 minutes
  - Return fallback responses
- [ ] Add error counters to metrics
- [ ] Handle Ollama failures gracefully (fallback to TextBlob for sentiment)

**Validation:** Simulate API failures, system continues operating with degraded functionality.

---

### Task 6.2: Logging and Observability
- [ ] Configure structured logging (JSON format) in Python:
  - Use `python-json-logger` library
  - Log levels: DEBUG, INFO, WARNING, ERROR
  - Include context: call_uuid, agent_id, timestamp
- [ ] Add log aggregation (stdout → Docker logs → Loki/Elasticsearch)
- [ ] Create Grafana dashboard for logs

**Validation:** Logs are searchable by call_uuid, errors are filterable.

---

### Task 6.3: Metrics with Prometheus
- [ ] Add to `requirements.txt`: `prometheus-client`
- [ ] Instrument Python code with metrics:
  - Counters: `calls_parked_total`, `calls_completed_total`, `errors_total`
  - Histograms: `call_duration_seconds`, `crm_lookup_duration_seconds`
  - Gauges: `active_calls`, `available_agents`
- [ ] Expose `/metrics` endpoint on Python HTTP server (add Flask or FastAPI)
- [ ] Configure Prometheus to scrape endpoint

**Validation:** Prometheus UI shows metrics, graphs display over time.

---

### Task 6.4: Distributed Tracing (Optional)
- [ ] Add to `requirements.txt`: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-jaeger`
- [ ] Instrument key operations with spans:
  - CRM lookup
  - Sentiment analysis
  - Call bridging
- [ ] Export traces to Jaeger
- [ ] View traces in Jaeger UI

**Validation:** Trace shows full call lifecycle: park → CRM → bridge → hangup with timing breakdown.

---

### Task 6.5: Health Checks and Monitoring
- [ ] Add `/health` endpoint in Python returning:
  - ESL connection status
  - Redis connection status
  - Last event received timestamp
  - Dramatiq worker status
- [ ] Add health check to Docker Compose:
  - `healthcheck: CMD curl -f http://localhost:8000/health || exit 1`
- [ ] Configure alerting: if health check fails for 3 consecutive checks, send alert

**Validation:** Stop Redis, health check fails, Docker marks container unhealthy.

---

### Task 6.6: Load Testing
- [ ] Install SIPp: `apt-get install sipp`
- [ ] Create SIPp scenario XML for inbound calls
- [ ] Run load test: 100 concurrent calls for 5 minutes
- [ ] Monitor metrics: CPU, memory, call latency, error rate
- [ ] Identify bottlenecks and optimize (e.g., increase worker count)

**Validation:** System handles 100 concurrent calls with < 2s assignment latency, no errors.

---

### Task 6.7: Basic Analytics Dashboard
- [ ] Create `src/routes/dashboard/analytics/+page.svelte`:
  - Real-time metrics: calls waiting, total calls today, agents available
  - Simple counters (no fancy charts yet)
  - Agent list with call count per agent
- [ ] Redis metrics tracking:
  - `HINCRBY metrics:daily:{date} total_calls 1`
  - `HSET metrics:agents:{agent_id} total_handled {count}`
- [ ] Supervisor view: `/dashboard/supervisor`
  - Live agent grid with status, current call
  - Call queue depth and longest wait time
  - Basic alerts (queue > 5 calls)
- [ ] **[DEFER]** Advanced forecasting/scheduling → Phase 7+ plugin

**Validation:** Dashboard shows real-time counts and agent status.

---

### Task 6.8: Quality Management (Core Feature)
- [ ] Recording review interface: `/dashboard/recordings`
  - List all recordings with filters (agent, date, duration)
  - Inline audio player with basic playback controls
  - Add notes capability: `HSET call:{uuid} supervisor_notes {text}`
  - Tag recordings: `SADD call:{uuid}:tags training compliance`
- [ ] Simple scorecard system:
  - Define 3-5 criteria in Redis: greeting, resolution, tone
  - Supervisors rate 1-5 scale per criterion
  - Store: `HSET call:{uuid}:evaluation greeting 4 resolution 5 tone 4`
  - Show agent average scores in dashboard
- [ ] No waveform visualization (too complex for MVP)
- [ ] No automatic transcription search (Phase 7+)

**Validation:** Supervisors can review recordings, add notes, and basic scoring works.

---

### Task 6.9: Live Call Monitoring & Coaching
- [ ] Add "Monitor" action to live call cards (supervisor only):
  - Click "Monitor" → Redis command: `cmd:monitor:{call_uuid}`
  - Python executor: `esl.execute('eavesdrop', agent_channel_uuid)`
  - Supervisor hears both sides, agents don't hear supervisor
- [ ] Add "Whisper" mode (coach agent privately):
  - Redis command: `cmd:whisper:{call_uuid}`
  - Python executor: `esl.execute('whisper', agent_channel_uuid)`
  - Supervisor talks only to agent, customer doesn't hear
- [ ] Add "Barge" mode (join call as participant):
  - Redis command: `cmd:barge:{call_uuid}`
  - Python executor: `esl.execute('three_way', agent_channel_uuid)`
- [ ] Update dashboard with supervisor controls sidebar

**Validation:** Supervisor can monitor, whisper, and barge into live calls without disrupting customer.

---

### Task 6.10: Callback Queue Management
- [ ] Create callback scheduling UI:
  - "Request Callback" button on call card (if wait > 5 min)
  - Form: preferred time, phone number, reason
  - Store: `ZADD callbacks:scheduled {timestamp} {call_data_json}`
- [ ] Create callback worker in Dramatiq:
  - Check `callbacks:scheduled` every minute
  - For due callbacks: originate call to customer, then bridge to available agent
  - Retry logic: 3 attempts, 5 min apart
- [ ] Add callbacks list to dashboard:
  - Show scheduled, in-progress, completed callbacks
  - Allow manual triggering: "Call Now"

**Validation:** Customer can schedule callback, system calls them back at scheduled time.

---

---

### Plugin Services (Optional - Can Enable Later)

### Task 6.11: CSAT Survey Service (Plugin)
- [ ] Create separate microservice: `services/csat-plugin/`
  - Dockerfile with Python + Redis client
  - Subscribe to `call_events` pub/sub channel
  - On `call_ended` event → trigger survey
- [ ] Survey IVR dialplan in FreeSWITCH:
  - Extension 9999: CSAT survey
  - Play: "On a scale of 1-5, how satisfied are you?"
  - Capture DTMF, publish to Redis: `PUBLISH csat_results {data}`
- [ ] CSAT analytics endpoint in SvelteKit:
  - `GET /api/csat/trends` → fetch from Redis
  - Display in dashboard (only if plugin enabled)
- [ ] Enable/disable via env var: `CSAT_ENABLED=true`

**Validation:** When enabled, surveys work. When disabled, calls end normally (no survey).

---

### Task 6.12: Skills-Based Routing Enhancement
- [ ] Define agent skills in Redis:
  - `SADD agent:{agent_id}:skills technical billing sales`
- [ ] Update smart routing to consider skills:
  - If caller history shows technical issues → route to technical agents
  - If high-value customer → route to senior agents
  - Use LLM to infer call reason from IVR or initial greeting
- [ ] Create skills management UI: `/dashboard/agents/{id}/skills`
  - Add/remove skills
  - Set proficiency levels (1-5)
- [ ] Update routing algorithm to match call requirements with agent skills

**Validation:** Technical calls route to technical agents, routing time < 500ms.

---

### Task 6.13: Security Hardening
- [ ] Move secrets to environment variables (no hardcoded passwords)
- [ ] Use secrets manager (AWS SSM, Vault, or Docker secrets)
- [ ] Configure FreeSWITCH ACL: only allow connections from known IPs
- [ ] Enable Redis authentication: `requirepass {strong_password}`
- [ ] HTTPS for SvelteKit (Caddy or Nginx reverse proxy)
- [ ] Rate limiting on API endpoints (express-rate-limit)

**Validation:** Penetration test (OWASP ZAP) finds no critical vulnerabilities.

---

### Task 6.14: Data Retention and GDPR Compliance
- [ ] Implement automatic data cleanup:
  - Recordings older than 30 days: delete from disk
  - Call records older than 90 days: remove from Redis
  - Transcripts and summaries: anonymize PII after 30 days
- [ ] Add data export API: `GET /api/calls/{uuid}/export` returns all call data
- [ ] Add data deletion API: `DELETE /api/calls/{uuid}` purges call and recording
- [ ] Document data retention policy in `docs/compliance.md`

**Validation:** Old data is automatically purged, export/delete APIs work correctly.

---

### Task 6.15: CI/CD Pipeline Setup
- [ ] Create `.github/workflows/ci.yml`:
  - Run on: push, pull_request
  - Jobs: lint, test, build Docker images
  - Python: pytest for unit tests
  - SvelteKit: Vitest for unit tests, Playwright for E2E
- [ ] Create `.github/workflows/cd.yml`:
  - Run on: push to main branch
  - Deploy to staging environment
  - Run smoke tests
  - If pass, deploy to production
- [ ] Set up Docker registry (Docker Hub, GitHub Container Registry, or private)

**Validation:** Push to main triggers deployment, new version goes live automatically.

---

### Task 6.16: Documentation and Runbooks
- [ ] Write comprehensive `README.md`:
  - Architecture overview with diagram
  - Setup instructions (local dev)
  - Environment variables reference
  - Deployment guide (production)
- [ ] Create `docs/runbooks/`:
  - `incident-response.md`: What to do when system is down
  - `scaling.md`: How to scale components
  - `backup-restore.md`: Backup/restore procedures
- [ ] Create `docs/api.md`: Document all HTTP and Redis APIs
- [ ] Record demo video showing full workflow

**Validation:** New team member can set up local environment in < 30 minutes using docs.

---

### Task 6.17: End-to-End Production Validation
- [ ] Deploy to production environment
- [ ] Run smoke tests: 10 test calls through full workflow
- [ ] Monitor for 24 hours:
  - Check metrics (call volume, latency, errors)
  - Review logs for unexpected warnings
  - Verify alerts fire correctly
- [ ] Conduct user acceptance testing (UAT) with real managers
- [ ] Gather feedback and document issues in backlog

**Validation:** System runs in production for 24 hours with zero downtime, positive user feedback.

---

## Completion Checklist

Before marking this change as complete:
- [ ] All 70+ tasks above are checked off
- [ ] `openspec validate implement-hybrid-telephony-ai-platform --strict` passes
- [ ] All specs have been moved to `openspec/specs/` (if applicable)
- [ ] Production deployment is successful
- [ ] Documentation is complete and reviewed
- [ ] Team is trained on new system
- [ ] Legacy system (if any) is deprecated or migrated

**Approval Required:** Product Owner, Engineering Lead

---

**Total Estimated Time:** 12-16 weeks with 2 full-time engineers  
**Dependencies:** Docker, FreeSWITCH knowledge, Python expertise, SvelteKit familiarity, DevOps skills

**Next Steps After Completion:** Archive this change proposal, update `openspec/specs/` with finalized capabilities, plan Phase 7 enhancements (multi-tenancy, mobile app, advanced ML features).
