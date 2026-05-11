"""
PostgreSQL advisory locks for cross-process coordination.

Used to prevent overlapping cron executions and accidental concurrent
nightly job runs on Railway (where deploys can overlap, restarts can
re-trigger jobs, and there's no single-source scheduler guarantee).

API:
  try_advisory_lock(key) → bool
      Acquire a session-level advisory lock. Returns True if acquired,
      False if another session holds it. Lock is released automatically
      when the DB session ends.
  advisory_lock(key) [context manager]
      Try to acquire; raise LockUnavailable if held by another session;
      release on exit.
  hash_lock_key(*parts) → int
      Stable 63-bit signed bigint hash of arbitrary string parts. PG
      advisory locks accept (int, int) or (bigint). We use bigint form.

PostgreSQL specific. Code that runs on other backends should branch on
connection.vendor.
"""
import contextlib
import hashlib

from django.db import connection


class LockUnavailable(Exception):
    """Raised when advisory_lock() cannot acquire because another session holds it."""


def hash_lock_key(*parts):
    """
    Hash arbitrary parts into a 63-bit signed bigint suitable for
    pg_advisory_lock. Stable across processes and Python versions.
    """
    raw = ':'.join(str(p) for p in parts).encode('utf-8')
    digest = hashlib.blake2b(raw, digest_size=8).digest()
    n = int.from_bytes(digest, 'big', signed=False)
    # Convert to signed 63-bit range to fit PG bigint and avoid sign issues.
    return n & 0x7FFFFFFFFFFFFFFF


def try_advisory_lock(key):
    if connection.vendor != 'postgresql':
        # Other backends: no-op (sqlite/mysql tests won't deadlock anyway).
        return True
    with connection.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", [key])
        return cur.fetchone()[0]


def release_advisory_lock(key):
    if connection.vendor != 'postgresql':
        return
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", [key])


@contextlib.contextmanager
def advisory_lock(key, *, on_busy='raise'):
    """
    Context manager. on_busy='raise' (default) raises LockUnavailable; on_busy='skip'
    yields False instead so caller can short-circuit.
    """
    acquired = try_advisory_lock(key)
    if not acquired:
        if on_busy == 'skip':
            yield False
            return
        raise LockUnavailable(f"Advisory lock {key} held by another session.")
    try:
        yield True
    finally:
        release_advisory_lock(key)
