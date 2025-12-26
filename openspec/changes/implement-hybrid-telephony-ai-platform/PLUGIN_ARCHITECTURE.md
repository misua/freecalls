# Plugin Architecture & Feature Simplification

## Overview

The system is now designed as a **modular plugin architecture** where advanced features can be added as independent microservices. This makes it easy to start simple and add complexity later.

---

## Core System (MVP - Phase 1-5)

These components run in every deployment:

### 1. **FreeSWITCH** (Telephony)
- Handles SIP calls
- Parks incoming calls
- Records audio
- Agents use regular SIP phones (not browser)

### 2. **Python Orchestrator**
- Listens to FreeSWITCH events
- Executes commands (bridge, transfer, hangup)
- Queues AI tasks

### 3. **Redis** (Message Bus)
- Stores call state
- Command queue
- Pub/sub for real-time updates

### 4. **SvelteKit Dashboard**
- Manager sees live calls
- Drag-and-drop to assign to agents
- Real-time updates via Server-Sent Events

### 5. **Core AI Workers** (Dramatiq)
- **CRM Lookup:** Fetch customer data from HubSpot
- **Basic Sentiment:** Transcribe + analyze emotion (happy/neutral/frustrated)
- **Call Summary:** Generate notes after call ends
- **Smart Routing:** LLM decides which agent based on history

---

## Plugin Services (Optional - Can Enable/Disable)

These are **separate Docker containers** that can be turned on/off:

### Plugin 1: CSAT Survey Service
**What it does:** After call ends, asks customer "Rate 1-5 stars"

**How to enable:**
```bash
# .env file
CSAT_ENABLED=true
```

**How it works:**
1. Plugin subscribes to Redis: `call_events` channel
2. When call ends → Triggers IVR survey
3. Customer presses number → Stored in Redis
4. Dashboard shows average CSAT scores

**Why plugin?** Some companies don't want surveys. Others do. This way you choose.

---

### Plugin 2: Quality Management Service
**What it does:** Supervisors review recordings and score agents

**Included in core (simplified):**
- Recording playback
- Add notes to calls
- Simple 1-5 scoring on 3-5 criteria

**NOT included (too complex):**
- Waveform visualization
- Automatic transcript search
- Advanced evaluation workflows

**Why core?** Most contact centers need basic quality checks. Advanced features are Phase 7+.

---

### Plugin 3: Skills-Based Routing (Enhanced)
**What it does:** Routes calls to agents based on skill proficiency

**How smart routing works:**
```python
# Basic (included in core):
def route_call(caller_id):
    history = get_crm(caller_id)
    reason = llm.predict(f"Why is {caller_id} calling? {history}")
    # Output: "technical_support"
    agent = find_available_agent()
    bridge(agent)

# Enhanced (plugin):
def route_call_advanced(caller_id):
    reason = llm.predict(...)  # "technical_support"
    
    # Find agents with skills
    agents = get_agents_with_skill("technical", min_level=3)
    
    # Score agents by:
    # - Skill proficiency (1-5)
    # - Recent CSAT scores
    # - Current workload
    best_agent = rank_agents(agents)
    
    bridge(best_agent)
```

**Core includes:** Basic routing (LLM infers reason → routes to available agent)

**Plugin adds:** Skill proficiency matching, agent performance scoring

---

## What RAG-Enhanced Sentiment Means (And Why It's Optional)

### Basic Sentiment (Included in Core):
```
Customer: "This doesn't work!"
AI: Detects sentiment = FRUSTRATED 😡
Dashboard: Shows red badge
```

### RAG-Enhanced Sentiment (Plugin - Phase 7+):
```
Customer: "The backup sync doesn't work!"
AI Process:
1. Transcribe: "backup sync doesn't work"
2. Detect sentiment: FRUSTRATED
3. Search ChromaDB: "backup sync"
4. Find KB article: "Known bug on Mac OS 14.2"
5. Tell agent: "Customer frustrated about backup sync → KB Article #42"

Agent sees: "😡 Frustrated | Issue: backup sync | KB: Article #42"
```

**Why it's a lot of work:**
- Need to embed all product docs into ChromaDB vectors
- Need to tune search queries for relevance
- Need to format results for agent display
- Adds 2-3 seconds latency per analysis

**Decision:** Start with basic sentiment. Add RAG later if needed.

---

## SIP Client: Browser vs Phone

### Five9's Approach:
- Agents log into web browser
- WebRTC handles audio (no phone needed)
- All calls through browser

### Our Approach (Simpler):
- Agents use **regular SIP phones** (desk phone or softphone app like Zoiper)
- Managers use **web dashboard** to assign calls
- FreeSWITCH bridges call to agent's SIP extension

**Why this way?**
1. **Simpler:** No WebRTC complexity
2. **Better audio:** Hardware phones have better quality
3. **Compatible:** Works with existing FreeSWITCH config
4. **Fallback:** If internet lags, phone still works

**Could we add browser calling?** Yes, FreeSWITCH supports WebRTC. But it's Phase 7+ enhancement.

---

## Docker Compose Example

```yaml
version: '3.8'

services:
  # Core (always running)
  freeswitch:
    image: signalwire/freeswitch:latest
    network_mode: host
  
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  
  orchestrator:
    build: ./python
    depends_on: [redis, freeswitch]
  
  dashboard:
    build: ./sveltekit
    ports: ["3000:3000"]
  
  # Plugins (enable via .env)
  csat-service:
    build: ./plugins/csat
    environment:
      - ENABLED=${CSAT_ENABLED:-false}
    depends_on: [redis]
  
  quality-mgmt:
    build: ./plugins/quality
    environment:
      - ENABLED=${QM_ENABLED:-false}
    depends_on: [redis]
```

**To enable CSAT:**
```bash
echo "CSAT_ENABLED=true" >> .env
docker-compose up -d
```

**To disable:**
```bash
echo "CSAT_ENABLED=false" >> .env
docker-compose restart csat-service
```

---

## Updated Implementation Plan

### Phase 1-2: Foundation (Weeks 1-4)
- FreeSWITCH + Docker
- Python orchestrator
- Redis state management
- CRM integration
- ✅ **Deliverable:** Calls park, managers see them in dashboard

### Phase 3: Dashboard (Weeks 5-6)
- SvelteKit UI
- Drag-and-drop assignment
- Real-time updates
- ✅ **Deliverable:** Full manager workflow works

### Phase 4: Commands (Week 7)
- Bridge, transfer, hangup commands
- Error handling
- ✅ **Deliverable:** Agents receive calls

### Phase 5: Core AI (Weeks 8-12)
- Local Ollama + Llama 3.1
- ChromaDB setup (for smart routing only)
- Whisper STT
- Basic sentiment (no RAG yet)
- Smart routing with LLM
- ✅ **Deliverable:** AI-powered call routing + sentiment detection

### Phase 6: Hardening (Weeks 13-16)
- Monitoring (Prometheus)
- Logging (structured JSON)
- Basic analytics dashboard
- Quality management (recording review, simple scoring)
- Load testing
- Security (HTTPS, auth)
- ✅ **Deliverable:** Production-ready system

### Phase 7+: Plugins (Future)
- CSAT survey service
- Enhanced skills routing
- RAG-enhanced sentiment
- Workforce forecasting
- Callback queue
- Gamification

---

## Feature Decision Matrix

| Feature | Status | Reason |
|---------|--------|--------|
| **Call parking** | ✅ Core | Essential for operation |
| **Drag-and-drop UI** | ✅ Core | Key differentiator |
| **CRM integration** | ✅ Core | Needed for context |
| **Basic sentiment** | ✅ Core | Low-hanging fruit |
| **Smart routing** | ✅ Core | AI value prop |
| **Recording playback** | ✅ Core | QM requirement |
| **Simple scorecards** | ✅ Core | Supervisor needs |
| **RAG sentiment** | 🔌 Plugin | Too complex for MVP |
| **CSAT surveys** | 🔌 Plugin | Not everyone wants |
| **Skills matching** | 🔌 Plugin | Nice but not required |
| **Workforce forecasting** | 🔌 Plugin | Only for 20+ agents |
| **Gamification** | 🔌 Plugin | Low priority |

---

## Questions Answered

### 1. "What is post-call CSAT?"
Customer hears: "Rate your satisfaction 1-5" → Presses button → Dashboard shows agent scores

**Status:** Optional plugin (can enable/disable)

### 2. "Are we using SIP client in browser?"
No, agents use regular SIP phones. Only managers use web dashboard.

**Could add browser calling:** Yes, but Phase 7+ (WebRTC complexity)

### 3. "What is RAG-enhanced sentiment?"
Combines emotion detection with product knowledge lookup → Suggests relevant KB articles

**Status:** Deferred to Phase 7+ (too complex for MVP)

### 4. "What is smart routing?"
LLM analyzes caller history → Predicts reason → Routes to best agent

**Status:** Core feature (Phase 5)

**Enhanced version (plugin):** Adds skill proficiency matching

### 5. "Aren't we doing our own brain for routing?"
Yes! "Smart routing" = "our AI routing brain" = same thing

The LLM learns from outcomes and improves over time.

---

## Summary

**MVP Core (Phase 1-5):**
- FreeSWITCH telephony
- Python orchestrator
- Redis messaging
- SvelteKit dashboard
- Local AI routing brain
- Basic sentiment detection
- Simple quality management

**Plugins (Phase 6+):**
- CSAT surveys
- Enhanced skills routing
- RAG sentiment analysis
- Workforce forecasting

**Philosophy:** Start simple, add complexity as needed. Every plugin can be enabled/disabled independently.
