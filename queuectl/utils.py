"""
Utility functions for queuectl
Helper functions used across modules
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List

logger = logging.getLogger('queuectl.utils')


def calculate_backoff_delay(attempts: int, base: int = 2) -> int:
    """
    Calculate exponential backoff delay
    
    Args:
        attempts: Number of attempts made
        base: Base for exponential calculation
        
    Returns:
        Delay in seconds
    """
    return base ** attempts


def calculate_run_at(delay_seconds: int) -> str:
    """
    Calculate future timestamp for delayed job
    
    Args:
        delay_seconds: Delay in seconds
        
    Returns:
        ISO format timestamp string
    """
    run_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
    return run_at.isoformat()


def format_timestamp(timestamp: Optional[str]) -> str:
    """
    Format timestamp for display
    
    Args:
        timestamp: ISO format timestamp string
        
    Returns:
        Formatted timestamp or 'N/A'
    """
    if not timestamp:
        return 'N/A'
    
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, AttributeError):
        return timestamp


def truncate_string(s: str, max_length: int = 50) -> str:
    """
    Truncate string with ellipsis if too long
    
    Args:
        s: String to truncate
        max_length: Maximum length
        
    Returns:
        Truncated string
    """
    if not s:
        return ''
    
    if len(s) <= max_length:
        return s
    
    return s[:max_length-2] + '..'


def parse_tags(tags_str: Optional[str]) -> List[str]:
    """
    Parse comma-separated tags string into list
    
    Args:
        tags_str: Comma-separated tags
        
    Returns:
        List of tag strings
    """
    if not tags_str:
        return []
    return [t.strip() for t in tags_str.split(',') if t.strip()]


def format_duration(seconds: float) -> str:
    """
    Format seconds into human-readable duration
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Human-readable duration string
    """
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"