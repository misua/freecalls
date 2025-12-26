# Capability: AI Intelligence Engine

## ADDED Requirements

### Requirement: System SHALL integrate with CRM using intelligent caching

The system SHALL lookup caller information from HubSpot CRM with intelligent caching to minimize API calls and costs.

#### Scenario: Cache miss triggers HubSpot lookup

**Given** a call parks with caller_id `+15551234567`  
**When** CRM lookup task executes  
**And** Redis cache key `crm:+15551234567` does not exist  
**Then** Dramatiq worker calls HubSpot API `/contacts/v1/contact/identity-profile/{caller_id}`  
**And** stores result in Redis with 1-hour TTL  
**And** updates call metadata: `HSET call:{uuid} crm_data "{json}"`

#### Scenario: Cache hit avoids API call

**Given** caller `+15551234567` called 30 minutes ago  
**And** CRM data is cached in Redis  
**When** same caller calls again  
**Then** CRM lookup retrieves from cache without API call  
**And** response time is < 10ms  
**And** cache hit metric is incremented

#### Scenario: HubSpot API failure fallback

**Given** CRM lookup task executes  
**When** HubSpot API returns 500 error or times out after 5 seconds  
**Then** task retries 3 times with exponential backoff  
**And** if all retries fail, stores `crm_data: {status: 'unavailable'}`  
**And** call proceeds without CRM data  
**And** error is logged for monitoring

---

### Requirement: System SHALL analyze caller sentiment in real-time

The system SHALL analyze caller sentiment during active calls using audio transcription and LLM analysis.

#### Scenario: Streaming audio chunks for analysis

**Given** a call is bridged and active  
**When** Python has been recording for 5 seconds  
**Then** it extracts a 5-second audio chunk  
**And** enqueues `analyze_sentiment.send(call_uuid, chunk_path)`  
**And** continues recording next chunk

#### Scenario: Whisper transcription and GPT sentiment

**Given** a Dramatiq worker receives sentiment task with audio chunk  
**When** worker sends audio to OpenAI Whisper API  
**Then** transcription is received within 2 seconds  
**And** worker sends to GPT-4o-mini: "Analyze sentiment (0.0-1.0): {transcript}"  
**And** parses numeric score from response  
**And** updates Redis: `HSET call:{uuid} sentiment_score {score}, last_transcript "{text}"`

#### Scenario: Low sentiment triggers manager alert

**Given** sentiment analysis returns score < 0.3  
**When** score is written to Redis  
**Then** Python publishes to `manager_alerts` channel  
**And** alert includes: call_uuid, sentiment_score, transcript_snippet  
**And** SvelteKit SSE pushes notification to dashboard  
**And** manager sees visual indicator (red border on call card)

#### Scenario: Fallback to TextBlob on OpenAI failure

**Given** OpenAI API is unavailable or rate-limited  
**When** sentiment analysis task executes  
**Then** worker uses local TextBlob library on transcript  
**And** computes polarity score (-1.0 to 1.0)  
**And** normalizes to 0.0-1.0 scale: `(polarity + 1) / 2`  
**And** logs fallback usage for monitoring

---

### Requirement: System SHALL generate AI-powered call summaries

The system SHALL generate AI-powered summaries of completed calls for agent review and quality assurance.

#### Scenario: Triggering summary on hangup

**Given** a call reaches `CHANNEL_HANGUP` event  
**And** call was bridged to agent (not abandoned)  
**When** Python processes hangup  
**Then** it enqueues `generate_summary.send(call_uuid, recording_path)` with priority=1 (background)  
**And** summary generation does not block other operations

#### Scenario: LangChain summarization pipeline

**Given** summary task receives recording path  
**When** worker transcribes full audio with Whisper  
**And** splits transcript into chunks of 2000 tokens  
**Then** uses LangChain MapReduce:  
    - Map: Summarize each chunk  
    - Reduce: Combine into final summary  
**And** final summary is < 200 words  
**And** stores in Redis: `HSET call:{uuid} summary "{text}"`

#### Scenario: Extracting action items from summary

**Given** LangChain has generated call summary  
**When** worker prompts GPT: "Extract action items from: {summary}"  
**Then** parses structured response with action list  
**And** stores: `HSET call:{uuid} action_items "[{...}]"`  
**And** creates tasks in HubSpot via API (if CRM integration enabled)

---

### Requirement: System SHALL use ML for optimal agent assignment

The system SHALL use machine learning to recommend optimal agent assignments based on historical patterns.

#### Scenario: Training routing model offline

**Given** historical call data with features: [caller_sentiment, topic, agent_id, resolution_time]  
**When** ML pipeline runs nightly  
**Then** trains scikit-learn RandomForestClassifier  
**And** evaluates on test set (80/20 split)  
**And** if accuracy > 75%, exports model to `models/routing_v{date}.pkl`  
**And** updates Redis key `ml:routing:model_path` to new version

#### Scenario: Real-time routing prediction

**Given** a call parks with CRM data and initial sentiment  
**When** routing task executes  
**Then** loads current model from Redis path  
**And** extracts features: [sentiment_score, caller_lifecycle_stage, call_hour, previous_agent_id]  
**And** predicts top 3 agent recommendations with confidence scores  
**And** stores: `HSET call:{uuid} recommended_agents "[{agent: 1001, confidence: 0.85}, ...]"`

#### Scenario: Fallback to round-robin on model failure

**Given** ML model fails to load or predict  
**When** routing task executes  
**Then** falls back to round-robin from available agents  
**And** logs warning: "ML routing unavailable, using fallback"  
**And** increments metric `routing_fallback_total`

---

### Requirement: System SHALL support AI-powered IVR interactions

The system SHALL support AI-powered interactive voice response using text-to-speech and speech-to-text.

#### Scenario: Greeting caller with dynamic TTS

**Given** a call parks without CRM match  
**When** Python decides to collect caller info via IVR  
**Then** generates text: "Hello, I didn't find your number. Please say your name."  
**And** calls ElevenLabs TTS API to generate audio  
**And** plays audio via ESL: `uuid_broadcast {uuid} {audio_url} both`

#### Scenario: Capturing caller response with STT

**Given** TTS prompt has finished playing  
**When** Python starts recording caller's speech  
**And** detects 2 seconds of silence (end of utterance)  
**Then** sends audio chunk to Deepgram STT API  
**And** receives transcript within 500ms  
**And** stores: `HSET call:{uuid} caller_stated_name "{text}"`

#### Scenario: Multi-turn conversation with GPT

**Given** caller has responded to initial prompt  
**When** Python sends context to GPT: "User said: {transcript}. Respond naturally."  
**Then** GPT generates next question or confirmation  
**And** Python converts to speech and plays  
**And** continues loop until info is collected or max 3 turns reached

---

### Requirement: System SHALL detect high-value and at-risk callers

The system SHALL detect high-value or at-risk callers and provide proactive notifications to managers.

#### Scenario: VIP caller detection

**Given** CRM lookup returns contact with `lifecycle_stage: 'customer'` and `annual_value > $100,000`  
**When** call metadata is written to Redis  
**Then** Python tags call: `HSET call:{uuid} vip true`  
**And** publishes alert: `PUBLISH manager_alerts {type: 'vip', call_uuid, name, value}`  
**And** dashboard displays gold badge on call card

#### Scenario: Frustrated caller escalation

**Given** sentiment score has been < 0.4 for 3 consecutive measurements  
**When** Python detects pattern  
**Then** automatically suggests escalation to senior agent  
**And** updates: `HSET call:{uuid} escalation_recommended true`  
**And** dashboard shows "Escalate" button with one-click assignment

#### Scenario: Returning customer recognition

**Given** caller_id matches previous call within last 7 days  
**When** CRM lookup completes  
**Then** retrieves previous call summary and outcome  
**And** displays in UI: "Caller discussed {topic} on {date}"  
**And** agent can review context before answering
