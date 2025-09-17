import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState


@pytest.mark.unit
class TestCircuitBreaker:
    def test_init_default_state(self):
        """Test that circuit breaker starts in closed state"""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker(config)
        
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0
    
    def test_successful_call_in_closed_state(self):
        """Test successful function call when circuit is closed"""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker(config)
        
        def test_func(x):
            return x * 2
        
        result = cb.call(test_func, 5)
        
        assert result == 10
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
    
    def test_failed_calls_open_circuit(self):
        """Test that enough failures open the circuit"""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(config)
        
        def failing_func():
            raise Exception("Test failure")
        
        # First two failures don't open circuit
        for i in range(2):
            with pytest.raises(Exception):
                cb.call(failing_func)
            assert cb.state == CircuitState.CLOSED
        
        # Third failure opens circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3
    
    def test_open_circuit_blocks_calls(self):
        """Test that open circuit blocks function calls"""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker(config)
        
        def failing_func():
            raise Exception("Test failure")
        
        # Open the circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Next call should be blocked
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            cb.call(lambda: "should not execute")
    
    def test_circuit_recovery_timeout(self):
        """Test circuit transitions to half-open after timeout"""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=1  # 1 second for testing
        )
        cb = CircuitBreaker(config)
        
        def failing_func():
            raise Exception("Test failure")
        
        # Open the circuit
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Wait for recovery timeout
        time.sleep(1.1)
        
        # Should transition to half-open on next call attempt
        with patch.object(cb, '_transition_to_half_open') as mock_transition:
            with pytest.raises(Exception, match="Circuit breaker is OPEN"):
                cb.call(lambda: "test")
            
            mock_transition.assert_called_once()
    
    def test_half_open_success_closes_circuit(self):
        """Test successful calls in half-open state close the circuit"""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            half_open_attempts=2
        )
        cb = CircuitBreaker(config)
        
        # Manually set to half-open state
        cb.state = CircuitState.HALF_OPEN
        
        def success_func():
            return "success"
        
        # First successful call
        result = cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.success_count == 1
        
        # Second successful call closes circuit
        result = cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
    
    def test_half_open_failure_reopens_circuit(self):
        """Test failure in half-open state reopens the circuit"""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker(config)
        
        # Manually set to half-open state
        cb.state = CircuitState.HALF_OPEN
        
        def failing_func():
            raise Exception("Test failure")
        
        with pytest.raises(Exception):
            cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        assert cb.success_count == 0
    
    def test_custom_exception_types(self):
        """Test circuit breaker with custom exception types"""
        class CustomError(Exception):
            pass
        
        config = CircuitBreakerConfig(
            failure_threshold=2,
            exception_types=(CustomError,)
        )
        cb = CircuitBreaker(config)
        
        def custom_failing_func():
            raise CustomError("Custom failure")
        
        def other_failing_func():
            raise ValueError("Should not count")
        
        # CustomError should count
        with pytest.raises(CustomError):
            cb.call(custom_failing_func)
        assert cb.failure_count == 1
        
        # ValueError should not count
        with pytest.raises(ValueError):
            cb.call(other_failing_func)
        assert cb.failure_count == 1  # Still 1
        
        # Another CustomError opens circuit
        with pytest.raises(CustomError):
            cb.call(custom_failing_func)
        assert cb.state == CircuitState.OPEN
    
    def test_get_state(self):
        """Test get_state method returns correct state string"""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker(config)
        
        assert cb.get_state() == "closed"
        
        cb.state = CircuitState.OPEN
        assert cb.get_state() == "open"
        
        cb.state = CircuitState.HALF_OPEN
        assert cb.get_state() == "half_open"
    
    def test_is_closed(self):
        """Test is_closed method"""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker(config)
        
        assert cb.is_closed() is True
        
        cb.state = CircuitState.OPEN
        assert cb.is_closed() is False
        
        cb.state = CircuitState.HALF_OPEN
        assert cb.is_closed() is False
    
    def test_reset(self):
        """Test manual reset of circuit breaker"""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker(config)
        
        # Open the circuit
        with pytest.raises(Exception):
            cb.call(lambda: 1/0)
        
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 1
        
        # Reset
        cb.reset()
        
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0
    
    def test_recovery_time_formatting(self):
        """Test recovery time formatting"""
        config = CircuitBreakerConfig(recovery_timeout=300)  # 5 minutes
        cb = CircuitBreaker(config)
        
        # Set last failure time
        cb.last_failure_time = datetime.now()
        
        recovery_time = cb._get_recovery_time()
        
        # Should be a formatted datetime string
        assert isinstance(recovery_time, str)
        assert len(recovery_time) > 0
        
        # Test with no failure time
        cb.last_failure_time = None
        assert cb._get_recovery_time() == "unknown"