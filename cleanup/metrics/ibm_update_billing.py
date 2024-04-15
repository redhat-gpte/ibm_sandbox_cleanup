from __future__ import annotations
from prometheus_client import Counter

from metrics import AppMetrics


class UpdateBillingMetrics(AppMetrics):
    ibm_update_billing_account_total = Counter(
        'ibm_update_billing_account_total',
        'Total number of accounts updated',
        ['instance']
    )

    ibm_update_billing_account_failure_total = Counter(
        'ibm_update_billing_account_failure_total',
        'Total number of account updates that failed',
        ['instance']
    )

    ibm_update_billing_acccount_failures = Counter(
        'ibm_update_billing_account_failures',
        'Total number of account updates that failed',
        ['sandbox_name', 'instance']
    )

    ibm_update_billing_account_success = Counter(
        'ibm_update_billing_account_success',
        'Total number of account updates that succeeded',
        ['sandbox_name', 'instance']
    )

    @classmethod
    def push_billing_account_total(cls):
        cls.ibm_update_billing_account_total.labels(instance='update_billing').inc()
        cls.push_metrics()

    @classmethod
    def push_billing_account_failure_total(cls):
        cls.ibm_update_billing_account_failure_total.labels(instance='update_billing').inc()
        cls.push_metrics()

    @classmethod
    def push_billing_account_failures(cls, sandbox_name):
        cls.ibm_update_billing_acccount_failures.labels(sandbox_name=sandbox_name, instance='update_billing').inc()
        cls.push_metrics()

    @classmethod
    def push_billing_account_success(cls, sandbox_name):
        cls.ibm_update_billing_account_success.labels(sandbox_name=sandbox_name, instance='billing_update').inc()
        cls.push_metrics()
