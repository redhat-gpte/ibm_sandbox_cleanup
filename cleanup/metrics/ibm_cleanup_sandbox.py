from __future__ import annotations
from prometheus_client import Counter, Gauge

from metrics import AppMetrics


class CleanUpSandboxMetrics(AppMetrics):
    ibm_verify_accounts = Gauge(
        'ibm_verify_accounts',
        'Total number of accounts verified',
        ['account', 'cloud_provider', 'instance', 'job_name']
    )

    ibm_current_usage = Gauge(
        'ibm_current_usage',
        'Total number of current usage',
        ['account', 'cloud_provider', 'instance', 'job_name']
    )

    ibm_previous_usage = Gauge(
        'ibm_previous_usage',
        'Total number of previous usage',
        ['account', 'cloud_provider', 'instance', 'job_name']
    )

    ibm_clean_accounts = Gauge(
        'ibm_clean_accounts',
        'Total number of accounts cleaned',
        ['account', 'cloud_provider', 'instance', 'job_name']
    )

    @classmethod
    def push_clean_metrics(cls, metric_name, value, job_name, labels=None, instance='check_cleanup'):
        if labels and isinstance(labels, dict):
            labels.update({'instance': instance, 'job_name': job_name})
        else:
            labels = {'instance': instance, 'job_name': job_name}

        print(labels)
        # labels_names = ['instance']
        # labels_values = [instance, job_name]
        # if labels and isinstance(labels, dict):
        #     for k, v in labels.items():
        #         labels_names.append(k)
        #         labels_values.append(v)

        # print(labels_names)
        attribute = getattr(cls, metric_name)
        attribute.labels(**labels).set(value)
        cls.push_metrics()
