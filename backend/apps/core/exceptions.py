import uuid
import logging
from itertools import islice
from django.db.models.deletion import ProtectedError
from django.http import Http404 as DjangoHttp404
from rest_framework.views import exception_handler
from rest_framework.exceptions import NotFound, ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger('django')

SPANISH_CODES = {
    'authentication_failed': 'Credenciales inválidas.',
    'not_authenticated': 'Debes iniciar sesión.',
    'permission_denied': 'No tienes permiso para realizar esta acción.',
    'not_found': 'El recurso solicitado no existe.',
    'method_not_allowed': 'Método no permitido.',
    'throttled': 'Demasiadas solicitudes. Intenta en unos minutos.',
    'parse_error': 'Error al procesar la solicitud.',
}

_ENGLISH_MARKERS = (
    'Ensure that', 'This field', 'Enter a valid',
    'This value', 'must be', 'is not valid',
)


def custom_exception_handler(exc, context):
    """
    Handler global de excepciones DRF.

    Formatos de respuesta:
      - Error simple:    {code, message}
      - Error de campo:  {code: "validation_error", errors: {field: [messages]}}
      - Error con meta:  {code: "validation_error", errors: {...}, meta: {...}}
      - Error 500:       {code: "server_error", message, request_id}

    Contrato para metadatos:
      - Las claves que comienzan con '__' en el dict de error se mueven a 'meta'
      - Ejemplo: {'__force_weight_required': True} → {'meta': {'force_weight_required': True}}
      - NUNCA usar '__' como prefijo en nombres de campos reales del serializer

    Usar request_id para correlacionar con Railway logs:
      grep '<request_id>' en stdout de Railway.
    """
    # Django Http404 no tiene default_code; convertir a DRF NotFound para que
    # default_code='not_found' y el mensaje salga en español.
    if isinstance(exc, DjangoHttp404):
        exc = NotFound()

    # isinstance() acepta subclases (ej. RestrictedError de Django 4.1+ que
    # es subclase de ProtectedError). Si una subclase específica requiriera
    # tratamiento distinto, agregar branch separado ANTES de este isinstance.
    if isinstance(exc, ProtectedError):
        return _handle_protected_error(exc)

    response = exception_handler(exc, context)

    if response is not None:
        code = getattr(exc, 'default_code', 'error')
        data = response.data

        if isinstance(data, dict) and 'detail' in data:
            message = SPANISH_CODES.get(code, _clean_message(str(data['detail'])))
            response.data = {'code': code, 'message': message}

        elif isinstance(data, dict):
            translated = {}
            meta = {}
            for field, messages in data.items():
                # Contrato: '__' prefijo = metadatos, no campo de error
                if isinstance(field, str) and field.startswith('__'):
                    meta[field[2:]] = messages
                    continue
                msgs = messages if isinstance(messages, list) else [messages]
                # NO limpiar mensajes de validación por campo - preservar contexto técnico
                # _clean_message solo aplica a detail/error (mensajes globales)
                translated[field] = [str(m) for m in msgs]
            response.data = {'code': 'validation_error', 'errors': translated}
            if meta:
                response.data['meta'] = meta

        elif isinstance(data, list):
            # ValidationError con string/lista usa 'validation_error', no 'invalid'
            output_code = 'validation_error' if isinstance(exc, DRFValidationError) else code
            message = _clean_message(str(data[0])) if data else 'Error inesperado.'
            response.data = {'code': output_code, 'message': message}

    else:
        request_id = str(uuid.uuid4())
        logger.exception(
            "[%s] Unhandled exception in %s",
            request_id,
            context.get('view'),
        )
        response = Response(
            {
                'code': 'server_error',
                'message': 'Error interno del servidor.',
                'request_id': request_id,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response


def _clean_message(msg: str) -> str:
    return 'Valor inválido.' if any(m in msg for m in _ENGLISH_MARKERS) else msg


# Bounded probe / hard cap del handler ProtectedError (PR-4B / ADR p16).
# - PROBE_LIMIT: si list(exc.protected_objects[:N]) devuelve N elementos sabemos
#   que hay "al menos N" sin pagar el queryset completo (que en una org con
#   miles de relaciones puede ser costoso de materializar).
# - COUNT_CAP: solo se ejecuta count() si el probe está saturado. El cap
#   evita full-table scan en escenarios extremos: si supera el cap se reporta
#   ">N" sin la cifra exacta.
_PROTECTED_PROBE_LIMIT = 6
_PROTECTED_COUNT_CAP = 1000
_PROTECTED_SAMPLE_LIMIT = 5


def _handle_protected_error(exc: ProtectedError) -> Response:
    """
    Mapea django.db.models.deletion.ProtectedError a 409 Conflict con shape
    canónico del proyecto (ADR p16 override de p15 §8 — semántica REST por
    sobre conveniencia frontend).

    Diseño defensivo:
    - isinstance EXACTO con ProtectedError (no IntegrityError/Exception broad)
      via type(exc) is ProtectedError en el caller — esto evita ocultar bugs
      de constraint, deadlock, FK compuestos, etc.
    - Probe via islice(): `exc.protected_objects` es un `set` (Django Collector
      lo materializa), no es subscriptable — usar islice para tomar primeros N
      sin convertir el set completo.
    - COUNT solo si probe saturado. Como `protected_objects` es set ya en
      memoria, len() es O(1) — sin query a DB. El "cap 1000" queda como
      defensa para casos futuros donde el handler pudiera recibir un
      queryset-like (forward-compat). Para set: si len > 1000, reporta
      ">1000" en lugar del número exacto (consistencia de shape).
    - Sample con dict {type, id, public_id} — NUNCA str(obj). Razones:
      a) PII leak: __str__ de Pet/Owner expone nombres en respuesta de error
      b) N+1: si __str__ accede relations (self.owner.name) → query extra
         por cada objeto del sample
      c) Determinismo: shape estable para parsers frontend
    """
    objects = exc.protected_objects
    probe = list(islice(objects, _PROTECTED_PROBE_LIMIT))
    saturated = len(probe) >= _PROTECTED_PROBE_LIMIT

    # Shape consistente para frontend (code-reviewer HIGH):
    # - protected_count: SIEMPRE int (cardinalidad real cuando se conoce;
    #   _PROTECTED_COUNT_CAP cuando se trunca arriba del cap).
    # - protected_count_truncated: bool — true si la cifra fue capped.
    # Sin esta separación, count alternaba entre "3" (str numérico) y ">1000"
    # (str literal), forzando dos parsers en el cliente.
    protected_count = len(probe)
    protected_count_truncated = False

    if saturated:
        try:
            if hasattr(objects, 'all') and hasattr(objects, 'filter'):
                # Queryset-like — slicing DB-side con LIMIT cap+1.
                bounded = objects.all()[:_PROTECTED_COUNT_CAP + 1].count()
            else:
                # Set/list ya en memoria (caso común — Django Collector).
                # len() es O(1) sin query.
                bounded = len(objects)
            if bounded > _PROTECTED_COUNT_CAP:
                protected_count = _PROTECTED_COUNT_CAP
                protected_count_truncated = True
            else:
                protected_count = bounded
        except Exception:
            # Si el count falla (timeout, schema raro), degradar reportando
            # al menos PROBE_LIMIT - 1 con truncated=True (cliente sabe que
            # la cifra real es ≥ PROBE_LIMIT).
            logger.warning(
                "ProtectedError count fallback — degraded to probe size",
                exc_info=True,
            )
            protected_count = _PROTECTED_PROBE_LIMIT - 1
            protected_count_truncated = True

    sample = [
        {
            'type': type(obj)._meta.label,
            'id': obj.pk,
            'public_id': str(getattr(obj, 'public_id', '') or '') or None,
        }
        for obj in probe[:_PROTECTED_SAMPLE_LIMIT]
    ]

    return Response(
        {
            'code': 'resource_has_dependencies',
            'message': 'No se puede eliminar este registro porque tiene información asociada.',
            'protected_count': protected_count,
            'protected_count_truncated': protected_count_truncated,
            'protected_sample': sample,
        },
        status=status.HTTP_409_CONFLICT,
    )
