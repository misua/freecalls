"""
Background tasks for call processing.

Architecture:
- "Write-Back" Actors: Sync call data to CRM after hangup (eventual consistency)
- "Continuous Sync" Actors: Pre-cache CRM data in Redis for fast lookups

Redis Namespaces:
- phone:{number} -> {customer_json} (Static CRM cache, updated by cron)
- call:{uuid} -> {live_state_json} (Ephemeral call state, deleted after hangup)

This creates clean separation:
- ESL Listener (Hot Path) = Fast Redis reads, no API calls
- Dramatiq Workers (Slow Path) = API calls, retries, rate limiting
"""
import os
import json
import time
import logging
import redis
import dramatiq
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Redis client for task communication
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

# CRM Configuration (TODO: Move to environment variables)
CRM_API_KEY = os.getenv('HUBSPOT_API_KEY', '')
CRM_ENABLED = bool(CRM_API_KEY)


# ============================================================================
# WRITE-BACK ACTOR: Post-Call CRM Sync
# ============================================================================

@dramatiq.actor(max_retries=3, min_backoff=1000, max_backoff=30000)
def sync_call_to_crm(call_uuid: str, caller_id: str, agent_id: str, duration: int, 
                      disposition: str = 'completed', recording_url: str = '') -> bool:
    """
    Sync basic call log to CRM (Write-Back Pattern).
    
    CRMs only need basic call logging:
    - Duration
    - Who handled it (agent/owner)
    - Disposition (completed, no answer, etc.)
    - Recording URL (if needed)
    
    All other metadata (conferences, transfers, supervisor monitoring, etc.)
    stays in our analytics system - CRMs can't handle that level of detail.
    
    Args:
        call_uuid: Call identifier (for our reference)
        caller_id: Phone number
        agent_id: Agent who handled the call
        duration: Call duration in seconds
        disposition: Call outcome (completed, abandoned, etc.)
        recording_url: Optional recording URL
    
    Returns:
        True if sync succeeded
    """
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    if not CRM_ENABLED:
        logger.info(f"CRM disabled, skipping sync for {call_uuid}")
        return False
    
    logger.info(f"Syncing call {call_uuid} to CRM (simple log only)")
    
    try:
        # Get contact_id from pre-cached phone lookup
        contact_cache = r.get(f'phone:{caller_id}')
        contact_id = None
        if contact_cache:
            contact_data = json.loads(contact_cache)
            contact_id = contact_data.get('id')
        else:
            logger.warning(f"No CRM contact found for {caller_id}, skipping sync")
            return False
        
        # TODO: Implement actual CRM API call
        # Keep it simple - CRMs just want basic call logging:
        # 
        # HubSpot example:
        # api_url = "https://api.hubspot.com/crm/v3/objects/calls"
        # payload = {
        #     "properties": {
        #         "hs_call_duration": duration,
        #         "hs_call_to_number": caller_id,
        #         "hubspot_owner_id": agent_id,
        #         "hs_call_disposition": disposition
        #     },
        #     "associations": [
        #         {"to": {"id": contact_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED"}]}
        #     ]
        # }
        # response = requests.post(api_url, json=payload, headers={'Authorization': f'Bearer {CRM_API_KEY}'})
        # response.raise_for_status()
        
        # Simulate API call
        time.sleep(0.3)
        
        logger.info(f"CRM sync complete for {call_uuid}: {duration}s call with {contact_id}")
        
        # Mark as synced
        r.hset(f'call:{call_uuid}', 'crm_synced', '1')
        r.hset(f'call:{call_uuid}', 'crm_synced_at', int(time.time()))
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to sync call {call_uuid} to CRM: {e}")
        raise


# ============================================================================
# CONTINUOUS SYNC ACTOR: Pre-Cache CRM Data
# ============================================================================

@dramatiq.actor(max_retries=5, min_backoff=2000, max_backoff=60000)
def cron_pull_crm_updates(delta_minutes: int = 10) -> int:
    """
    Continuous sync to keep Redis "warm" with CRM data (Pre-Cache Pattern).
    
    Strategy: Pull contacts modified in last N minutes (delta sync, not full sync).
    
    This runs periodically (every 5-10 minutes) to:
    1. Query CRM for recently modified contacts
    2. Update phone:{number} keys in Redis
    3. Keep cache fresh without overwhelming CRM API
    
    Args:
        delta_minutes: Look back window for modified contacts
    
    Returns:
        Number of contacts synced
    """
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    if not CRM_ENABLED:
        logger.info("CRM disabled, skipping continuous sync")
        return 0
    
    logger.info(f"Starting CRM delta sync (last {delta_minutes} minutes)")
    
    try:
        # TODO: Implement actual CRM API query
        # Example for HubSpot (contacts modified in last N minutes):
        # since_timestamp = int(time.time() - (delta_minutes * 60)) * 1000
        # api_url = f"https://api.hubspot.com/crm/v3/objects/contacts"
        # params = {
        #     "properties": "firstname,lastname,phone,email,lifecyclestage,hs_lead_status",
        #     "updatedSince": since_timestamp,
        #     "limit": 100
        # }
        # response = requests.get(api_url, params=params, headers=HEADERS)
        # contacts = response.json().get('results', [])
        
        # Simulate API response
        time.sleep(0.5)
        contacts = [
            {
                'id': '12345',
                'properties': {
                    'firstname': 'John',
                    'lastname': 'Doe',
                    'phone': '5551234567',
                    'email': 'john@example.com',
                    'lifecyclestage': 'customer',
                    'hs_lead_status': 'OPEN'
                }
            }
        ]
        
        synced_count = 0
        for contact in contacts:
            contact_id = contact.get('id')
            props = contact.get('properties', {})
            phone = props.get('phone', '').replace('-', '').replace(' ', '')
            
            if not phone:
                continue
            
            # Build cached contact data
            cached_contact = {
                'id': contact_id,
                'name': f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
                'email': props.get('email', ''),
                'phone': phone,
                'lifecycle_stage': props.get('lifecyclestage', 'unknown'),
                'status': props.get('hs_lead_status', 'unknown'),
                'cached_at': int(time.time())
            }
            
            # Store in Redis with 24-hour TTL
            cache_key = f'phone:{phone}'
            r.setex(cache_key, 86400, json.dumps(cached_contact))
            
            synced_count += 1
            logger.debug(f"Cached contact: {phone} -> {cached_contact['name']}")
        
        logger.info(f"CRM delta sync completed: {synced_count} contacts updated")
        
        # Store metrics
        r.hincrby('metrics:crm_sync', 'total_syncs', 1)
        r.hincrby('metrics:crm_sync', 'total_contacts', synced_count)
        r.hset('metrics:crm_sync', 'last_sync', int(time.time()))
        
        return synced_count
        
    except Exception as e:
        logger.error(f"CRM delta sync failed: {e}")
        # Dramatiq will retry automatically
        raise


# ============================================================================
# HELPER: Fast CRM Lookup (Called from Orchestrator)
# ============================================================================

def fast_crm_lookup(r: redis.Redis, caller_id: str) -> Optional[Dict[str, Any]]:
    """
    Fast CRM lookup using pre-cached data (HOT PATH - not a Dramatiq actor).
    
    This is called by the orchestrator on CHANNEL_PARK for instant screen pop.
    NO API calls - pure Redis read.
    
    Args:
        r: Redis connection
        caller_id: Phone number to look up
    
    Returns:
        Cached contact data or None
    """
    cache_key = f'phone:{caller_id}'
    cached_data = r.get(cache_key)
    
    if cached_data:
        logger.info(f"Fast CRM hit for {caller_id}")
        return json.loads(cached_data)
    else:
        logger.info(f"Fast CRM miss for {caller_id}")
        return None


@dramatiq.actor(max_retries=1, time_limit=30000)
def analyze_sentiment(call_uuid: str, audio_chunk_path: str) -> Optional[Dict[str, float]]:
    """
    Analyze sentiment from audio chunk.
    
    This task:
    1. Transcribes audio with Whisper (local or API)
    2. Analyzes sentiment with local LLM
    3. Updates Redis with score
    4. Publishes update for dashboard
    
    Args:
        call_uuid: Unique call identifier
        audio_chunk_path: Path to audio file to analyze
    
    Returns:
        Sentiment data with score and emotion
    """
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    logger.info(f"Analyzing sentiment for call {call_uuid}, chunk: {audio_chunk_path}")
    
    # TODO: Implement actual sentiment analysis
    # For now, return mock data
    time.sleep(1)  # Simulate processing
    
    sentiment_data = {
        'score': 0.7,  # 0.0 = negative, 1.0 = positive
        'emotion': 'neutral',
        'timestamp': int(time.time())
    }
    
    # Update Redis
    r.hset(f'call:{call_uuid}', 'sentiment_score', sentiment_data['score'])
    r.hset(f'call:{call_uuid}', 'emotion', sentiment_data['emotion'])
    
    # Publish event
    r.publish('call_events', json.dumps({
        'event': 'sentiment_updated',
        'data': {
            'call_uuid': call_uuid,
            'score': sentiment_data['score'],
            'emotion': sentiment_data['emotion']
        }
    }))
    
    # Alert if low sentiment
    if sentiment_data['score'] < 0.3:
        r.publish('call_events', json.dumps({
            'event': 'low_sentiment_alert',
            'data': {
                'call_uuid': call_uuid,
                'score': sentiment_data['score'],
                'emotion': sentiment_data['emotion']
            }
        }))
        logger.warning(f"Low sentiment detected for call {call_uuid}: {sentiment_data['score']}")
    
    return sentiment_data


@dramatiq.actor(max_retries=1, time_limit=120000)
def generate_summary(call_uuid: str, recording_path: str) -> Optional[str]:
    """
    Generate AI-powered call summary after call ends.
    
    This task:
    1. Transcribes full recording with Whisper
    2. Analyzes with local LLM
    3. Extracts action items
    4. Stores summary in Redis
    
    Args:
        call_uuid: Unique call identifier
        recording_path: Path to full call recording
    
    Returns:
        Summary text
    """
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    logger.info(f"Generating summary for call {call_uuid}")
    
    # TODO: Implement actual summarization
    time.sleep(2)  # Simulate processing
    
    summary = f"Call summary for {call_uuid}: Customer inquiry resolved successfully."
    action_items = [
        {"task": "Follow up in 3 days", "priority": "medium", "owner": "agent"},
        {"task": "Send documentation", "priority": "high", "owner": "agent"}
    ]
    
    # Store in Redis
    r.hset(f'call:{call_uuid}', 'summary', summary)
    r.hset(f'call:{call_uuid}', 'action_items', json.dumps(action_items))
    
    # Publish event
    r.publish('call_events', json.dumps({
        'event': 'summary_generated',
        'data': {
            'call_uuid': call_uuid,
            'summary': summary,
            'action_items': action_items
        }
    }))
    
    logger.info(f"Summary generated for call {call_uuid}")
    return summary


@dramatiq.actor(max_retries=2, min_backoff=2000)
def predict_routing(call_uuid: str) -> Optional[list]:
    """
    Predict best agents for routing based on historical data.
    
    This task:
    1. Loads call context (CRM, sentiment, issue)
    2. Queries product knowledge base
    3. Runs ML model for routing prediction
    4. Returns top 3 recommended agents
    
    Args:
        call_uuid: Unique call identifier
    
    Returns:
        List of recommended agent IDs with confidence scores
    """
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    logger.info(f"Predicting routing for call {call_uuid}")
    
    # Get call context
    call_data = r.hgetall(f'call:{call_uuid}')
    
    # TODO: Implement actual routing prediction
    time.sleep(0.5)
    
    # Mock recommendations
    recommendations = [
        {'agent_id': '1000', 'confidence': 0.92, 'reason': 'Technical expert'},
        {'agent_id': '1001', 'confidence': 0.85, 'reason': 'Available and experienced'},
        {'agent_id': '1002', 'confidence': 0.78, 'reason': 'Customer relationship history'}
    ]
    
    # Store recommendations
    r.hset(f'call:{call_uuid}', 'recommended_agents', json.dumps(recommendations))
    
    # Publish event
    r.publish('call_events', json.dumps({
        'event': 'routing_predicted',
        'data': {
            'call_uuid': call_uuid,
            'recommendations': recommendations
        }
    }))
    
    logger.info(f"Routing predicted for call {call_uuid}: {recommendations}")
    return recommendations


# ============================================================================
# ANALYTICS/REPORTING: Store detailed call data for internal reporting
# ============================================================================

@dramatiq.actor(max_retries=1)
def store_call_analytics(call_uuid: str, analytics_data: Dict[str, Any]) -> bool:
    """
    Store detailed call analytics for internal reporting/dashboards.
    
    This is where ALL the telephony metadata goes:
    - Multi-leg call details (conferences, transfers)
    - Supervisor monitoring/eavesdropping
    - Call quality metrics
    - Agent performance data
    - Queue wait times
    - Customer satisfaction scores
    
    This data goes to TimescaleDB for long-term analytics/reporting,
    NOT in the CRM (CRMs don't need this level of detail).
    
    Args:
        call_uuid: Call identifier
        analytics_data: Complete call metadata
    
    Returns:
        True if stored successfully
    """
    from orchestrator.db import insert_call_analytics
    
    logger.info(f"Storing analytics for call {call_uuid} in TimescaleDB")
    
    try:
        # Convert timestamps to proper format
        from datetime import datetime
        
        def parse_timestamp(ts):
            """Convert Unix timestamp to datetime if needed"""
            if not ts:
                return None
            try:
                if isinstance(ts, str):
                    return datetime.fromtimestamp(int(ts))
                elif isinstance(ts, (int, float)):
                    return datetime.fromtimestamp(ts)
                return ts
            except (ValueError, TypeError):
                return None
        
        # Prepare data for TimescaleDB insertion
        db_record = {
            'caller_id': analytics_data.get('caller_id'),
            'agent_id': analytics_data.get('agent_id'),
            'duration': int(analytics_data.get('duration', 0)),
            'wait_time': int(analytics_data.get('wait_time', 0)),
            'status': analytics_data.get('status', 'completed'),
            
            # Multi-leg call data
            'conference_room': analytics_data.get('conference_room', ''),
            'conference_participants': str(analytics_data.get('conference_participants', '')),
            
            # Supervisor activity
            'supervisor_id': analytics_data.get('supervisor_id', ''),
            
            # Call quality
            'recording_path': analytics_data.get('recording_path', ''),
            
            # Timestamps (convert to datetime)
            'parked_at': parse_timestamp(analytics_data.get('parked_at')),
            'bridged_at': parse_timestamp(analytics_data.get('bridged_at')),
            'ended_at': parse_timestamp(analytics_data.get('ended_at')) or datetime.now()
        }
        
        # Insert into TimescaleDB
        success = insert_call_analytics(call_uuid, db_record)
        
        if success:
            logger.info(f"Analytics stored in TimescaleDB for call {call_uuid}")
        else:
            logger.warning(f"Failed to store analytics for call {call_uuid}")
        
        return success
        
    except Exception as e:
        logger.error(f"Failed to store analytics for {call_uuid}: {e}")
        # Don't raise - this is non-critical, log the error and continue
        return False


# ============================================================================
# PERIODIC SCHEDULER: Trigger continuous sync every N minutes
# ============================================================================

@dramatiq.actor
def schedule_crm_sync():
    """
    Self-scheduling task to trigger continuous CRM sync.
    
    This actor calls itself recursively to maintain periodic sync.
    Alternative: Use APScheduler or cron for production.
    """
    import gevent
    
    logger.info("Scheduling next CRM sync in 10 minutes")
    
    # Trigger the sync
    cron_pull_crm_updates.send(delta_minutes=10)
    
    # Schedule next run (10 minutes = 600 seconds)
    gevent.spawn_later(600, lambda: schedule_crm_sync.send())