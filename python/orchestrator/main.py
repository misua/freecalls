# CRITICAL: Monkey patch ALL gevent operations FIRST before any other imports
# This fixes DNS resolution in greenlets for Redis connections
from gevent import monkey
monkey.patch_all()

import sys
import os

# CRITICAL: Add /app to Python path so workers module can be imported
sys.path.insert(0, '/app')

import time
import json
import redis
import gevent
from greenswitch import InboundESL
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
FREESWITCH_HOST = os.getenv('FREESWITCH_HOST', 'localhost')
FREESWITCH_PORT = int(os.getenv('FREESWITCH_PORT', '8021'))
ESL_PASSWORD = os.getenv('ESL_PASSWORD', 'ClueCon')

# Redis client will be initialized in main()
redis_client = None

def sync_registrations(esl):
    """Periodically sync registration status from FreeSWITCH to Redis"""
    logger.info("Starting registration sync task...")
    
    while True:
        try:
            gevent.sleep(30)  # Sync every 30 seconds
            
            r = redis.from_url(REDIS_URL, decode_responses=True)
            
            # Get previously known registrations
            previous_registrations = set()
            for key in r.scan_iter('user:*:registered'):
                username = key.split(':')[1]
                previous_registrations.add(username)
            
            # Get current registrations from FreeSWITCH
            response = esl.send('api show registrations')
            if not hasattr(response, 'data'):
                continue
                
            registrations = response.data.strip().split('\n')
            registered_users = set()
            
            for line in registrations:
                if line and line[0].isdigit():
                    parts = line.split(',')
                    if parts and parts[0].isdigit():
                        username = parts[0]
                        registered_users.add(username)
                        # Refresh TTL to 120 seconds
                        r.setex(f'user:{username}:registered', 120, '1')
            
            # Detect newly registered users
            newly_registered = registered_users - previous_registrations
            for username in newly_registered:
                logger.info(f"Sync detected new registration: {username}")
                r.publish('call_events', json.dumps({
                    'event': 'user_registered',
                    'data': {'user_id': username}
                }))
            
            # Detect newly unregistered users
            newly_unregistered = previous_registrations - registered_users
            for username in newly_unregistered:
                logger.info(f"Sync detected unregistration: {username}")
                r.publish('call_events', json.dumps({
                    'event': 'user_unregistered',
                    'data': {'user_id': username}
                }))
            
            logger.info(f"Synced {len(registered_users)} registrations: {', '.join(sorted(registered_users))}")
            
        except Exception as e:
            logger.error(f"Error syncing registrations: {e}")
            gevent.sleep(5)

def handle_park_event(event):
    """Handle CHANNEL_PARK events - when a call is parked"""
    call_uuid = event.headers.get('Unique-ID')
    caller_id = event.headers.get('Caller-Caller-ID-Number', 'Unknown')
    caller_name = event.headers.get('Caller-Caller-ID-Name', 'Unknown')
    
    logger.info(f"Call parked: {call_uuid} from {caller_name} <{caller_id}>")
    
    # Create fresh Redis connection for this greenlet
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    # ========================================
    # HOT PATH: Fast CRM lookup (Redis only)
    # ========================================
    # Check pre-cached contact data (phone:{number} namespace)
    # This is INSTANT - no API calls, no blocking
    contact_name = caller_name
    contact_data = None
    crm_id = None
    
    cache_key = f'phone:{caller_id}'
    cached_contact = r.get(cache_key)
    if cached_contact:
        contact_data = json.loads(cached_contact)
        contact_name = contact_data.get('name', caller_name)
        crm_id = contact_data.get('id')
        logger.info(f"Fast CRM hit for {caller_id}: {contact_name} (ID: {crm_id})")
    else:
        logger.info(f"Fast CRM miss for {caller_id} - using ANI only")
    
    # Store call in ephemeral namespace (call:{uuid})
    call_data = {
        'uuid': call_uuid,
        'caller_id': caller_id,
        'caller_name': contact_name,  # Use CRM name if found
        'status': 'parked',
        'parked_at': int(time.time())
    }
    
    # Add CRM metadata if found
    if crm_id:
        call_data['crm_id'] = crm_id
        call_data['crm_cached'] = '1'
        if contact_data:
            call_data['lifecycle_stage'] = contact_data.get('lifecycle_stage', 'unknown')
            call_data['email'] = contact_data.get('email', '')
    
    r.hset(f'call:{call_uuid}', mapping=call_data)
    r.zadd('calls:parked', {call_uuid: time.time()})
    
    # Publish to dashboard (with enriched name)
    r.publish('call_events', json.dumps({
        'event': 'call_parked',
        'data': call_data
    }))
    
    logger.info(f"Stored call {call_uuid} in Redis")
    
    # ========================================
    # SLOW PATH: Enqueue background tasks
    # ========================================
    # These run asynchronously and won't block the hot path
    try:
        from workers.tasks import predict_routing
        
        # If we have CRM data, predict best routing
        if crm_id:
            try:
                logger.info(f"Enqueueing routing prediction for {call_uuid}")
                predict_routing.send(call_uuid)
            except Exception as routing_err:
                logger.warning(f"Could not enqueue routing prediction: {routing_err}")
        
    except Exception as e:
        logger.error(f"Error enqueueing background tasks: {e}")
        # Don't fail the call if background tasks fail to enqueue

def handle_hangup_event(event):
    """Handle CHANNEL_HANGUP events"""
    call_uuid = event.headers.get('Unique-ID')
    
    logger.info(f"Call hangup: {call_uuid}")
    
    # Create fresh Redis connection for this greenlet
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    # Get call data
    call_data = r.hgetall(f'call:{call_uuid}')
    is_original_call = bool(call_data and call_data.get('caller_id'))
    
    # ========================================
    # PART 1: Handle original call cleanup
    # ========================================
    if is_original_call:
        agent_id = call_data.get('agent_id')
        
        # Check if this call is in a conference
        if call_data.get('status') == 'conference':
            conference_room = call_data.get('conference_room')
            logger.info(f"Call {call_uuid} in conference {conference_room}, checking remaining participants")
            
            # Check if ANY agent legs are still active in this conference
            has_active_participants = False
            for agent_key in r.scan_iter('agent:*:active_call'):
                agent_data = r.hgetall(agent_key)
                if agent_data.get('conference_room') == conference_room:
                    has_active_participants = True
                    break
            
            if has_active_participants:
                logger.info(f"Conference {conference_room} still has active participants, skipping cleanup")
                return
            
            # All participants left - cleanup everything
            logger.info(f"Conference {conference_room} ended, cleaning up call and agents")
        
        # Calculate call duration
        bridged_at = call_data.get('bridged_at')
        duration = 0
        if bridged_at:
            try:
                duration = int(time.time()) - int(bridged_at)
            except ValueError:
                pass
        
        # Update call status
        r.hset(f'call:{call_uuid}', 'status', 'ended')
        r.hset(f'call:{call_uuid}', 'ended_at', int(time.time()))
        r.hset(f'call:{call_uuid}', 'duration', duration)
        r.zrem('calls:parked', call_uuid)
        r.expire(f'call:{call_uuid}', 300)  # 5 minute TTL
        
        # Enqueue analytics (unless already enqueued by conference cleanup)
        if not call_data.get('analytics_enqueued'):
            try:
                from workers.tasks import sync_call_to_crm, store_call_analytics
                
                caller_id = call_data.get('caller_id')
                parked_at = call_data.get('parked_at')
                wait_time = 0
                if parked_at and bridged_at:
                    try:
                        wait_time = int(bridged_at) - int(parked_at)
                    except ValueError:
                        pass
                
                # Determine call status
                if agent_id and duration > 0:
                    status = 'completed'
                elif agent_id:
                    status = 'abandoned'
                else:
                    status = 'missed'
                
                analytics_data = {
                    'caller_id': caller_id,
                    'agent_id': agent_id or '',
                    'duration': duration,
                    'wait_time': wait_time,
                    'status': status,
                    'conference_room': call_data.get('conference_room', ''),
                    'conference_participants': call_data.get('conference_participants', ''),
                    'supervisor_id': call_data.get('supervisor_id', ''),
                    'recording_path': call_data.get('recording_path', ''),
                    'parked_at': parked_at,
                    'bridged_at': bridged_at,
                    'ended_at': int(time.time())
                }
                
                logger.info(f"Enqueueing analytics storage for call {call_uuid} (status: {status})")
                store_call_analytics.send(call_uuid, analytics_data)
                
                if agent_id and duration > 0:
                    logger.info(f"Enqueueing CRM sync for call {call_uuid}")
                    sync_call_to_crm.send(
                        call_uuid=call_uuid,
                        caller_id=caller_id,
                        agent_id=agent_id,
                        duration=duration,
                        disposition='completed',
                        recording_url=call_data.get('recording_path', '')
                    )
            except Exception as e:
                logger.error(f"Error enqueueing background tasks: {e}")
        else:
            logger.info(f"Analytics already enqueued for call {call_uuid}, skipping duplicate")
        
        # Clear agent if non-conference call
        if agent_id and not call_data.get('conference_room'):
            r.delete(f'agent:{agent_id}:active_call')
            r.publish('call_events', json.dumps({
                'event': 'agent_available',
                'data': {'agent_id': agent_id}
            }))
    
    # ========================================
    # PART 2: Handle agent leg cleanup (for ALL hangups)
    # ========================================
    for agent_key in r.scan_iter('agent:*:active_call'):
        agent_data = r.hgetall(agent_key)
        
        # Check if this UUID matches this agent's conference leg
        if agent_data.get('agent_uuid') == call_uuid:
            agent_num = agent_key.split(':')[1]
            conference_room = agent_data.get('conference_room')
            
            if conference_room:
                logger.info(f"Agent {agent_num}'s conference leg ended (UUID: {call_uuid}), conference: {conference_room}")
                r.delete(agent_key)
                r.publish('call_events', json.dumps({
                    'event': 'agent_available',
                    'data': {'agent_id': agent_num}
                }))
                
                # Check if conference is now empty
                remaining_participants = 0
                for check_key in r.scan_iter('agent:*:active_call'):
                    check_data = r.hgetall(check_key)
                    if check_data.get('conference_room') == conference_room:
                        remaining_participants += 1
                
                if remaining_participants == 0:
                    logger.info(f"Conference {conference_room} is now empty, cleaning up all related calls")
                    for call_key in r.scan_iter('call:*'):
                        call_check_data = r.hgetall(call_key)
                        if call_check_data.get('conference_room') == conference_room:
                            call_check_uuid = call_check_data.get('uuid')
                            logger.info(f"Cleaning up conference call {call_check_uuid}")
                            
                            # Enqueue analytics BEFORE cleanup
                            try:
                                from workers.tasks import store_call_analytics
                                
                                # Calculate metrics
                                bridged_at = call_check_data.get('bridged_at')
                                parked_at = call_check_data.get('parked_at')
                                duration = 0
                                wait_time = 0
                                
                                if bridged_at:
                                    try:
                                        duration = int(time.time()) - int(bridged_at)
                                    except ValueError:
                                        pass
                                
                                if parked_at and bridged_at:
                                    try:
                                        wait_time = int(bridged_at) - int(parked_at)
                                    except ValueError:
                                        pass
                                
                                # Determine status
                                agent_id = call_check_data.get('agent_id')
                                if agent_id and duration > 0:
                                    status = 'completed'
                                elif agent_id:
                                    status = 'abandoned'
                                else:
                                    status = 'missed'
                                
                                analytics_data = {
                                    'caller_id': call_check_data.get('caller_id'),
                                    'agent_id': agent_id or '',
                                    'duration': duration,
                                    'wait_time': wait_time,
                                    'status': status,
                                    'conference_room': conference_room,
                                    'conference_participants': call_check_data.get('conference_participants', ''),
                                    'supervisor_id': call_check_data.get('supervisor_id', ''),
                                    'recording_path': call_check_data.get('recording_path', ''),
                                    'parked_at': parked_at,
                                    'bridged_at': bridged_at,
                                    'ended_at': int(time.time())
                                }
                                
                                logger.info(f"Conference analytics data: participants={analytics_data['conference_participants']}, supervisor={analytics_data['supervisor_id']}")
                                logger.info(f"Enqueueing analytics for conference call {call_check_uuid} (status: {status})")
                                store_call_analytics.send(call_check_uuid, analytics_data)
                            except Exception as e:
                                logger.error(f"Error enqueueing analytics for conference cleanup: {e}")
                            
                            # Now cleanup - mark analytics as already enqueued
                            r.hset(call_key, 'status', 'ended')
                            r.hset(call_key, 'ended_at', int(time.time()))
                            r.hset(call_key, 'analytics_enqueued', '1')  # Prevent double-enqueueing
                            r.expire(call_key, 300)
                            r.publish('call_events', json.dumps({
                                'event': 'call_ended',
                                'data': {'uuid': call_check_uuid}
                            }))
            else:
                # Non-conference agent leg
                logger.info(f"Clearing active call for agent {agent_num} (UUID: {call_uuid})")
                r.delete(agent_key)
                r.publish('call_events', json.dumps({
                    'event': 'agent_available',
                    'data': {'agent_id': agent_num}
                }))
    
    r.publish('call_events', json.dumps({
        'event': 'call_ended',
        'data': {'uuid': call_uuid}
    }))

def handle_registration_event(event):
    """Handle CUSTOM sofia::register/unregister events for tracking user registrations"""
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        
        event_subclass = event.headers.get('Event-Subclass')
        username = event.headers.get('from-user')
        
        if not username:
            return
            
        if event_subclass == 'sofia::register':
            contact = event.headers.get('contact')
            # Store registration with TTL of 120 seconds (double the typical registration interval)
            r.setex(f'user:{username}:registered', 120, '1')
            logger.info(f"User {username} registered: {contact}")
            
            # Publish registration event
            r.publish('call_events', json.dumps({
                'event': 'user_registered',
                'data': {'user_id': username}
            }))
        elif event_subclass == 'sofia::unregister':
            r.delete(f'user:{username}:registered')
            logger.info(f"User {username} unregistered")
            
            # Publish unregistration event
            r.publish('call_events', json.dumps({
                'event': 'user_unregistered',
                'data': {'user_id': username}
            }))
    except Exception as e:
        logger.error(f"Error in handle_registration_event: {e}")

def handle_bridge_event(event):
    """Handle CHANNEL_BRIDGE events"""
    call_uuid = event.headers.get('Unique-ID')
    other_uuid = event.headers.get('Other-Leg-Unique-ID')
    
    # Get destination number to identify which agent
    dest_number = event.headers.get('Caller-Destination-Number', '')
    caller_number = event.headers.get('Caller-Caller-ID-Number', '')
    
    logger.info(f"Call bridged: {call_uuid} <-> {other_uuid}, caller: {caller_number}, agent: {dest_number}")
    
    try:
        # Create fresh Redis connection for this greenlet
        r = redis.from_url(REDIS_URL, decode_responses=True)
        
        # Get original call data
        call_data = r.hgetall(f'call:{call_uuid}')
        logger.info(f"Retrieved call data for {call_uuid}: {call_data}")
        
        # Check if this is a transfer (call already had an agent)
        old_agent_id = call_data.get('agent_id')
        if old_agent_id and old_agent_id != dest_number:
            # This is a transfer - clear old agent's active call
            logger.info(f"Transfer detected: {old_agent_id} -> {dest_number}")
            r.delete(f'agent:{old_agent_id}:active_call')
            
            # Publish agent available event
            r.publish('call_events', json.dumps({
                'event': 'agent_available',
                'data': {'agent_id': old_agent_id}
            }))
        
        # Update call status
        r.hset(f'call:{call_uuid}', 'status', 'bridged')
        r.hset(f'call:{call_uuid}', 'bridged_at', int(time.time()))
        r.hset(f'call:{call_uuid}', 'bridged_to', other_uuid)
        r.hset(f'call:{call_uuid}', 'agent_id', dest_number)
        r.zrem('calls:parked', call_uuid)
        
        # Store active call for new agent
        agent_call_data = {
            'call_uuid': call_uuid,
            'caller_number': call_data.get('caller_number', caller_number),
            'caller_name': call_data.get('caller_name', caller_number),
            'bridged_at': int(time.time())
        }
        r.hset(f'agent:{dest_number}:active_call', mapping=agent_call_data)
        logger.info(f"Set active call for agent {dest_number}: {agent_call_data}")
        
        # Verify it was written
        verify = r.hgetall(f'agent:{dest_number}:active_call')
        logger.info(f"Verified agent:{dest_number}:active_call = {verify}")
        
        r.publish('call_events', json.dumps({
            'event': 'call_bridged',
            'data': {
                'uuid': call_uuid,
                'agent_id': dest_number,
                'caller_number': call_data.get('caller_number', caller_number),
                'caller_name': call_data.get('caller_name', caller_number),
                'bridged_at': int(time.time())
            }
        }))
        logger.info(f"Published call_bridged event for agent {dest_number}")
        
    except Exception as e:
        logger.error(f"Error in handle_bridge_event: {e}", exc_info=True)

def process_bridge_commands(esl):
    """Process bridge commands from Redis queue"""
    logger.info("Starting bridge command processor...")
    
    while True:
        try:
            # Create fresh Redis connection for this greenlet
            r = redis.from_url(REDIS_URL, decode_responses=True)
            
            # Blocking pop with 1 second timeout
            result = r.blpop('cmd:bridge', timeout=1)
            
            if result:
                _, cmd = result
                call_uuid, agent_id = cmd.split(':')
                
                logger.info(f"Processing bridge command: {call_uuid} -> {agent_id}")
                
                # Transfer the parked call to the agent extension
                transfer_cmd = f"api uuid_transfer {call_uuid} {agent_id} XML default"
                response = esl.send(transfer_cmd)
                
                # For api commands, response is in .data attribute
                response_data = response.data if hasattr(response, 'data') else ''
                
                logger.info(f"Transfer command: {transfer_cmd}")
                logger.info(f"Transfer response: {response_data}")
                
                if response_data and '-ERR' in str(response_data):
                    logger.error(f"Transfer failed: {response_data}")
                else:
                    logger.info(f"Successfully initiated transfer of call {call_uuid} to agent {agent_id}")
                
        except Exception as e:
            logger.error(f"Error processing bridge command: {e}")
            gevent.sleep(1)

def process_call_control_commands(esl):
    """Process call control commands from Redis queue"""
    logger.info("Starting call control processor...")
    
    while True:
        try:
            # Create fresh Redis connection for this greenlet
            r = redis.from_url(REDIS_URL, decode_responses=True)
            
            # Blocking pop with 1 second timeout
            result = r.blpop('cmd:call_control', timeout=1)
            
            if result:
                _, cmd_json = result
                cmd = json.loads(cmd_json)
                
                action = cmd.get('action')
                call_uuid = cmd.get('call_uuid')
                target_agent = cmd.get('target_agent')
                
                logger.info(f"Processing call control: {action} for {call_uuid}")
                
                if action == 'hold':
                    # Put call on hold (play hold music)
                    hold_cmd = f"api uuid_hold {call_uuid}"
                    response = esl.send(hold_cmd)
                    response_data = response.data if hasattr(response, 'data') else ''
                    logger.info(f"Hold response: {response_data}")
                    
                elif action == 'resume':
                    # Resume call (stop hold music)
                    resume_cmd = f"api uuid_hold off {call_uuid}"
                    response = esl.send(resume_cmd)
                    response_data = response.data if hasattr(response, 'data') else ''
                    logger.info(f"Resume response: {response_data}")
                    
                elif action == 'transfer' and target_agent:
                    # Blind transfer to another agent
                    transfer_cmd = f"api uuid_transfer {call_uuid} {target_agent} XML default"
                    response = esl.send(transfer_cmd)
                    response_data = response.data if hasattr(response, 'data') else ''
                    logger.info(f"Transfer to {target_agent} response: {response_data}")
                    
                elif action == 'hangup':
                    # Get the specific agent who is hanging up
                    agent_id = cmd.get('agent_id')
                    agent_uuid_to_hangup = call_uuid  # Default to call_uuid
                    
                    if agent_id:
                        # Check if this agent is in a conference
                        agent_data = r.hgetall(f'agent:{agent_id}:active_call')
                        if agent_data.get('agent_uuid'):
                            # Agent is in a conference, hangup only their leg
                            agent_uuid_to_hangup = agent_data['agent_uuid']
                            logger.info(f"Agent {agent_id} in conference, hanging up agent UUID: {agent_uuid_to_hangup}")
                        else:
                            logger.info(f"Agent {agent_id} hanging up call: {call_uuid}")
                    else:
                        logger.warning(f"No agent_id provided for hangup of {call_uuid}, using call_uuid")
                    
                    # Hangup the call (or agent's conference leg)
                    hangup_cmd = f"api uuid_kill {agent_uuid_to_hangup}"
                    response = esl.send(hangup_cmd)
                    response_data = response.data if hasattr(response, 'data') else ''
                    logger.info(f"Hangup response: {response_data}")
                    
                elif action == 'conference' and target_agent:
                    # Create conference by originating to target agent first, then transfer current parties
                    call_data = r.hgetall(f'call:{call_uuid}')
                    agent_uuid = call_data.get('bridged_to')
                    current_agent = call_data.get('agent_id')
                    caller_number = call_data.get('caller_id')
                    
                    room_num = f"31{call_uuid[-2:]}"
                    
                    logger.info(f"Creating conference {room_num} with all three parties")
                    
                    if agent_uuid:
                        # Step 1: Originate to target agent to CREATE the conference first
                        originate_cmd = f"api originate user/{target_agent} &conference({room_num}@default)"
                        response = esl.send(originate_cmd)
                        target_agent_uuid = ''
                        if hasattr(response, 'data') and response.data.strip().startswith('+OK'):
                            target_agent_uuid = response.data.strip().split()[1] if len(response.data.strip().split()) > 1 else ''
                        logger.info(f"Created conference {room_num} by adding target agent {target_agent}: {response.data if hasattr(response, 'data') else ''}")
                        
                        # Step 2: Wait for conference to be established
                        time.sleep(0.5)
                        
                        # Step 3: Move existing bridged parties into conference using uuid_broadcast
                        # uuid_broadcast executes the conference app on existing channels WITHOUT creating new UUIDs
                        # This keeps the original channels alive - no hangups!
                        broadcast1 = esl.send(f"api uuid_broadcast {call_uuid} aleg conference::{room_num}@default")
                        logger.info(f"Broadcast conference to caller {call_uuid}: {broadcast1.data if hasattr(broadcast1, 'data') else ''}")
                        
                        broadcast2 = esl.send(f"api uuid_broadcast {agent_uuid} aleg conference::{room_num}@default")
                        logger.info(f"Broadcast conference to agent {agent_uuid}: {broadcast2.data if hasattr(broadcast2, 'data') else ''}")
                        
                        # Wait for broadcasts to complete
                        time.sleep(0.5)
                        
                        # Update active calls to show conference info
                        # For current agent - keep their agent_uuid for hangup
                        current_agent_info = {
                            'call_uuid': call_uuid,
                            'agent_uuid': agent_uuid,  # Store the agent's UUID for proper hangup
                            'caller_number': caller_number,
                            'caller_name': call_data.get('caller_name', caller_number),
                            'conference_room': room_num,
                            'conference_participants': json.dumps([current_agent, target_agent]),  # Store as JSON string
                            'bridged_at': call_data.get('bridged_at')
                        }
                        
                        # For target agent - use their UUID from originate response
                        target_agent_info = {
                            'call_uuid': call_uuid,
                            'agent_uuid': target_agent_uuid,  # Store target agent's UUID
                            'caller_number': caller_number,
                            'caller_name': call_data.get('caller_name', caller_number),
                            'conference_room': room_num,
                            'conference_participants': json.dumps([current_agent, target_agent]),  # Store as JSON string
                            'bridged_at': call_data.get('bridged_at')
                        }
                        
                        # Update both agents' active calls to show they're in conference
                        r.hset(f'agent:{current_agent}:active_call', mapping=current_agent_info)
                        r.hset(f'agent:{target_agent}:active_call', mapping=target_agent_info)
                        
                        # Update call data to mark it as in conference WITH participant info
                        r.hset(f'call:{call_uuid}', 'status', 'conference')
                        r.hset(f'call:{call_uuid}', 'conference_room', room_num)
                        r.hset(f'call:{call_uuid}', 'conference_participants', json.dumps([current_agent, target_agent]))
                        
                        # Publish conference event
                        event_data = {
                            'type': 'conference_created',
                            'room': room_num,
                            'caller': caller_number,
                            'agents': [current_agent, target_agent]
                        }
                        r.publish('call_events', json.dumps(event_data))
                        logger.info(f"Published conference event for room {room_num}")
                
                elif action == 'eavesdrop':
                    # Manager eavesdrop on conference
                    conference_room = cmd.get('conference_room')
                    manager_extension = cmd.get('manager_extension')
                    
                    logger.info(f"Manager {manager_extension} eavesdropping on conference {conference_room}")
                    
                    # Originate call to manager and join conference in muted/listen-only mode
                    # Using +flags{mute} to make them listen-only
                    originate_cmd = f"api originate user/{manager_extension} &conference({conference_room}@default+flags{{mute}})"
                    response = esl.send(originate_cmd)
                    logger.info(f"Eavesdrop response: {response.data if hasattr(response, 'data') else ''}")
                    
                    # Update call record to track supervisor
                    for call_key in r.scan_iter('call:*'):
                        call_check_data = r.hgetall(call_key)
                        if call_check_data.get('conference_room') == conference_room:
                            r.hset(call_key, 'supervisor_id', manager_extension)
                            logger.info(f"Marked supervisor {manager_extension} on call {call_check_data.get('uuid')}")
                    
                else:
                    logger.warning(f"Unknown action: {action}")
                
        except Exception as e:
            logger.error(f"Error processing call control command: {e}")
            gevent.sleep(1)

def main():
    """Main event loop"""
    global redis_client
    
    logger.info("Starting FreeCalls Orchestrator (FreeSWITCH)...")
    
    # Connect to Redis
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    logger.info(f"Connected to Redis at {REDIS_URL}")
    
    while True:
        try:
            logger.info(f"Connecting to FreeSWITCH at {FREESWITCH_HOST}:{FREESWITCH_PORT}")
            
            esl = InboundESL(host=FREESWITCH_HOST, port=FREESWITCH_PORT, password=ESL_PASSWORD)
            esl.connect()
            
            logger.info("Connected to FreeSWITCH ESL")
            
            # Register event handlers
            esl.register_handle('CHANNEL_PARK', handle_park_event)
            esl.register_handle('CHANNEL_HANGUP', handle_hangup_event)
            esl.register_handle('CHANNEL_BRIDGE', handle_bridge_event)
            esl.register_handle('CUSTOM', handle_registration_event)
            
            # Subscribe to events
            esl.send('event plain CHANNEL_PARK CHANNEL_HANGUP CHANNEL_BRIDGE')
            esl.send('event plain CUSTOM sofia::register')
            esl.send('event plain CUSTOM sofia::unregister')
            
            logger.info("Subscribed to events: CHANNEL_PARK, CHANNEL_HANGUP, CHANNEL_BRIDGE, CUSTOM sofia::register/unregister")
            logger.info("Listening for events...")
            
            # Start command processors in background greenlets
            gevent.spawn(process_bridge_commands, esl)
            logger.info("Bridge command processor started")
            
            gevent.spawn(process_call_control_commands, esl)
            logger.info("Call control processor started")
            
            # Start registration sync task
            gevent.spawn(sync_registrations, esl)
            logger.info("Registration sync task started")
            
            # Keep main thread alive while greenlets process events
            # greenswitch spawns background greenlets that automatically
            # receive events and dispatch to registered handlers
            while esl.connected:
                gevent.sleep(1)
                    
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            logger.info("Reconnecting in 5 seconds...")
            time.sleep(5)

if __name__ == '__main__':
    main()
