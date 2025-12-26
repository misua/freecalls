# Capability: Redis State Management

## ADDED Requirements

### Requirement: System SHALL maintain structured call state

The system SHALL maintain structured call state in Redis with consistent key naming and data types.

#### Scenario: Creating call record on park

**Given** a call parks in FreeSWITCH  
**When** Python orchestrator receives `CHANNEL_PARK` event  
**Then** creates Redis hash with keys:  
```
HSET call:{uuid}
  state "parked"
  caller_id "+15551234567"
  caller_name "John Doe"
  parked_at 1703548800
  created_at 1703548800
  sip_call_id "abc123@domain"
```
**And** adds to sorted set: `ZADD calls {parked_at} {uuid}`  
**And** sets expiration: `EXPIRE call:{uuid} 86400`

#### Scenario: Updating call state on assignment

**Given** a call is in "parked" state  
**When** manager assigns to agent via dashboard  
**Then** atomic update with Redis transaction:  
```
WATCH call:{uuid}
MULTI
HSET call:{uuid} state "assigned" assigned_to "1001" assigned_at {timestamp}
EXEC
```
**And** if transaction fails (concurrent modification), retry once

#### Scenario: Cleaning up completed calls

**Given** a call reaches "completed" state  
**When** `CHANNEL_HANGUP` event processed  
**Then** updates final fields:  
```
HSET call:{uuid}
  state "completed"
  completed_at {timestamp}
  duration_seconds {duration}
```
**And** removes from active set: `ZREM calls {uuid}`  
**And** adds to history set: `ZADD calls:completed {completed_at} {uuid}`  
**And** expiration extended to 7 days

---

### Requirement: System SHALL implement reliable command queue

The system SHALL implement a reliable command queue for UI-to-Python communication.

#### Scenario: Enqueuing bridge command

**Given** SvelteKit receives call assignment request  
**When** POST `/api/assign` handler executes  
**Then** validates inputs (call_uuid exists, agent_id valid)  
**And** pushes command: `LPUSH cmd:bridge "{uuid}:{agent_id}:{timestamp}"`  
**And** returns immediately with 202 Accepted status

#### Scenario: Python consuming commands with blocking pop

**Given** Python orchestrator is running  
**When** command consumer loop executes  
**Then** blocks on: `BRPOP cmd:bridge 1` (1 second timeout)  
**And** if command received, parses payload  
**And** executes FreeSWITCH ESL command  
**And** publishes result: `PUBLISH cmd:result:{uuid} "{success: true}"`

#### Scenario: Command timeout handling

**Given** a bridge command is enqueued  
**When** Python does not process within 10 seconds  
**Then** SvelteKit times out waiting for result  
**And** checks call state: `HGET call:{uuid} state`  
**And** if still "assigned", retries command once  
**And** if second timeout, marks as failed and alerts user

---

### Requirement: System SHALL use Pub/Sub for event distribution

The system SHALL use Redis Pub/Sub for real-time event distribution to multiple subscribers.

#### Scenario: Publishing call state changes

**Given** Python updates call state in Redis  
**When** state transition occurs (e.g., parked → assigned)  
**Then** publishes to channel: `PUBLISH call_updates "{type: 'call_updated', call_uuid, new_state}"`  
**And** all subscribed SvelteKit servers receive event within 10ms  
**And** broadcast to connected SSE clients

#### Scenario: Multiple dashboard instances stay synchronized

**Given** two managers have dashboards open  
**When** one manager assigns a call  
**Then** both dashboards receive SSE update simultaneously  
**And** call disappears from available list on both screens  
**And** no race condition allows double-assignment

#### Scenario: Alert broadcasting

**Given** Python detects VIP caller  
**When** alert is generated  
**Then** publishes: `PUBLISH manager_alerts "{type: 'vip', call_uuid, ...}"`  
**And** all connected managers receive desktop notification  
**And** alert is persisted: `LPUSH alerts {json}` for late-joining managers

---

### Requirement: System SHALL cache external API responses

The system SHALL cache external API responses to reduce latency and costs.

#### Scenario: Writing cache on HubSpot lookup

**Given** Dramatiq worker fetches contact from HubSpot  
**When** API returns successful response  
**Then** stores in Redis: `SETEX crm:{caller_id} 3600 "{json}"`  
**And** cache expires after 1 hour (3600 seconds)  
**And** increments metric: `INCR metrics:crm:cache_misses`

#### Scenario: Reading from cache on subsequent call

**Given** caller called within last hour  
**When** CRM lookup task executes  
**Then** checks: `GET crm:{caller_id}`  
**And** if exists, parses JSON and returns immediately  
**And** increments: `INCR metrics:crm:cache_hits`  
**And** avoids HubSpot API call

#### Scenario: Cache invalidation on update

**Given** agent updates contact info in HubSpot during call  
**When** HubSpot webhook fires to `/api/webhooks/crm-update`  
**Then** SvelteKit deletes: `DEL crm:{caller_id}`  
**And** next lookup fetches fresh data

---

### Requirement: System SHALL collect operational metrics

The system SHALL collect and aggregate operational metrics in Redis for monitoring dashboards.

#### Scenario: Tracking call volume over time

**Given** calls are parking throughout the day  
**When** Python processes `CHANNEL_PARK` event  
**Then** increments hourly counter: `INCR metrics:calls:parked:{YYYY-MM-DD-HH}`  
**And** sets expiration to 30 days on counter key  
**And** increments total: `INCR metrics:calls:parked:total`

#### Scenario: Calculating average wait time

**Given** calls transition from parked to assigned  
**When** wait time is computed: `assigned_at - parked_at`  
**Then** adds to time series: `ZADD metrics:wait_times {timestamp} {wait_seconds}`  
**And** trims to keep only last 10,000 samples: `ZREMRANGEBYRANK metrics:wait_times 0 -10001`  
**And** dashboard computes percentiles: p50, p95, p99

#### Scenario: Monitoring AI service health

**Given** Dramatiq workers call OpenAI API  
**When** request completes or fails  
**Then** records latency: `ZADD metrics:openai:latency {timestamp} {ms}`  
**And** increments success/failure: `INCR metrics:openai:{success|failure}`  
**And** calculates error rate: failures / (success + failures)

---

### Requirement: System SHALL track agent availability

The system SHALL track agent availability and current assignments in Redis.

#### Scenario: Agent registration

**Given** an agent's SIP extension registers with FreeSWITCH  
**When** Python receives `REGISTER` event  
**Then** creates agent record:  
```
HSET agent:1001
  extension "1001"
  name "Jane Smith"
  status "available"
  registered_at {timestamp}
  current_call null
```
**And** adds to available set: `SADD agents:available 1001`

#### Scenario: Agent goes busy on call bridge

**Given** a call bridges to agent 1001  
**When** `CHANNEL_BRIDGE` event processed  
**Then** updates atomically:  
```
HSET agent:1001 status "busy" current_call "{uuid}"
SREM agents:available 1001
SADD agents:busy 1001
```
**And** publishes: `PUBLISH agent_updates "{agent_id: 1001, status: 'busy'}"`

#### Scenario: Agent becomes available on hangup

**Given** agent's call ends  
**When** `CHANNEL_HANGUP` event processed  
**Then** updates:  
```
HSET agent:1001 status "available" current_call null
SREM agents:busy 1001
SADD agents:available 1001
```
**And** publishes status change

---

### Requirement: System SHALL configure Redis for data durability

The system SHALL configure Redis for appropriate data durability without sacrificing performance.

#### Scenario: Automatic snapshot backups

**Given** Redis is configured with `save 60 1000`  
**When** 1000 writes occur within 60 seconds  
**Then** Redis creates RDB snapshot to disk  
**And** snapshot file is named `dump.rdb`  
**And** on restart, data is restored from snapshot

#### Scenario: Append-only file for write durability

**Given** Redis is configured with `appendonly yes` and `appendfsync everysec`  
**When** write commands execute (HSET, LPUSH, etc.)  
**Then** commands are appended to AOF file every second  
**And** on crash, at most 1 second of data is lost  
**And** AOF is more durable than RDB snapshots

#### Scenario: Monitoring Redis memory usage

**Given** Redis is running with `maxmemory 2gb`  
**When** memory usage exceeds 1.8GB (90% threshold)  
**Then** Python monitoring script triggers alert  
**And** eviction policy `volatile-lru` removes keys with TTL  
**And** prevents OOM crashes

---

### Requirement: System SHALL support Redis Sentinel for failover

The system SHALL support Redis Sentinel for automatic failover in production.

#### Scenario: Sentinel monitors master

**Given** Redis Sentinel is configured with 3 nodes  
**When** Sentinel checks master health every 1 second  
**And** master fails to respond for 5 seconds  
**Then** Sentinel declares master as down  
**And** initiates automatic failover to replica

#### Scenario: Application reconnects to new master

**Given** Redis master failed over to replica  
**When** Python orchestrator detects connection loss  
**Then** queries Sentinel for new master address  
**And** reconnects to new master within 10 seconds  
**And** resumes normal operation without manual intervention

#### Scenario: Split-brain prevention

**Given** network partition separates master from Sentinels  
**When** Sentinels promote replica to new master  
**Then** old master detects it's in minority partition  
**And** stops accepting writes (read-only mode)  
**And** prevents data conflicts when partition heals
