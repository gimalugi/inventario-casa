"""WSGI entry point for Inventario Casa.

Keeps the application module unchanged while applying the Home Assistant
Ingress theme compatibility layer to the rendered page.
"""

import app as inventory


app = inventory.app

# v2.3.5 - compatibilità menu SELECT nativi Windows/Chrome
