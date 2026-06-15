import hashlib
import asyncio
import time
import logging

logger = logging.getLogger(__name__)

def get_lock_id(session_id: str) -> int:
    """
    Hash a session_id into a signed 64-bit integer consistently to prevent Python hash randomization issues.
    """
    hasher = hashlib.md5(session_id.encode('utf-8'))
    digest = hasher.digest()
    # Take the first 8 bytes and convert to signed 64-bit integer (PostgreSQL bigint)
    return int.from_bytes(digest[:8], byteorder='big', signed=True)

class SessionLockManager:
    def __init__(self, check_interval: float = 0.1):
        self.check_interval = check_interval

    async def acquire_lock(self, conn, session_id: str, timeout: float = 8.0):
        """
        Acquire a transactional advisory lock on PostgreSQL for the given session_id.
        Will retry periodically until timeout is reached, then raises TimeoutError.
        """
        lock_id = get_lock_id(session_id)
        start_time = time.perf_counter()
        
        while True:
            # pg_try_advisory_xact_lock returns boolean indicating whether the lock was successfully acquired
            try:
                locked = await conn.fetchval("SELECT pg_try_advisory_xact_lock($1)", lock_id)
                if locked:
                    logger.debug(f"Acquired transaction advisory lock for session {session_id} (lock_id: {lock_id})")
                    return True
            except Exception as e:
                logger.error(f"Error trying to acquire advisory lock: {e}")
                raise e
            
            elapsed = time.perf_counter() - start_time
            if elapsed >= timeout:
                raise TimeoutError(f"Failed to acquire lock for session {session_id} within {timeout} seconds")
            
            await asyncio.sleep(self.check_interval)
