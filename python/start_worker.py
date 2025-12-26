"""
Dramatiq worker startup script.

This script:
1. Initializes the Dramatiq broker
2. Discovers all actors from workers.tasks
3. Starts the periodic CRM sync scheduler
4. Runs the worker process
"""
import logging
import dramatiq
from workers import redis_broker
from workers.tasks import schedule_crm_sync

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Kick off the periodic CRM sync on worker startup
logger.info("Starting periodic CRM sync scheduler...")
schedule_crm_sync.send()

logger.info("Dramatiq worker ready")
