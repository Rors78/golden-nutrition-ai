"""Barcode → macros via the Open Food Facts public API.

No API key, no account: OFF asks only for a descriptive User-Agent. Lookups
are stateless — nothing is stored until the user logs the meal.
"""
import json
import urllib.error
import urllib.request

OFF_URL = ('https://world.openfoodfacts.org/api/v2/product/{code}.json'
           '?fields=product_name,brands,serving_size,serving_quantity,nutriments')

# app field → OFF nutriment key stem
_FIELDS = (('protein', 'proteins'), ('calories', 'energy-kcal'),
           ('carbs', 'carbohydrates'), ('fat', 'fat'), ('fiber', 'fiber'))


def _num(nutriments, key):
    try:
        return round(float(nutriments.get(key)), 1)
    except (TypeError, ValueError):
        return None


def normalize(payload):
    """OFF product payload → {name, brand, serving_size, basis, macros} or None.

    Prefers per-serving macros when OFF has them (basis 'serving'), else falls
    back to per-100g (basis '100g'). Returns None when the product is missing
    or has no usable calorie/protein data at all.
    """
    product = payload.get('product') or {}
    if payload.get('status') != 1 or not product:
        return None
    n = product.get('nutriments', {})
    for basis, suffix in (('serving', '_serving'), ('100g', '_100g')):
        macros = {field: _num(n, stem + suffix) for field, stem in _FIELDS}
        if macros['calories'] is not None or macros['protein'] is not None:
            return {
                'name': str(product.get('product_name') or '').strip() or 'Unknown product',
                'brand': str(product.get('brands') or '').strip(),
                'serving_size': str(product.get('serving_size') or '').strip(),
                'basis': basis,
                'macros': {k: (v if v is not None else 0) for k, v in macros.items()},
            }
    return None


def lookup_barcode(code):
    """Look a barcode up on Open Food Facts. Returns normalize()'s dict or None.

    Raises ValueError for junk input before any network I/O.
    """
    digits = ''.join(ch for ch in str(code) if ch.isdigit())
    if not 8 <= len(digits) <= 14:
        raise ValueError('That does not look like a product barcode.')
    req = urllib.request.Request(
        OFF_URL.format(code=digits),
        headers={'User-Agent': 'GoldenNutritionAI/1.0 (self-hosted personal tracker)'})
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            payload = json.load(res)
    except urllib.error.HTTPError as e:
        if e.code == 404:          # OFF answers 404 for unknown barcodes
            return None
        raise
    return normalize(payload)
