import unicodedata
import bleach


def sanitize_text(value: str | None, max_length: int = 5000) -> str:
    """
    Sanitiza campos de texto libre antes de persistir en DB.

    Límites recomendados por campo:
      diagnosis / treatment / notes  → max_length=5000
      vaccine_name                   → max_length=255
      batch_number / motivo / reason → max_length=100

    Orden de operaciones:
      1. Truncar (protección DoS/CPU antes de procesar)
      2. Normalizar unicode (elimina ofuscaciones como ＜script＞)
      3. Eliminar todo HTML y comentarios con bleach
      4. Strip final (detecta strings de solo espacios)
    """
    if not value:
        return ""
    value = value[:max_length]
    value = unicodedata.normalize("NFKC", value)
    value = bleach.clean(
        value,
        tags=[],
        attributes={},
        strip=True,
        strip_comments=True,
    )
    return value.strip()
