#!/usr/bin/env python3
"""
Post-procesamiento: toma raw_items.json / raw_recipes.json (salida de extract.py)
y produce items.json / recipes.json según el modelo de datos definido en los
docs 02/03 del proyecto.

Uso:
    python process.py

Requiere que extract.py ya se haya corrido antes en la misma carpeta.
"""

import json
import re
import html
from pathlib import Path

BASE = Path(__file__).parent

# Lista curada de "estaciones" que en realidad no son ítems poseíbles/craftables
# (objetos o condiciones especiales del mundo). Ver doc 03, sección
# "station compuesto: distinguir mueble real de condición ambiental".
# Se separan en dos grupos: las que SÍ representan un requisito real aunque
# no tengan imagen de ítem (van a `station`), y las que son condiciones
# ambientales (van a `requiredCondition`).
KNOWN_NON_ITEM_STATIONS = {
    "Demon Altar", "Crimson Altar", "Shimmer", "By Hand",
    "Honey", "Water", "Placed Bottle", "Placed Bottle only",
    "Lava",  # confirmado en extracción real: mismo patrón que Water/Honey
}
# Normalizaciones de texto (mismo concepto, distinto string en la wiki)
STATION_NORMALIZATION = {
    "Placed Bottle only": "Placed Bottle",
}
# Condiciones ambientales confirmadas hasta ahora (ver doc 03 + extracción real)
KNOWN_ENVIRONMENTAL_CONDITIONS = {
    "Ecto Mist",
    "Snow Biome",  # confirmado en extracción real: condición de bioma, no mueble
}


def decode_text(s):
    if s is None:
        return None
    return html.unescape(s).strip()


def parse_sell(sell_raw):
    """Extrae el valor numérico de venta desde el HTML doble-escapado.
    Ver doc 03: nunca parsear el HTML visual, solo data-sort-value="N".
    """
    if not sell_raw:
        return None
    unescaped = html.unescape(sell_raw)
    match = re.search(r'data-sort-value="(\d+)"', unescaped)
    if match:
        return int(match.group(1))
    return None


def parse_damage(damage_raw):
    if damage_raw in (None, ""):
        return None
    try:
        return int(str(damage_raw).strip())
    except ValueError:
        return None


def parse_defense(defense_raw):
    """Confirmado contra datos reales (500 filas de muestra, itemid 1-501):
    siempre viene como entero limpio, sin HTML mezclado -- a diferencia de
    'sell'/'rare', no necesita regex. Mismo patrón que parse_damage.
    """
    if defense_raw in (None, ""):
        return None
    try:
        return int(str(defense_raw).strip())
    except ValueError:
        return None


def parse_damage_type(damage_type_raw):
    """Confirmado contra datos reales: valores vistos son 'Melee', 'Ranged',
    'Magic', 'Summon' (con mayúscula inicial). 'Thrown' existe en la lógica
    del módulo Iteminfo de la wiki pero no se confirmó en una fila real
    todavía -- se acepta igual si aparece, sin lista cerrada de valores
    válidos (evitar descartar un valor legítimo por no estar en una lista
    hardcodeada). Ver test correspondiente para el set de valores vigilado.
    """
    if damage_type_raw in (None, ""):
        return None
    return decode_text(damage_type_raw)


def parse_rare(rare_raw):
    """Parsea 'rare'. La mayoría de las veces viene como entero limpio (o
    el string literal 'quest'), pero un puñado de filas (~12 en el dataset
    real) traen el wikitext SIN procesar, con forma
    '<span class="rarity">...Rarity color N.png...' o
    'data-sort-value="NN"'. En esos casos se extrae el número de ahí.
    """
    if rare_raw in (None, ""):
        return None
    raw = str(rare_raw).strip()

    if raw == "quest":
        return "quest"

    try:
        return int(raw)
    except ValueError:
        pass

    # Caso wikitext sin procesar: intentar data-sort-value="NN" primero
    match = re.search(r'data-sort-value="(-?\d+)"', raw)
    if match:
        return int(match.group(1))

    # Fallback: "Rarity color N.png" / "Rarity level: N"
    match = re.search(r'[Rr]arity[ _]color[ _](-?\d+)\.png', raw)
    if match:
        return int(match.group(1))
    match = re.search(r'[Rr]arity level:?\s*(-?\d+)', raw)
    if match:
        return int(match.group(1))

    UNPARSED_RARE.add(raw[:80])
    return None


UNPARSED_RARE = set()


def build_image_url(imagefile):
    if not imagefile:
        return None
    return "https://terraria.wiki.gg/images/" + imagefile.strip().replace(" ", "_")


def process_items(raw_items):
    """Convierte filas crudas de Items -> lista de items.json + diccionario name->itemid.

    Nota sobre itemid duplicados: la API real devuelve un puñado de itemid
    repetidos entre dos páginas distintas (ej. id 5036 = "Otherworldly Music
    Box (Lunar Boss)" Y "Ocram Trophy" a la vez). Como itemid es la clave
    primaria del modelo de datos, no se pueden guardar ambos. Se conserva la
    PRIMERA aparición y se reportan los descartes en duplicate_itemids.json
    para revisión manual (probablemente sean 2 templates de recipe/infobox
    distintos apuntando al mismo id por error de la wiki).

    Nota sobre 'name': se agrega directo en cada item (nombre en inglés,
    tal como viene de la wiki) además de usarse como clave del diccionario
    name_to_id interno. Confirmado contra datos reales: nunca viene vacío
    para una fila con itemid válido, pero NO es único -- 9 nombres se
    repiten entre 2+ itemid distintos (ej. "Strange Plant" aparece 4 veces,
    variantes de bioma). Por eso 'name' es solo un dato descriptivo, nunca
    una clave -- la clave única sigue siendo 'id'.
    """
    items = []
    name_to_id = {}
    seen_ids = set()

    for row in raw_items:
        itemid = row.get("itemid")
        if itemid in (None, ""):
            continue  # sets compuestos, ya filtrados con where=itemid>0 pero por las dudas
        itemid = int(itemid)

        if itemid in seen_ids:
            DUPLICATE_ITEMIDS.append({"itemid": itemid, "name": row.get("name"), "row": row})
            continue
        seen_ids.add(itemid)

        name = decode_text(row.get("name"))
        if name:
            name_to_id[name] = itemid

        # 'type' viene como string plano delimitado por '^', NO como lista
        # ya parseada (confirmado con datos reales, a diferencia de lo que
        # se esperaba). Ejemplo real: "furniture^light source^crafting material"
        type_raw = row.get("type") or ""
        type_list = [t for t in type_raw.split("^") if t] if isinstance(type_raw, str) else list(type_raw)

        category = type_list[0] if len(type_list) > 0 else None
        subcategory = type_list[1] if len(type_list) > 1 else None

        item = {
            "id": itemid,
            "name": name,
            "category": category,
            "subcategory": subcategory,
            "imageUrl": build_image_url(row.get("imagefile")),
            "rarity": parse_rare(row.get("rare")),
        }

        damage = parse_damage(row.get("damage"))
        if damage is not None:
            item["damage"] = damage

        damage_type = parse_damage_type(row.get("damagetype"))
        if damage_type is not None:
            item["damageType"] = damage_type

        defense = parse_defense(row.get("defense"))
        if defense is not None:
            item["defense"] = defense

        sell_value = parse_sell(row.get("sell"))
        if sell_value is not None:
            item["sellValue"] = sell_value

        items.append(item)

    return items, name_to_id


def parse_args(args_raw):
    """Parsea el campo 'args' de Recipes: split '^' luego '¦' -> [{name, quantity}]."""
    if not args_raw:
        return []
    ingredients = []
    for chunk in args_raw.split("^"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("¦")
        if len(parts) != 2:
            continue
        name, qty = parts
        name = decode_text(name)
        try:
            qty = int(qty)
        except ValueError:
            qty = 1
        ingredients.append({"name": name, "quantity": qty})
    return ingredients


def parse_station(station_raw, name_to_id):
    """Devuelve (station_list_or_None, required_condition_or_None) según la
    heurística híbrida acordada en el doc 03.
    """
    if not station_raw:
        return None, None

    station_raw = decode_text(station_raw)
    parts = [p.strip() for p in station_raw.split(" and ") if p.strip()]

    stations = []
    condition = None

    for part in parts:
        normalized = STATION_NORMALIZATION.get(part, part)

        if normalized in name_to_id:
            # coincide con un ítem real de la tabla Items -> mueble normal
            stations.append(normalized)
        elif normalized in KNOWN_NON_ITEM_STATIONS:
            stations.append(normalized)
        elif normalized in KNOWN_ENVIRONMENTAL_CONDITIONS:
            condition = normalized
        else:
            # valor no clasificado: se deja como station por defecto, pero
            # se reporta para revisión manual (ver unknown_stations.json)
            stations.append(normalized)
            UNKNOWN_STATIONS.add(normalized)

    return (stations if stations else None), condition


UNKNOWN_STATIONS = set()
DUPLICATE_ITEMIDS = []
MALFORMED_RESULTIDS = set()
ORPHAN_RESULT_IDS = set()


def load_ingredient_categories():
    """Carga ingredient_categories.json (generado por extract_categories.py)
    y le suma un puñado de excepciones manuales confirmadas en process.py:
    nombres de ingrediente que NO tienen sección propia en la página wiki
    de grupos (por eso extract_categories.py no los cubre), pero que sí
    son categorías legítimas del juego, confirmadas cruzando manualmente
    contra Items.

    Devuelve {} si el archivo no existe, para que process.py siga
    funcionando aunque ese paso opcional todavía no se haya corrido —
    simplemente no habrá categoryHint en ese caso.
    """
    path = BASE / "ingredient_categories.json"
    categories = {}
    if path.exists():
        categories = json.loads(path.read_text(encoding="utf-8"))

    # Excepciones confirmadas (ver doc 03): "(bait)" son variantes de un
    # ítem real que sí existe en Items sin ese sufijo -- se resuelven a un
    # solo itemId real, no a un grupo de alternativas. "Recorded Music
    # Boxes" es distinto: son 75 ítems "Music Box (X)" distintos (una por
    # cada canción grabable), una categoría abierta/dinámica del juego, no
    # un set finito curado por la wiki -- se deja sin `alternatives` (lista
    # vacía) para no fingir una lista cerrada que no existe; la app deberá
    # tratar este caso mostrando el nombre sin resolver a un ítem concreto.
    manual_extras = {
        "Blue Jellyfish (bait)": [2436],   # = "Blue Jellyfish" en Items
        "Green Jellyfish (bait)": [2437],  # = "Green Jellyfish" en Items
        "Pink Jellyfish (bait)": [2438],   # = "Pink Jellyfish" en Items
        "Recorded Music Boxes": [],        # categoría abierta, ver nota arriba
        "Any Gold Bar": [19, 706],          # = Gold Bar + Platinum Bar (ver doc 08:
                                             # apareció en receta nueva "Format:C",
                                             # no cubierto por extract_categories.py
                                             # en la corrida original -- mismo patrón
                                             # que Any Iron Bar = [Iron Bar, Lead Bar])
        "Any Silver Bar": [21, 705],        # = Silver Bar + Tungsten Bar (ver doc 08:
                                             # apareció en "Harpy Charm", receta ya
                                             # existente que antes resolvía bien --
                                             # la wiki parece haber re-escrito el
                                             # texto del ingrediente con la nueva
                                             # versión del juego, no un ítem nuevo)
    }
    for name, ids in manual_extras.items():
        categories.setdefault(name, ids)

    return categories


def load_orphan_image_urls():
    """Carga orphan_image_urls.json (generado por verify_orphan_images.py,
    que corre localmente y verifica con HTTP real -- no una suposición --
    que cada URL construida por convención existe de verdad en la wiki).
    Devuelve {} si el archivo no existe, para que process.py siga
    funcionando aunque este paso opcional todavía no se haya corrido.
    """
    path = BASE / "orphan_image_urls.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def process_recipes(raw_recipes, name_to_id, valid_item_ids, ingredient_categories, orphan_image_urls):
    recipes = []

    for row in raw_recipes:
        # Filtrar recetas legacy (descontinuadas). El campo puede venir como
        # bool, "0"/"1", 0/1 según cómo lo serialice la API.
        legacy = row.get("legacy")
        if legacy in (1, "1", True, "true"):
            continue

        resultid = row.get("resultid")
        if resultid in (None, ""):
            # confirmado en extracción real: unas pocas filas legacy traen
            # resultid vacío (ej. "Monokuma" set). Ya deberían haberse
            # descartado arriba por legacy=1, pero se cubre por las dudas.
            continue

        # confirmado en extracción real: un puñado de filas legacy traen
        # resultid con formato roto, no un entero puro (ej. "5004 / 1870",
        # "5035sp" — casos de armaduras Dragon con dos ids alternativos, o
        # sufijos). Todos los casos vistos hasta ahora son legacy=1, pero se
        # blinda el parseo por si una futura re-extracción trae un caso así
        # vigente: se descarta esa fila puntual en vez de crashear el script.
        try:
            resultid = int(resultid)
        except ValueError:
            MALFORMED_RESULTIDS.add(str(resultid))
            continue

        amount = row.get("amount")
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            amount = 1

        ingredients_raw = parse_args(row.get("args"))
        ingredients = []
        for ing in ingredients_raw:
            item_id = name_to_id.get(ing["name"])
            ingredient = {
                "itemId": item_id,  # puede quedar None si no se encontró match; revisar en QA
                "quantity": ing["quantity"],
            }
            # Si no hay itemId pero el nombre coincide con un grupo conocido
            # de ingredientes alternativos (ej. "Any Iron Bar" -> [22, 704],
            # ver ingredient_categories.json y doc 03 "Resuelto: mapeo de
            # ingredientes 'Any X'..."), se agrega categoryHint para que la
            # app pueda resolver las alternativas sin necesitar un itemId
            # único (no lo hay -- son varias alternativas válidas).
            if item_id is None and ing["name"] in ingredient_categories:
                ingredient["categoryHint"] = ing["name"]
            ingredients.append(ingredient)

        station_list, required_condition = parse_station(row.get("station"), name_to_id)

        # confirmado en extracción real: 65 resultId referencian ítems que
        # tienen receta en la tabla Recipes pero NUNCA aparecen como fila en
        # la tabla Items (mayormente sets temáticos de muebles: "X
        # Candelabra/Candle/Door", ej. Aetherium, Feywood, Hallowed...). No
        # es un bug de process.py ni de extract.py -- es un hueco real en
        # cómo la wiki modela esos ítems en Cargo (confirmado: la wiki SÍ
        # documenta estos ítems en texto y su receta está completa en
        # Cargo, lo que falta es el infobox individual migrado a la tabla
        # Items -- probablemente temporal, contenido de 1.4.5.0).
        #
        # Decisión de producto (ver doc 03): se muestran parcialmente en
        # vez de filtrarse. Para que la app tenga algo que mostrar sin
        # depender de items.json (que no tiene esta fila), se agrega
        # resultName tomado directo de Recipes.result -- SOLO en este caso
        # excepcional, para no duplicar el nombre en las ~3900 recetas
        # normales que sí resuelven bien contra items.json + i18n.
        is_orphan = resultid not in valid_item_ids
        if is_orphan:
            ORPHAN_RESULT_IDS.add(resultid)

        recipe = {
            "id": f"{resultid}-{len(recipes)}",  # id simple, ver nota abajo
            "resultItemId": resultid,
            "resultQuantity": amount,
            "ingredients": ingredients,
            "station": station_list,
            "requiredCondition": required_condition,
        }
        if is_orphan:
            recipe["resultName"] = decode_text(row.get("result"))
            # URL de imagen confirmada con HTTP real por verify_orphan_images.py
            # (no una suposición -- el usuario corrió el script localmente y
            # confirmó 65/65 con la misma convención usada en build_image_url()
            # para el resto de items.json). Si por algún motivo el diccionario
            # no tiene esta entrada (script no corrido aún, o caso nuevo sin
            # verificar), se omite el campo en vez de inventar una URL sin
            # confirmar.
            image_url = orphan_image_urls.get(str(resultid))
            if image_url:
                recipe["resultImageUrl"] = image_url
        recipes.append(recipe)

    return recipes


def main():
    raw_items_path = BASE / "raw_items.json"
    raw_recipes_path = BASE / "raw_recipes.json"

    if not raw_items_path.exists() or not raw_recipes_path.exists():
        print("❌ Faltan raw_items.json / raw_recipes.json. Corré extract.py primero.")
        return

    raw_items = json.loads(raw_items_path.read_text(encoding="utf-8"))
    raw_recipes = json.loads(raw_recipes_path.read_text(encoding="utf-8"))

    print(f"Procesando {len(raw_items)} items crudos...")
    items, name_to_id = process_items(raw_items)
    print(f"-> {len(items)} items procesados.")

    valid_item_ids = {item["id"] for item in items}
    ingredient_categories = load_ingredient_categories()
    if ingredient_categories:
        print(f"Cargado ingredient_categories.json: {len(ingredient_categories)} grupos.")
    else:
        print("⚠️  ingredient_categories.json no encontrado -- los ingredientes "
              "tipo 'Any X' quedarán sin categoryHint. Correr extract_categories.py "
              "para generarlo (opcional, no bloquea el resto del pipeline).")

    orphan_image_urls = load_orphan_image_urls()
    if orphan_image_urls:
        print(f"Cargado orphan_image_urls.json: {len(orphan_image_urls)} URLs confirmadas.")
    else:
        print("⚠️  orphan_image_urls.json no encontrado -- las recetas huérfanas "
              "quedarán sin resultImageUrl. Correr verify_orphan_images.py "
              "para generarlo (opcional, no bloquea el resto del pipeline).")

    print(f"Procesando {len(raw_recipes)} recipes crudas...")
    recipes = process_recipes(raw_recipes, name_to_id, valid_item_ids, ingredient_categories, orphan_image_urls)
    print(f"-> {len(recipes)} recipes procesadas (legacy descartadas).")

    items_out = BASE / "items.json"
    recipes_out = BASE / "recipes.json"
    items_out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    recipes_out.write_text(json.dumps(recipes, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ {items_out}")
    print(f"✅ {recipes_out}")

    # Reportes de QA para revisión manual
    missing_ingredient_matches = sum(
        1 for r in recipes for ing in r["ingredients"] if ing["itemId"] is None
    )
    unresolved_with_hint = sum(
        1 for r in recipes for ing in r["ingredients"]
        if ing["itemId"] is None and "categoryHint" in ing
    )
    unresolved_without_hint = missing_ingredient_matches - unresolved_with_hint
    if missing_ingredient_matches:
        print(f"\n{missing_ingredient_matches} ingredientes sin itemId directo: "
              f"{unresolved_with_hint} resueltos con categoryHint (esperado, "
              f"grupos 'Any X'), {unresolved_without_hint} sin ninguna resolución.")
        if unresolved_without_hint:
            print(f"⚠️  {unresolved_without_hint} de esos quedaron sin itemId Y sin "
                  f"categoryHint -- revisar manualmente, podría ser un nombre nuevo "
                  f"no cubierto por ingredient_categories.json.")

    if UNKNOWN_STATIONS:
        unknown_path = BASE / "unknown_stations.json"
        unknown_path.write_text(
            json.dumps(sorted(UNKNOWN_STATIONS), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n⚠️  {len(UNKNOWN_STATIONS)} valores de 'station' no reconocidos "
              f"(ni ítem ni excepción curada). Guardados en {unknown_path} para revisar "
              f"si son muebles nuevos, condiciones ambientales nuevas, o casos 'and' "
              f"con nombres de estación distintos a los ya vistos.")

    if DUPLICATE_ITEMIDS:
        dup_path = BASE / "duplicate_itemids.json"
        dup_path.write_text(
            json.dumps(DUPLICATE_ITEMIDS, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n⚠️  {len(DUPLICATE_ITEMIDS)} filas con itemid duplicado fueron "
              f"DESCARTADAS (se conservó solo la primera aparición de cada id). "
              f"Detalle en {dup_path} — revisar manualmente si alguno de estos "
              f"ítems descartados debería tener su propio id.")

    if UNPARSED_RARE:
        print(f"\n⚠️  {len(UNPARSED_RARE)} valores de 'rare' no se pudieron parsear "
              f"a número (quedaron como null). Ejemplos: {list(UNPARSED_RARE)[:3]}")

    if MALFORMED_RESULTIDS:
        malformed_path = BASE / "malformed_resultids.json"
        malformed_path.write_text(
            json.dumps(sorted(MALFORMED_RESULTIDS), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n⚠️  {len(MALFORMED_RESULTIDS)} filas con 'resultid' en formato no "
              f"numérico fueron DESCARTADAS (ej. '5004 / 1870', '5035sp'). "
              f"Detalle en {malformed_path} — hasta ahora todos los casos vistos "
              f"eran legacy, revisar si esto sigue siendo cierto en una re-extracción.")

    if ORPHAN_RESULT_IDS:
        orphan_path = BASE / "orphan_result_ids.json"
        orphan_path.write_text(
            json.dumps(sorted(ORPHAN_RESULT_IDS), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n⚠️  {len(ORPHAN_RESULT_IDS)} resultItemId en recipes.json NO tienen "
              f"un item correspondiente en items.json (la receta existe, el item no). "
              f"Detalle en {orphan_path}. Mayormente sets temáticos de muebles "
              f"(Candelabra/Candle/Door) ausentes de la tabla Items en la wiki. "
              f"La app consumidora debe manejar este caso (ej. mostrar el nombre "
              f"desde recipes sin imagen/rareza, o filtrar estas recetas).")


if __name__ == "__main__":
    main()
