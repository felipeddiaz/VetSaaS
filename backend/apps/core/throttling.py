import re

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class ExtendedRateThrottle(SimpleRateThrottle):
    """
    Extiende parse_rate para soportar ventanas explícitas como:
    - 5/15min
    - 5/15m
    - 10/2h

    Mantiene compatibilidad con formatos nativos DRF (5/min, 100/hour, etc.).
    """

    _WINDOW_RE = re.compile(r"^(?P<num>\d+)\s*/\s*(?P<dur>\d+)\s*(?P<unit>[a-zA-Z]+)$")

    @staticmethod
    def _unit_to_seconds(unit: str) -> int:
        unit = unit.strip().lower()
        if unit.startswith('s'):
            return 1
        if unit.startswith('m'):
            return 60
        if unit.startswith('h'):
            return 3600
        if unit.startswith('d'):
            return 86400
        raise ValueError(f"Unidad de throttle no soportada: {unit}")

    def parse_rate(self, rate):
        if rate is None:
            return (None, None)

        if isinstance(rate, str):
            m = self._WINDOW_RE.match(rate.strip())
            if m:
                num_requests = int(m.group('num'))
                duration = int(m.group('dur')) * self._unit_to_seconds(m.group('unit'))
                return (num_requests, duration)

        return super().parse_rate(rate)


class LoginRateThrottle(ExtendedRateThrottle, AnonRateThrottle):
    """Limita intentos de login por IP. Tasa en DEFAULT_THROTTLE_RATES['login']."""
    scope = 'login'


class LoginUserRateThrottle(ExtendedRateThrottle):
    """
    Limita intentos de login por IP+username combinados.
    Si el body no tiene username, usa solo IP (no ignorar el request).
    Tasa en DEFAULT_THROTTLE_RATES['login_by_user'].
    """
    scope = 'login_by_user'

    def get_cache_key(self, request, view):
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        ip = ip.split(',')[0].strip()
        username = (request.data or {}).get('username', '').strip().lower()

        if not username:
            # Sin username → throttle solo por IP (no ignorar el request)
            return self.cache_format % {'scope': self.scope, 'ident': f'ip_{ip}'}

        return self.cache_format % {'scope': self.scope, 'ident': f'{ip}_{username}'}
