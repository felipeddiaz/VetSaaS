from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Throttle específico para el endpoint de login.
    Limita intentos por IP para mitigar brute force.
    Tasa configurable en settings.DEFAULT_THROTTLE_RATES['login'].
    """
    scope = 'login'
