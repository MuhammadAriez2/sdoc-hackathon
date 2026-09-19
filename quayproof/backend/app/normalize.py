"""Conservative, versioned normalization. No fuzzy equality and no guessed digits."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation


def text_key(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).casefold()
    return ' '.join(re.sub(r'[^\w\s]', ' ', value).split())


def number(value: str) -> Decimal:
    value = value.strip()
    # Only unambiguous English grouping; decimal commas need explicit human interpretation.
    if ',' in value:
        if not re.fullmatch(r'\d{1,3}(,\d{3})+(\.\d+)?', value):
            raise ValueError('Ambiguous numeric separators')
        value = value.replace(',', '')
    if not re.fullmatch(r'\d+(\.\d+)?', value):
        raise ValueError('Unsupported numeric form')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Invalid number') from exc
    if not result.is_finite() or result <= 0:
        raise ValueError('Value must be positive')
    return result


def normalize(field: str, raw: str, context: str = '') -> str:
    if text_key(raw) in {'', 'na', 'n a', 'none', 'unknown', 'tbc', 'tbd', 'nil'}:
        raise ValueError('Missing or unresolved value')
    if field == 'container_count':
        plain = re.fullmatch(r'\s*(\d+)\s*(?:containers?|ctns?)?\s*', raw, re.I)
        size = re.fullmatch(r"\s*(\d+)\s*[x×]\s*(?:20|40|45)\s*['’\"]?\s*(?:HC|HQ|GP|DC|FT)?\s*", raw, re.I)
        match = plain or size
        if not match or int(match[1]) <= 0:
            raise ValueError('Container count is ambiguous; packages are not containers')
        return str(int(match[1]))
    if field == 'gross_weight_kg':
        match = re.fullmatch(r'\s*([\d,.]+)\s*(kg|kgs|kilograms?|mt|tonnes?|metric tons?|lbs?|pounds?)?\s*', raw, re.I)
        if not match:
            raise ValueError('Uncertain weight or OCR characters')
        unit = (match[2] or '').lower()
        if not unit:
            if re.search(r'\b(kg|kgs|kilograms?)\b', context, re.I):
                unit = 'kg'
            else:
                raise ValueError('Weight unit is missing')
        multiplier = Decimal('1000') if unit in {'mt', 'tonne', 'tonnes', 'metric ton', 'metric tons'} else Decimal('0.45359237') if unit in {'lb', 'lbs', 'pound', 'pounds'} else Decimal('1')
        return format((number(match[1]) * multiplier).normalize(), 'f')
    result = text_key(raw)
    if not result:
        raise ValueError('Empty value')
    return result
