# Capability: FreeSWITCH Orchestration

## ADDED Requirements

### Requirement: System SHALL provide containerized FreeSWITCH deployment

The system SHALL provide a reproducible FreeSWITCH deployment using Docker containers with proper network configuration and volume management.

#### Scenario: Developer starts local environment

**Given** a developer has Docker installed  
**When** they run `docker-compose up freeswitch`  
**Then** FreeSWITCH starts with ESL enabled on port 8021  
**And** SIP profiles are loaded from mounted configuration  
**And** recordings directory is persisted to host filesystem

#### Scenario: Production deployment with host networking

**Given** a production server with Docker  
**When** FreeSWITCH container starts with `network_mode: host`  
**Then** RTP media ports (16384-32768) are directly accessible  
**And** no NAT traversal issues occur  
**And** SIP signaling on port 5060 is available

---

### Requirement: System SHALL maintain persistent ESL connection

The system SHALL maintain a persistent ESL connection from Python to FreeSWITCH for programmatic call control.

#### Scenario: Python connects to ESL on startup

**Given** FreeSWITCH is running with ESL enabled  
**When** the Python orchestrator starts  
**Then** it connects to `localhost:8021` with configured password  
**And** subscribes to `CHANNEL_PARK`, `CHANNEL_BRIDGE`, `CHANNEL_HANGUP` events  
**And** maintains connection with automatic reconnection on failure

#### Scenario: Handling ESL disconnection

**Given** an active ESL connection  
**When** FreeSWITCH restarts or network interruption occurs  
**Then** Python detects connection loss within 5 seconds  
**And** attempts reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s)  
**And** logs reconnection attempts with WARNING level  
**And** successfully resumes event processing after reconnection

---

### Requirement: System SHALL park incoming calls and enable retrieval

The system SHALL park incoming calls immediately and provide mechanisms for programmatic retrieval and bridging.

#### Scenario: Inbound call automatically parks

**Given** a caller dials the main number  
**When** FreeSWITCH receives the SIP INVITE  
**Then** the dialplan executes `park()` application  
**And** emits a `CHANNEL_PARK` event with call_uuid  
**And** the caller hears hold music

#### Scenario: Python retrieves parked call details

**Given** a `CHANNEL_PARK` event is received via ESL  
**When** Python parses the event payload  
**Then** it extracts `call_uuid`, `caller_id_number`, `caller_id_name`  
**And** retrieves additional variables: `sip_from_uri`, `sip_to_uri`, `sip_call_id`

#### Scenario: Bridging parked call to agent

**Given** a call with UUID `abc-123` is parked  
**When** Python executes `uuid_bridge abc-123 sofia/internal/1001@domain`  
**Then** FreeSWITCH bridges the call to agent extension 1001  
**And** emits a `CHANNEL_BRIDGE` event  
**And** both parties can hear each other

---

### Requirement: System SHALL record calls with organized metadata

The system SHALL record calls to disk with organized file naming and metadata.

#### Scenario: Automatic recording on bridge

**Given** a call is bridged to an agent  
**When** the `CHANNEL_BRIDGE` event is processed  
**Then** Python executes `uuid_record abc-123 /recordings/${uuid}_${timestamp}.wav`  
**And** recording starts immediately  
**And** file path is stored in Redis for later retrieval

#### Scenario: Recording stops on hangup

**Given** a call is being recorded  
**When** either party hangs up  
**Then** FreeSWITCH finalizes the WAV file  
**And** Python receives `CHANNEL_HANGUP` event  
**And** recording duration is calculated and stored

---

### Requirement: System SHALL provide maintainable dialplan configuration

The system SHALL provide maintainable XML dialplan configuration for routing logic.

#### Scenario: Loading custom dialplan on startup

**Given** dialplan XML files exist in `./freeswitch/conf/dialplan/`  
**When** FreeSWITCH container starts  
**Then** all XML files are parsed and loaded  
**And** errors in XML syntax are logged to console  
**And** FreeSWITCH exits with non-zero code if dialplan is invalid

#### Scenario: Reloading dialplan without restart

**Given** FreeSWITCH is running  
**When** dialplan XML is modified on disk  
**And** Python executes ESL command `reloadxml`  
**Then** FreeSWITCH reloads configuration without dropping active calls  
**And** new calls use updated dialplan

---

### Requirement: System SHALL support configurable SIP profiles

The system SHALL support configurable SIP profiles for internal and external communication.

#### Scenario: Internal profile for agent extensions

**Given** `conf/sip_profiles/internal.xml` defines internal profile  
**When** FreeSWITCH starts  
**Then** profile binds to port 5060  
**And** accepts registrations from 192.168.0.0/16 without authentication  
**And** agents can register with softphones

#### Scenario: External profile for carrier trunks

**Given** `conf/sip_profiles/external.xml` defines external profile  
**When** FreeSWITCH starts  
**Then** profile binds to public IP on port 5080  
**And** requires authentication for INVITE  
**And** applies ACL rules to prevent abuse
