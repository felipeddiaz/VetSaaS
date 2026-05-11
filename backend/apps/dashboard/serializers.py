"""
Dashboard read serializers (Capa 5 minimal v1).

Design rule (per user directive): every datapoint must explicitly carry
its provenance. Snapshots are tagged source='snapshot' + lifecycle_state.
Today is tagged source='live' with lifecycle_state=null. Mixed responses
NEVER combine values without these tags.

corrupt snapshot rows are NOT served. They are filtered out at the view
layer and surfaced via /api/internal/analytics-health/ instead.
"""
from rest_framework import serializers


# ---------------------------------------------------------------------------
# Operational metrics (visible to ASSISTANT, VET, ADMIN).
# ---------------------------------------------------------------------------
class OperationalMetricsSerializer(serializers.Serializer):
    appointments_total = serializers.IntegerField()
    appointments_done = serializers.IntegerField()
    appointments_no_show = serializers.IntegerField()
    medical_records_closed = serializers.IntegerField()


class OperationalDatapointSerializer(serializers.Serializer):
    bucket_date = serializers.DateField()
    source = serializers.ChoiceField(choices=['snapshot', 'live'])
    lifecycle_state = serializers.CharField(allow_null=True)
    metrics_schema_version = serializers.IntegerField(allow_null=True)
    metrics = OperationalMetricsSerializer()


# ---------------------------------------------------------------------------
# Financial metrics (visible to ADMIN only).
# ---------------------------------------------------------------------------
class FinancialMetricsSerializer(serializers.Serializer):
    revenue_paid = serializers.DecimalField(max_digits=14, decimal_places=2)
    revenue_accrual = serializers.DecimalField(max_digits=14, decimal_places=2)
    invoices_paid_count = serializers.IntegerField()


class FinancialDatapointSerializer(serializers.Serializer):
    bucket_date = serializers.DateField()
    source = serializers.ChoiceField(choices=['snapshot', 'live'])
    lifecycle_state = serializers.CharField(allow_null=True)
    metrics_schema_version = serializers.IntegerField(allow_null=True)
    metrics = FinancialMetricsSerializer()


# ---------------------------------------------------------------------------
# Envelope.
# ---------------------------------------------------------------------------
class RangeSerializer(serializers.Serializer):
    from_ = serializers.DateField()
    to = serializers.DateField()
    tz = serializers.CharField()

    def to_representation(self, obj):
        d = super().to_representation(obj)
        d['from'] = d.pop('from_')
        return d


class SeriesEnvelopeSerializer(serializers.Serializer):
    """Generic envelope. `series` is set by the view to the appropriate
    datapoint serializer's output."""
    range = RangeSerializer()
    series = serializers.ListField(child=serializers.DictField())
    today = serializers.DictField(allow_null=True)
    notes = serializers.ListField(child=serializers.CharField(), required=False)
