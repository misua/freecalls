# Capability: Real-time Dashboard

## ADDED Requirements

### Requirement: System SHALL display live call list with auto-refresh

The system SHALL display all active and parked calls in real-time with auto-refresh capabilities.

#### Scenario: Initial page load with SSR

**Given** a manager navigates to `/dashboard`  
**When** SvelteKit server-side handler executes  
**Then** queries Redis: `ZRANGE calls 0 -1 WITHSCORES`  
**And** for each call_uuid, fetches: `HGETALL call:{uuid}`  
**And** renders HTML with initial call list  
**And** page loads within 500ms

#### Scenario: Real-time updates via Server-Sent Events

**Given** dashboard page is loaded in browser  
**When** SvelteKit establishes SSE connection to `/api/call-events`  
**Then** server streams updates whenever Redis publishes to `call_updates` channel  
**And** browser receives JSON events: `{type: 'call_added|call_updated|call_removed', call: {...}}`  
**And** Svelte store updates reactively without full page reload

#### Scenario: Call list sorting by wait time

**Given** multiple calls are parked  
**When** dashboard renders call list  
**Then** calls are ordered by `parked_at` timestamp (oldest first)  
**And** each call displays countdown timer: "Waiting 2m 34s"  
**And** timer updates every second without server round-trip

---

### Requirement: System SHALL allow drag-and-drop call assignment

The system SHALL allow managers to assign calls to agents via intuitive drag-and-drop interface.

#### Scenario: Dragging call card to agent

**Given** a call card is displayed with `draggable="true"`  
**When** manager clicks and drags call card  
**Then** card becomes semi-transparent (opacity: 0.5)  
**And** cursor changes to "move"  
**And** drag preview shows call metadata (caller name, wait time)

#### Scenario: Dropping on agent zone

**Given** a call is being dragged  
**When** manager hovers over agent card  
**Then** agent card highlights with border color change  
**And** when dropped:  
    - Calls SvelteKit API: `POST /api/assign {callUuid, agentId}`  
    - API writes to Redis: `LPUSH cmd:bridge {callUuid}:{agentId}`  
    - Returns success response  
    - UI optimistically updates call status to "Assigning..."

#### Scenario: Handling assignment failure

**Given** manager drops call on agent  
**When** Python executes bridge command but agent is busy  
**Then** ESL returns error: "User busy"  
**And** Python writes: `HSET call:{uuid} error "Agent busy"`  
**And** SSE pushes error to dashboard  
**And** UI reverts call to "Parked" state with error toast

---

### Requirement: System SHALL show comprehensive call information

The system SHALL show comprehensive call information including CRM data, sentiment, and wait time.

#### Scenario: Call card shows caller identity

**Given** CRM lookup completed for call  
**When** dashboard renders call card  
**Then** displays:  
    - Caller name (from CRM or caller_id_name)  
    - Phone number (formatted as +1 (555) 123-4567)  
    - Company name (from CRM)  
    - Profile avatar (from CRM or generic icon)

#### Scenario: Real-time sentiment gauge

**Given** sentiment analysis is running on active call  
**When** sentiment score updates in Redis  
**Then** SSE pushes new score to dashboard  
**And** call card displays gauge: color changes from red (< 0.4) to yellow (0.4-0.7) to green (> 0.7)  
**And** shows latest transcript snippet below gauge

#### Scenario: Wait time warning threshold

**Given** a call has been parked for > 2 minutes  
**When** dashboard evaluates wait time  
**Then** call card border pulses with orange animation  
**And** wait time text turns red  
**And** plays subtle notification sound (if enabled in settings)

---

### Requirement: System SHALL display agent availability and assignments

The system SHALL display agent availability and current call assignments.

#### Scenario: Agent card shows availability

**Given** agents are registered in system  
**When** dashboard loads agent list  
**Then** each agent card shows:  
    - Name and extension  
    - Status: Available (green), Busy (red), Offline (gray)  
    - Current call info if busy (caller name, duration)  
    - Drop zone for call assignment

#### Scenario: Auto-detecting agent status from FreeSWITCH

**Given** Python monitors agent SIP registrations  
**When** agent's extension registers/unregisters  
**Then** Python updates Redis: `HSET agent:{id} status "available|offline"`  
**And** when call bridges to agent: `HSET agent:{id} status "busy", current_call "{uuid}"`  
**And** on hangup: `HSET agent:{id} status "available", current_call null`

#### Scenario: Manual status override

**Given** an agent wants to go on break  
**When** they click status dropdown and select "Break"  
**Then** SvelteKit writes: `HSET agent:{id} status "break"`  
**And** agent card grays out and rejects call drops  
**And** manager sees "On Break" label

---

### Requirement: System SHALL provide search and filter capabilities

The system SHALL provide search and filter capabilities for finding specific calls or agents.

#### Scenario: Searching calls by caller info

**Given** dashboard displays 20+ calls  
**When** manager types "John" in search box  
**Then** call list filters to show only calls where:  
    - Caller name contains "John" (case-insensitive)  
    - OR company name contains "John"  
    - OR phone number contains "John" (partial match)  
**And** filtering happens client-side without server call

#### Scenario: Filtering by sentiment

**Given** sentiment scores are available  
**When** manager clicks "Show frustrated callers only"  
**Then** call list filters to sentiment_score < 0.4  
**And** displays count: "3 frustrated callers"  
**And** filter can be combined with search

#### Scenario: Filtering by wait time

**Given** calls have varying wait times  
**When** manager selects "> 5 minutes" filter  
**Then** only calls with `parked_at` older than 5 minutes ago are shown  
**And** list updates dynamically as calls age past threshold

---

### Requirement: System SHALL provide historical call records

The system SHALL provide historical call records for analysis and quality assurance.

#### Scenario: Viewing completed calls

**Given** manager navigates to `/dashboard/history`  
**When** page loads  
**Then** queries Redis for calls with state="completed" in last 24 hours  
**And** displays paginated list (25 per page)  
**And** each record shows: caller, agent, duration, sentiment, summary

#### Scenario: Playing call recording

**Given** a completed call has recording_path  
**When** manager clicks "Play" button  
**Then** fetches audio file via `/api/recordings/{uuid}`  
**And** displays HTML5 audio player with playback controls  
**And** shows transcript synchronized with audio timestamps

#### Scenario: Exporting call data

**Given** manager selects date range filter  
**When** they click "Export CSV"  
**Then** SvelteKit streams CSV with fields: [timestamp, caller_id, agent_id, duration, sentiment, summary, recording_url]  
**And** download starts automatically  
**And** export is rate-limited to 1 per minute

---

### Requirement: System SHALL push real-time notifications for events

The system SHALL push real-time notifications for important events requiring manager attention.

#### Scenario: VIP caller notification

**Given** a VIP call is detected (from AI engine)  
**When** Python publishes to `manager_alerts` channel  
**Then** SSE pushes to all connected dashboards  
**And** browser shows native desktop notification (if permission granted)  
**And** plays notification sound  
**And** alert banner appears at top of dashboard

#### Scenario: SLA breach warning

**Given** a call wait time exceeds configured threshold (e.g., 5 minutes)  
**When** Python detects breach  
**Then** publishes alert with severity: 'high'  
**And** dashboard displays persistent warning banner until call is assigned  
**And** notification includes quick-assign button with recommended agent

#### Scenario: System health alerts

**Given** Redis connection is lost  
**When** SvelteKit server detects failure  
**Then** displays error banner: "Connection lost. Reconnecting..."  
**And** attempts reconnection every 2 seconds  
**And** shows green banner: "Connected" when restored

---

### Requirement: System SHALL be usable on various devices

The system SHALL be usable on various devices and meet accessibility standards.

#### Scenario: Mobile dashboard view

**Given** manager accesses dashboard on mobile device (< 768px width)  
**When** page loads  
**Then** switches to single-column layout  
**And** drag-and-drop is replaced with "Assign" button opening agent selector  
**And** call cards are stacked vertically  
**And** touch gestures work for scrolling and interaction

#### Scenario: Keyboard navigation

**Given** manager uses keyboard only (no mouse)  
**When** they Tab through interface  
**Then** focus indicators are visible on all interactive elements  
**And** Enter key activates buttons  
**And** Arrow keys navigate call list  
**And** Escape closes modals and dropdowns

#### Scenario: Screen reader compatibility

**Given** manager uses screen reader  
**When** navigating call list  
**Then** each call announces: "Call from {name}, waiting {duration}, sentiment {score}"  
**And** agent status announces: "{name}, {status}"  
**And** ARIA labels are present on all icons and controls
