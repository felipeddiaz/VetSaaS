import uuid
import logging
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

    if isinstance(exc, ProtectedError):
        return Response(
            {
                'code': 'protected_resource',
                'error': 'No se puede eliminar este registro porque tiene información asociada.',
            },
            status=status.HTTP_409_CONFLICT,
        )

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
