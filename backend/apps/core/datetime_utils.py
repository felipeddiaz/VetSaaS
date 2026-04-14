from datetime import datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from django.utils import timezone


@lru_cache(maxsize=256)
def _tzinfo(tz_name):
    return ZoneInfo(tz_name)


def get_context_timezone(entity):
    tz_name = getattr(entity, 'timezone', None) or 'UTC'
    return _tzinfo(tz_name)


def org_now_utc(org):
    return timezone.now().astimezone(ZoneInfo('UTC'))


def org_now_local(org):
    return org_now_utc(org).astimezone(get_context_timezone(org))


def org_today_local(org):
    return org_now_local(org).date()


def local_day_bounds_utc(org, local_date):
    tz = get_context_timezone(org)

    start_local = datetime.combine(local_date, time.min).replace(tzinfo=tz)
    next_local = datetime.combine(local_date + timedelta(days=1), time.min).replace(tzinfo=tz)

    start_utc = start_local.astimezone(ZoneInfo('UTC'))
    end_utc_exclusive = next_local.astimezone(ZoneInfo('UTC'))
    return start_utc, end_utc_exclusive


def filter_by_local_day(qs, field, org, local_date):
    start_utc, end_utc_exclusive = local_day_bounds_utc(org, local_date)
    return qs.filter(**{f'{field}__gte': start_utc, f'{field}__lt': end_utc_exclusive})


def local_date_time_to_utc(org, local_date, local_time):
    tz = get_context_timezone(org)
    local_dt = datetime.combine(local_date, local_time).replace(tzinfo=tz)
    return local_dt.astimezone(ZoneInfo('UTC'))


def utc_to_local(org, utc_dt):
    if not utc_dt:
        return None
    return utc_dt.astimezone(get_context_timezone(org))
