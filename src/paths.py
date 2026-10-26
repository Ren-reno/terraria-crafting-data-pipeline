"""Rutas centralizadas del proyecto.

Todos los scripts de src/ leen y escriben a través de estas constantes, así el
layout del repo se define en un solo lugar:

    data/            -> datos finales (items.json, recipes.json, ingredient_categories.json)
    data/raw/        -> crudos de extract.py (no versionados, ver .gitignore)
    data/audit/      -> reportes de auditoría de los casos especiales de la fuente
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
AUDIT_DIR = DATA_DIR / "audit"
