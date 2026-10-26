#!/usr/bin/env python3
"""
Extracción de Items y Recipes desde terraria.wiki.gg vía la API de MediaWiki
(action=cargoquery), pensado para correr LOCALMENTE en tu máquina (no desde
el entorno de Claude, que respeta robots.txt de forma estricta).

Uso:
    pip install requests
    python src/extract.py

Salida:
    data/raw/raw_items.json     -> filas crudas de la tabla Items (paginadas y unidas)
    data/raw/raw_recipes.json   -> filas crudas de la tabla Recipes (paginadas y unidas)

Notas de diseño (ver docs 02/03 del proyecto):
- limit=500 confirmado como seguro (no se probó ni se usa limit=max/5000,
  que es el límite reservado para bots autenticados y no está confirmado
  para este wiki).
- offset confirmado como estrategia de paginación segura, sin cortes/duplicados.
- Se agrega un delay entre requests (rate limiting respetuoso) y un
  User-Agent identificable, ya que el robots.txt de la red wiki.gg bloquea
  /api.php para bots automatizados estándar. Correr este script es una
  decisión consciente de quien lo ejecuta: revisa los términos de la wiki
  antes de correrlo a gran escala o de publicar el proyecto resultante.
"""

import json
import time
import sys

import requests

from paths import RAW_DIR

API_URL = "https://terraria.wiki.gg/api.php"

# Identificarse de forma honesta, no camuflar el script como un browser real.
HEADERS = {
    "User-Agent": "TerrariaCrafteosBot/0.1 (uso personal, no comercial; "
                  "extraccion puntual de datos de Items/Recipes via Cargo API)"
}

LIMIT = 500          # confirmado seguro para este wiki (no usar 'max'/5000)
DELAY_SECONDS = 2.0  # espera entre requests, respetuoso con el servidor
MAX_RETRIES = 3
RETRY_BACKOFF = 5.0  # segundos, se multiplica por intento


def cargo_query(tables: str, fields: str, where: str = None,
                 order_by: str = None, limit: int = LIMIT, offset: int = 0) -> list:
    """Hace una sola request a action=cargoquery y devuelve la lista de filas."""
    params = {
        "action": "cargoquery",
        "tables": tables,
        "fields": fields,
        "format": "json",
        "limit": limit,
        "offset": offset,
    }
    if where:
        params["where"] = where
    if order_by:
        params["order_by"] = order_by

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                raise RuntimeError(f"API error: {data['error']}")

            # cargoquery envuelve cada fila en {"title": {...}}
            rows = [item["title"] for item in data.get("cargoquery", [])]
            return rows

        except Exception as e:
            last_error = e
            wait = RETRY_BACKOFF * attempt
            print(f"  [reintento {attempt}/{MAX_RETRIES}] error: {e} -> esperando {wait}s", file=sys.stderr)
            time.sleep(wait)

    raise RuntimeError(f"Fallaron {MAX_RETRIES} intentos. Último error: {last_error}")


def extract_table(tables: str, fields: str, where: str = None,
                   order_by: str = None, label: str = "tabla") -> list:
    """Extrae una tabla completa, paginando con offset hasta que no queden filas."""
    all_rows = []
    offset = 0

    while True:
        print(f"[{label}] pidiendo offset={offset} (limit={LIMIT})...")
        rows = cargo_query(tables, fields, where=where, order_by=order_by,
                            limit=LIMIT, offset=offset)

        if not rows:
            print(f"[{label}] offset={offset} devolvió 0 filas -> fin de la paginación.")
            break

        all_rows.extend(rows)
        print(f"[{label}] +{len(rows)} filas (total acumulado: {len(all_rows)})")

        if len(rows) < LIMIT:
            # última página parcial, no hace falta seguir pidiendo
            break

        offset += LIMIT
        time.sleep(DELAY_SECONDS)

    return all_rows


def main():
    out_dir = RAW_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Items ---
    # Campos mínimos acordados en el doc 03, sección "Qué falta hacer".
    # damagetype/defense agregados después (ver doc 07): confirmados en
    # vivo contra la API real -- damagetype devuelve "Melee"/"Ranged"/
    # "Magic"/"Summon" (con mayúscula inicial, no en minúscula como se
    # asumía al principio), defense es un entero limpio como string (no
    # necesita regex, a diferencia de sell/rare).
    items_fields = "itemid,name,type,rare,damage,sell,imagefile,damagetype,defense"
    items = extract_table(
        tables="Items",
        fields=items_fields,
        where="itemid>0",          # descarta filas de "sets" (itemid null)
        order_by="itemid",
        label="Items",
    )
    items_path = out_dir / "raw_items.json"
    items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Items: {len(items)} filas guardadas en {items_path}")

    time.sleep(DELAY_SECONDS)

    # --- Recipes ---
    # 'legacy' es obligatorio (ver doc 03) para poder filtrar recetas vigentes
    # en el post-procesamiento.
    recipes_fields = "result,resultid,amount,station,args,legacy"
    recipes = extract_table(
        tables="Recipes",
        fields=recipes_fields,
        order_by="result",
        label="Recipes",
    )
    recipes_path = out_dir / "raw_recipes.json"
    recipes_path.write_text(json.dumps(recipes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Recipes: {len(recipes)} filas guardadas en {recipes_path}")

    print("\nListo. Corré src/process.py para transformar estos crudos a items.json / recipes.json.")


if __name__ == "__main__":
    main()
