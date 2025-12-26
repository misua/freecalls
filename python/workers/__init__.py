"""
Dramatiq worker configuration for background task processing.

This module handles all CPU-intensive and I/O-bound tasks that should not
block the real-time orchestrator event loop.
"""
import os
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import CurrentMessage

# Get Redis URL from environment
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

# Configure Redis broker for Dramatiq
redis_broker = RedisBroker(url=REDIS_URL)

# Add middleware
redis_broker.add_middleware(CurrentMessage())

# Set as the default broker
dramatiq.set_broker(redis_broker)
