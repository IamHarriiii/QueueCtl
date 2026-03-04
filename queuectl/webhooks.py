"""
Webhook notification system for queuectl
Handles HTTP callbacks for job lifecycle events with rate limiting
"""
import requests
import json
import time
import hashlib
import hmac
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict
from .storage import Storage

logger = logging.getLogger('queuectl.webhooks')


class WebhookEvent:
    """Webhook event types"""
    JOB_STARTED = 'job.started'
    JOB_COMPLETED = 'job.completed'
    JOB_FAILED = 'job.failed'
    JOB_TIMEOUT = 'job.timeout'
    JOB_CANCELLED = 'job.cancelled'
    
    @classmethod
    def all_events(cls) -> List[str]:
        """Get all event types"""
        return [cls.JOB_STARTED, cls.JOB_COMPLETED, cls.JOB_FAILED, 
                cls.JOB_TIMEOUT, cls.JOB_CANCELLED]


class RateLimiter:
    """Simple token bucket rate limiter for webhook dispatch"""
    
    def __init__(self, max_per_minute: int = 100) -> None:
        self.max_per_minute = max_per_minute
        self._calls: Dict[str, list] = defaultdict(list)
    
    def allow(self, key: str) -> bool:
        """Check if a call is allowed for the given key"""
        now = time.time()
        cutoff = now - 60
        
        # Remove old entries
        self._calls[key] = [t for t in self._calls[key] if t > cutoff]
        
        if len(self._calls[key]) >= self.max_per_minute:
            return False
        
        self._calls[key].append(now)
        return True


class WebhookManager:
    """Manages webhook configurations"""
    
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self._ensure_webhook_tables()
    
    def _ensure_webhook_tables(self) -> None:
        """Create webhook tables if they don't exist"""
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    events TEXT NOT NULL,
                    secret TEXT,
                    enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhook_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    webhook_id TEXT NOT NULL,
                    job_id TEXT,
                    event TEXT NOT NULL,
                    status_code INTEGER,
                    response TEXT,
                    error TEXT,
                    delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (webhook_id) REFERENCES webhooks(id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_logs_job ON webhook_logs(job_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_logs_webhook ON webhook_logs(webhook_id)")
    
    def add_webhook(self, webhook_id: str, url: str, events: List[str], 
                    secret: Optional[str] = None) -> bool:
        """Add a new webhook"""
        with self.storage._get_conn() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO webhooks (id, url, events, secret)
                    VALUES (?, ?, ?, ?)
                """, (webhook_id, url, json.dumps(events), secret))
                logger.info(f"Webhook added: {webhook_id} -> {url}")
                return True
            except Exception as e:
                logger.error(f"Error adding webhook: {e}")
                return False
    
    def get_webhooks_for_event(self, event: str) -> List[Dict]:
        """Get all enabled webhooks for a specific event"""
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, url, events, secret
                FROM webhooks
                WHERE enabled = 1
            """)
            
            webhooks = []
            for row in cursor.fetchall():
                events = json.loads(row['events'])
                if event in events or '*' in events:
                    webhooks.append({
                        'id': row['id'],
                        'url': row['url'],
                        'events': events,
                        'secret': row['secret']
                    })
            
            return webhooks
    
    def list_webhooks(self) -> List[Dict]:
        """List all webhooks"""
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, url, events, enabled, created_at
                FROM webhooks
                ORDER BY created_at DESC
            """)
            
            return [{
                'id': row['id'],
                'url': row['url'],
                'events': json.loads(row['events']),
                'enabled': bool(row['enabled']),
                'created_at': row['created_at']
            } for row in cursor.fetchall()]
    
    def remove_webhook(self, webhook_id: str) -> bool:
        """Remove a webhook"""
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
            return cursor.rowcount > 0
    
    def toggle_webhook(self, webhook_id: str, enabled: bool) -> bool:
        """Enable or disable a webhook"""
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE webhooks SET enabled = ? WHERE id = ?
            """, (1 if enabled else 0, webhook_id))
            return cursor.rowcount > 0
    
    def log_delivery(self, webhook_id: str, job_id: str, event: str,
                     status_code: Optional[int] = None, response: Optional[str] = None,
                     error: Optional[str] = None) -> None:
        """Log webhook delivery attempt"""
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO webhook_logs (webhook_id, job_id, event, status_code, response, error)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (webhook_id, job_id, event, status_code, response, error))


class WebhookDispatcher:
    """Dispatches webhook notifications with rate limiting and HMAC signing"""
    
    def __init__(self, manager: WebhookManager, max_retries: int = 3,
                 rate_limit: int = 100) -> None:
        self.manager = manager
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(max_per_minute=rate_limit)
    
    def dispatch(self, event: str, job_data: Dict[str, Any]) -> None:
        """Dispatch webhook for an event"""
        webhooks = self.manager.get_webhooks_for_event(event)
        
        for webhook in webhooks:
            if not self.rate_limiter.allow(webhook['id']):
                logger.warning(f"Rate limit exceeded for webhook {webhook['id']}")
                self.manager.log_delivery(
                    webhook['id'], job_data.get('id'), event,
                    error="Rate limit exceeded"
                )
                continue
            self._send_webhook(webhook, event, job_data)
    
    def _send_webhook(self, webhook: Dict, event: str, job_data: Dict[str, Any]) -> None:
        """Send webhook with retry logic and HMAC signing"""
        payload = {
            'event': event,
            'job': {
                'id': job_data.get('id'),
                'command': job_data.get('command'),
                'state': job_data.get('state'),
                'exit_code': job_data.get('exit_code'),
                'attempts': job_data.get('attempts'),
                'priority': job_data.get('priority'),
                'tags': job_data.get('tags'),
                'created_at': job_data.get('created_at'),
                'updated_at': job_data.get('updated_at')
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
        payload_json = json.dumps(payload, default=str)
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Queuectl-Webhook/2.0',
            'X-Webhook-Event': event,
        }
        
        # HMAC signature for authentication
        if webhook.get('secret'):
            signature = hmac.new(
                webhook['secret'].encode(),
                payload_json.encode(),
                hashlib.sha256
            ).hexdigest()
            headers['X-Webhook-Signature'] = f"sha256={signature}"
            headers['X-Webhook-Secret'] = webhook['secret']
        
        # Retry with exponential backoff
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    webhook['url'],
                    data=payload_json,
                    headers=headers,
                    timeout=10
                )
                
                self.manager.log_delivery(
                    webhook['id'], job_data.get('id'), event,
                    status_code=response.status_code,
                    response=response.text[:500]
                )
                
                if 200 <= response.status_code < 300:
                    logger.debug(f"Webhook {webhook['id']} delivered: {event}")
                    return
                
                logger.warning(f"Webhook {webhook['id']} returned {response.status_code}")
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Webhook {webhook['id']} failed: {error_msg[:200]}")
                
                self.manager.log_delivery(
                    webhook['id'], job_data.get('id'), event,
                    error=error_msg[:500]
                )
                
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
