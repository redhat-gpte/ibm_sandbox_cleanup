from __future__ import annotations
from prometheus_client import Counter

from metrics import AppMetrics


class UpdateBillingMetrics(AppMetrics):
    update_billing_account_total = Counter(
        'update_billing_account_total',
        'Total number of accounts updated',
        ['instance']
    )

    update_billing_account_failure_total = Counter(
        'update_billing_account_failure_total',
        'Total number of account updates that failed',
        ['instance']
    )

    update_billing_acccount_failures = Counter(
        'update_billing_account_failures',
        'Total number of account updates that failed',
        ['sandbox_name', 'instance']
    )

    update_billing_account_success = Counter(
        'update_billing_account_success',
        'Total number of account updates that succeeded',
        ['sandbox_name', 'instance']
    )

    @classmethod
    def push_billing_account_total(cls):
        cls.update_billing_account_total.labels(instance='update_billing').inc()
        cls.push_metrics()

    @classmethod
    def push_billing_account_failure_total(cls):
        cls.update_billing_account_failure_total.labels(instance='update_billing').inc()
        cls.push_metrics()

    @classmethod
    def push_billing_account_failures(cls, sandbox_name):
        cls.update_billing_acccount_failures.labels(sandbox_name=sandbox_name, instance='update_billing').inc()
        cls.push_metrics()

    @classmethod
    def push_billing_account_success(cls, sandbox_name):
        cls.update_billing_account_success.labels(sandbox_name=sandbox_name, instance='billing_update').inc()
        cls.push_metrics()
