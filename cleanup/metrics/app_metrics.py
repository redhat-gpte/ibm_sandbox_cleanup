import os
from functools import wraps
import logging
from prometheus_client import Summary, push_to_gateway, REGISTRY


logger = logging.getLogger(__name__)


class AppMetrics:
    request_latency_seconds = Summary(
        'request_latency_seconds',
        'Time spent processing request',
        ['method_name']
        )

    @classmethod
    def record_request_latency(cls, func):
        """Decorator to measure and record the time taken by a function, with method labeling."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            method_name = func.__name__
            with cls.request_latency_seconds.labels(method_name=method_name).time():
                result = func(*args, **kwargs)
            cls.push_metrics()  # Optionally push metrics after recording
            return result
        return wrapper

    @classmethod
    def push_metrics(cls):
        """Pushes all metrics to the configured Pushgateway."""
        pushgateway_url = os.getenv("PUSH_GATEWAY_URL", 'http://localhost:9091')
        if not pushgateway_url:
            logger.warning("PUSH_GATEWAY_URL not set. Skipping push to gateway.")
            return
        job_name = cls.__name__
        try:
            push_to_gateway(pushgateway_url, job=job_name, registry=REGISTRY, timeout=10)
        except Exception as e:
            logger.error(f"Failed to push metrics: {str(e)}")
