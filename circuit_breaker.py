import time
import logging
from enum import Enum
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5
    recovery_timeout: int = 900  # 15 minutes
    half_open_attempts: int = 2
    exception_types: tuple = field(default_factory=lambda: (Exception,))


class CircuitBreaker:
    """
    Circuit breaker implementation to prevent cascading failures
    
    States:
    - CLOSED: Normal operation, requests are allowed
    - OPEN: Too many failures, requests are blocked
    - HALF_OPEN: Testing if service has recovered
    """
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state_changed_at: datetime = datetime.now()
        
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                raise Exception(f"Circuit breaker is OPEN. Service unavailable until {self._get_recovery_time()}")
                
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.config.exception_types as e:
            self._on_failure()
            raise e
            
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery"""
        if self.last_failure_time is None:
            return False
        recovery_time = self.last_failure_time + timedelta(seconds=self.config.recovery_timeout)
        return datetime.now() >= recovery_time
        
    def _get_recovery_time(self) -> str:
        """Get formatted recovery time"""
        if self.last_failure_time is None:
            return "unknown"
        recovery_time = self.last_failure_time + timedelta(seconds=self.config.recovery_timeout)
        return recovery_time.strftime("%Y-%m-%d %H:%M:%S")
        
    def _on_success(self):
        """Handle successful call"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.half_open_attempts:
                self._transition_to_closed()
        else:
            self.failure_count = 0
            
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            self._transition_to_open()
        elif self.failure_count >= self.config.failure_threshold:
            self._transition_to_open()
            
    def _transition_to_closed(self):
        """Transition to CLOSED state"""
        logger.info("Circuit breaker transitioning to CLOSED state")
        self.state = CircuitState.CLOSED
        self.state_changed_at = datetime.now()
        self.failure_count = 0
        self.success_count = 0
        
    def _transition_to_open(self):
        """Transition to OPEN state"""
        logger.warning(f"Circuit breaker transitioning to OPEN state after {self.failure_count} failures")
        self.state = CircuitState.OPEN
        self.state_changed_at = datetime.now()
        self.success_count = 0
        
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        logger.info("Circuit breaker transitioning to HALF_OPEN state")
        self.state = CircuitState.HALF_OPEN
        self.state_changed_at = datetime.now()
        self.success_count = 0
        
    def get_state(self) -> str:
        """Get current circuit breaker state"""
        return self.state.value
        
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)"""
        return self.state == CircuitState.CLOSED
        
    def reset(self):
        """Manually reset the circuit breaker"""
        self._transition_to_closed()