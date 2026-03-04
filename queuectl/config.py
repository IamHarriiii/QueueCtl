"""
Configuration management for queuectl
Handles getting and setting configuration values with validation
"""
import logging
from typing import Any, Dict, Set
from .storage import Storage

logger = logging.getLogger('queuectl.config')


class Config:
    """Configuration manager with validation and defaults"""

    DEFAULTS: Dict[str, Any] = {
        'max_retries': 3,
        'backoff_base': 2,
        'job_timeout': 300,
        'worker_poll_interval': 1,
        'priority_inheritance': True,
        'command_validation': True,
        'webhook_rate_limit': 100,  # Max webhook calls per minute
    }

    VALID_KEYS: Set[str] = set(DEFAULTS.keys())

    def __init__(self, storage: Storage) -> None:
        """Initialize config manager with storage"""
        self.storage = storage

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        if default is None:
            default = self.DEFAULTS.get(key)

        return self.storage.get_config(key, default)

    def set(self, key: str, value: Any) -> bool:
        """
        Set configuration value

        Args:
            key: Configuration key
            value: Value to set

        Returns:
            True if successful
        """
        logger.info(f"Config updated: {key} = {value}")
        return self.storage.set_config(key, value)

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values, filling in defaults for missing keys"""
        stored = self.storage.list_config()
        result = dict(self.DEFAULTS)
        result.update(stored)
        return result

    def is_valid_key(self, key: str) -> bool:
        """Check if configuration key is valid"""
        return key in self.VALID_KEYS

    def reset_to_defaults(self) -> None:
        """Reset all configuration to defaults"""
        for key, value in self.DEFAULTS.items():
            self.set(key, value)
        logger.info("Configuration reset to defaults")
