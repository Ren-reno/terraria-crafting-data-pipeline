"""
Tests de calidad de datos sobre items.json y recipes.json.

Estos tests no verifican "código" en el sentido tradicional — verifican que
el DATASET generado por el pipeline (extract.py -> process.py) cumple el
contrato de datos esperado por la app que lo consume. Cada test documenta
una regla que se descubrió necesaria al toparse con datos reales del wiki
(ver 03-avance-extraccion-cargo.md para el detalle de cada hallazgo).

Uso:
    pip install pytest
    pytest tests/ -v

Requiere que items.json y recipes.json ya existan (correr extract.py y
process.py primero).
"""

import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent.parent

# Campos numéricos válidos de rarity (Terraria usa -13..12 aprox., más el
# string especial "quest" para ítems de misión). Ver doc 03.
VALID_RARITY_TYPES = (int, type(None))
VALID_RARITY_SPECIAL = {"quest"}

# Umbral de tolerancia: cuántos ingredientes sin itemId resuelto es "esperado"
# (son los "Any Iron Bar", "Any Wood", etc. — categorías genéricas del juego,
# no un bug de parseo. Ver doc 03, sección de decisiones pendientes).
# Si este número sube mucho más, probablemente indica un bug de matching real.
MAX_EXPECTED_UNRESOLVED_INGREDIENTS = 400


@pytest.fixture(scope="module")
def items():
    path = DATA_DIR / "items.json"
    if not path.exists():
        pytest.skip(f"{path} no existe — correr extract.py y process.py primero")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def recipes():
    path = DATA_DIR / "recipes.json"
    if not path.exists():
        pytest.skip(f"{path} no existe — correr extract.py y process.py primero")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def item_ids(items):
    return {item["id"] for item in items}


# ---------------------------------------------------------------------------
# items.json — estructura y tipos
# ---------------------------------------------------------------------------

class TestItemsStructure:
    def test_items_no_esta_vacio(self, items):
        assert len(items) > 0, "items.json no debería estar vacío"

    def test_items_tiene_volumen_esperado(self, items):
        # Terraria 1.4.5.x tiene ~5000-6000 items individuales (no sets).
        # Un número muy por fuera de este rango sugiere un problema de
        # extracción (paginación cortada, filtro mal aplicado, etc.)
        assert 4000 <= len(items) <= 8000, (
            f"Cantidad de items ({len(items)}) fuera del rango esperado. "
            f"¿Se cortó la paginación en extract.py?"
        )

    def test_todos_los_items_tienen_id_entero(self, items):
        for item in items:
            assert isinstance(item["id"], int), (
                f"item.id debería ser int, encontrado {type(item['id'])} en {item}"
            )

    def test_todos_los_items_tienen_name_no_vacio(self, items):
        # Confirmado contra datos reales: 'name' nunca viene vacío para una
        # fila con itemid válido (0 casos en 6082 filas crudas). Se agrega
        # como campo obligatorio -- si esto cambia en una futura
        # re-extracción, es una señal real de que algo se rompió, no un
        # caso a tolerar en silencio.
        sin_name = [item["id"] for item in items if not item.get("name") or not item["name"].strip()]
        assert not sin_name, (
            f"{len(sin_name)} item(s) sin 'name' (o vacío): {sin_name[:10]}. "
            f"Esto no debería pasar nunca -- revisar process.py o los datos crudos."
        )

    def test_name_no_es_clave_unica_pero_id_si(self, items):
        # Documentado, no es un bug: 7 nombres se repiten entre 2+ itemid
        # distintos en el dataset FINAL (ej. "Strange Plant" x4, variantes
        # de bioma). Esto significa que la UI/app NUNCA debe usar 'name'
        # como clave para buscar o identificar un ítem -- solo 'id' es
        # única.
        #
        # Nota sobre el número exacto: en raw_items.json (6082 filas, sin
        # deduplicar) hay 9 nombres duplicados, no 7. La diferencia son 2
        # nombres ("Forbidden Lihzahrd Brick Wall", "Silent Fish") cuya
        # única "pareja" duplicada era justo una de las 11 filas
        # descartadas por itemid duplicado (ver duplicate_itemids.json) --
        # al perder su pareja, esos 2 nombres pasaron a ser únicos en el
        # archivo final. Confirmado cruzando ambos archivos, no es
        # coincidencia. Por eso este test valida contra items.json (el
        # dato real que consume la app), no contra el crudo.
        from collections import Counter
        KNOWN_DUPLICATE_NAME_COUNT = 7

        name_counts = Counter(item["name"] for item in items if item.get("name"))
        duplicated_names = {name: count for name, count in name_counts.items() if count > 1}
        assert len(duplicated_names) == KNOWN_DUPLICATE_NAME_COUNT, (
            f"{len(duplicated_names)} nombres duplicados entre distintos id, "
            f"distinto al valor conocido de {KNOWN_DUPLICATE_NAME_COUNT}. "
            f"Ejemplos: {list(duplicated_names.items())[:5]}. Si subió mucho, "
            f"revisar si sigue siendo solo variantes de bioma/reskins."
        )

    def test_ids_son_unicos(self, items):
        # Se descubrió en la extracción real que la wiki puede devolver el
        # mismo itemid para dos ítems distintos (11 casos en ~6000 items,
        # todos en el rango de contenido reciente). process.py debe
        # descartar los duplicados y quedarse con la primera aparición.
        ids = [item["id"] for item in items]
        duplicated = {i for i in ids if ids.count(i) > 1}
        assert not duplicated, (
            f"Hay {len(duplicated)} id(s) duplicados en items.json: {duplicated}. "
            f"process.py debería haberlos deduplicado."
        )

    def test_todos_los_items_tienen_category(self, items):
        # category puede faltar en la wiki, pero no debería ser un string
        # con '^' sin separar (bug histórico: 'type' venía como string
        # plano delimitado por '^', no como lista ya parseada).
        for item in items:
            category = item.get("category")
            if category is not None:
                assert "^" not in category, (
                    f"category de item {item['id']} contiene '^' sin separar: "
                    f"{category!r} — indica que el split de 'type' no se aplicó"
                )

    def test_rarity_tiene_tipo_valido(self, items):
        for item in items:
            rarity = item.get("rarity")
            is_valid_int_or_none = isinstance(rarity, VALID_RARITY_TYPES)
            is_valid_special = rarity in VALID_RARITY_SPECIAL
            assert is_valid_int_or_none or is_valid_special, (
                f"rarity inválido en item {item['id']}: {rarity!r} "
                f"(tipo {type(rarity)}). Posible wikitext sin parsear."
            )

    def test_rarity_no_contiene_html_sin_parsear(self, items):
        # Se descubrió que ~12 items traen el wikitext crudo de rarity
        # (ej. '<span class="rarity">...') en vez de un entero limpio.
        # Este test asegura que el fallback de parseo en process.py los
        # resolvió (o al menos que no quedó HTML crudo en el dataset final).
        for item in items:
            rarity = item.get("rarity")
            if isinstance(rarity, str):
                assert "<" not in rarity and ">" not in rarity, (
                    f"rarity de item {item['id']} contiene HTML sin parsear: "
                    f"{rarity!r}"
                )

    def test_sell_value_es_no_negativo(self, items):
        for item in items:
            sell_value = item.get("sellValue")
            if sell_value is not None:
                assert isinstance(sell_value, int) and sell_value >= 0, (
                    f"sellValue inválido en item {item['id']}: {sell_value!r}"
                )

    def test_image_url_tiene_formato_esperado(self, items):
        for item in items:
            image_url = item.get("imageUrl")
            if image_url is not None:
                assert image_url.startswith("https://terraria.wiki.gg/images/"), (
                    f"imageUrl con formato inesperado en item {item['id']}: {image_url!r}"
                )
                assert " " not in image_url, (
                    f"imageUrl de item {item['id']} contiene espacios sin "
                    f"reemplazar por '_': {image_url!r}"
                )

    def test_rarity_quest_tiene_count_conocido_y_no_craftea(self, items, recipes):
        # Decisión de producto documentada (ver doc 04): "quest" es un tier
        # de rareza OFICIAL del juego (peces del Angler, Strange Plants),
        # no un dato roto -- no se convierte a número. Se vigila que (a) el
        # conteo no cambie sin avisar y (b) ninguno de estos ítems participe
        # en crafteo, que es la razón por la que no bloquea el resto del
        # pipeline. Si (b) deja de cumplirse, sí habría que resolverlo antes
        # de mostrar esa receta en la UI.
        KNOWN_QUEST_COUNT = 45
        quest_items = [i for i in items if i.get("rarity") == "quest"]
        assert len(quest_items) == KNOWN_QUEST_COUNT, (
            f"{len(quest_items)} items con rarity='quest', distinto al valor "
            f"conocido de {KNOWN_QUEST_COUNT}. Revisar si sigue siendo el "
            f"mismo caso (peces del Angler / Strange Plants) o algo nuevo."
        )

        quest_ids = {i["id"] for i in quest_items}
        en_recetas = [
            r["id"] for r in recipes
            if r["resultItemId"] in quest_ids
            or any(ing.get("itemId") in quest_ids for ing in r["ingredients"])
        ]
        assert not en_recetas, (
            f"{len(en_recetas)} receta(s) involucran un ítem con rarity='quest' "
            f"(como resultado o ingrediente): {en_recetas[:5]}. Esto rompe el "
            f"supuesto de que 'quest' no afecta pantallas de crafteo -- revisar "
            f"cómo mostrar rarity en ese caso puntual antes de continuar."
        )

    def test_category_null_tiene_count_conocido_y_pocos_crafteables(self, items, recipes):
        # Decisión de producto documentada (ver doc 04): 107 items sin
        # category (la wiki no completó ese campo -- mismo patrón de "hueco
        # de mantenimiento" que las recetas huérfanas, ver doc 03). De esos,
        # solo un puñado participa en crafteo y le importa a la pantalla
        # principal de la app; el resto es aceptable resolverlo con una
        # categoría de respaldo ("Otros") en el frontend, sin tocar el
        # pipeline. Se vigilan ambos conteos para detectar cambios.
        KNOWN_NULL_CATEGORY_COUNT = 107
        KNOWN_CRAFTEABLE_COUNT = 7

        null_category_items = [i for i in items if i.get("category") is None]
        assert len(null_category_items) == KNOWN_NULL_CATEGORY_COUNT, (
            f"{len(null_category_items)} items con category=null, distinto al "
            f"valor conocido de {KNOWN_NULL_CATEGORY_COUNT}."
        )

        null_ids = {i["id"] for i in null_category_items}
        crafteables = [r for r in recipes if r["resultItemId"] in null_ids]
        assert len(crafteables) == KNOWN_CRAFTEABLE_COUNT, (
            f"{len(crafteables)} items con category=null SÍ son crafteables "
            f"(aparecen como resultado de receta), distinto al valor conocido "
            f"de {KNOWN_CRAFTEABLE_COUNT}. Si subió, revisar si vale la pena "
            f"mapear esos casos a mano en process.py en vez de dejarlos para "
            f"el frontend."
        )


# ---------------------------------------------------------------------------
# recipes.json — estructura y tipos
# ---------------------------------------------------------------------------

class TestRecipesStructure:
    def test_recipes_no_esta_vacio(self, recipes):
        assert len(recipes) > 0, "recipes.json no debería estar vacío"

    def test_recipes_tiene_volumen_esperado(self, recipes):
        assert 3000 <= len(recipes) <= 6000, (
            f"Cantidad de recipes ({len(recipes)}) fuera del rango esperado."
        )

    def test_ninguna_recipe_es_legacy(self, recipes):
        # legacy=1 debería haberse filtrado en process.py. No hay campo
        # 'legacy' expuesto en el modelo final, así que esto se valida
        # indirectamente: todas las recipes deben tener resultItemId válido
        # (las legacy con resultid vacío nunca deberían haber llegado acá).
        for recipe in recipes:
            assert recipe.get("resultItemId") is not None, (
                f"Recipe sin resultItemId: {recipe}. Las filas legacy con "
                f"resultid vacío deberían haberse descartado en process.py."
            )

    def test_result_quantity_es_positivo(self, recipes):
        for recipe in recipes:
            qty = recipe["resultQuantity"]
            assert isinstance(qty, int) and qty >= 1, (
                f"resultQuantity inválido en recipe {recipe['id']}: {qty!r}"
            )

    def test_toda_recipe_tiene_al_menos_un_ingrediente(self, recipes):
        for recipe in recipes:
            assert len(recipe["ingredients"]) >= 1, (
                f"Recipe {recipe['id']} no tiene ingredientes"
            )

    def test_ingredient_quantity_es_positivo(self, recipes):
        for recipe in recipes:
            for ing in recipe["ingredients"]:
                assert isinstance(ing["quantity"], int) and ing["quantity"] >= 1, (
                    f"quantity inválido en ingrediente de recipe {recipe['id']}: {ing}"
                )

    def test_station_es_lista_o_none(self, recipes):
        for recipe in recipes:
            station = recipe.get("station")
            assert station is None or isinstance(station, list), (
                f"station debería ser lista o None en recipe {recipe['id']}: {station!r}"
            )
            if station is not None:
                assert len(station) >= 1, (
                    f"station es una lista vacía en recipe {recipe['id']} "
                    f"— debería ser None en ese caso, no []"
                )

    def test_station_y_required_condition_no_ambos_none_si_habia_dato(self, recipes):
        # Si la fila original de Cargo tenía station, al menos uno de los
        # dos campos (station o requiredCondition) debe tener contenido.
        # No podemos saber acá si "originalmente" tenía dato, pero sí
        # podemos chequear que no queden strings vacíos en required_condition.
        for recipe in recipes:
            cond = recipe.get("requiredCondition")
            if cond is not None:
                assert cond.strip() != "", (
                    f"requiredCondition vacío (debería ser None) en recipe {recipe['id']}"
                )


# ---------------------------------------------------------------------------
# Integridad referencial entre items.json y recipes.json
# ---------------------------------------------------------------------------

class TestIntegridadReferencial:
    def test_result_item_id_huerfanas_tiene_count_conocido(self, recipes, item_ids):
        # Este test documenta la respuesta a la pregunta pendiente del doc
        # 03: ¿alguna recipe activa referencia un itemId que no existe en
        # items.json? SÍ, 67 recipes (65 resultItemId únicos) — sets
        # temáticos de muebles (ej. "Aetherium Candelabra/Candle/Door") que
        # tienen receta completa en Cargo pero cuya ficha individual nunca
        # llegó a la tabla Items (confirmado: contenido de la versión
        # 1.4.5.0, probablemente pendiente de migración de infobox en la
        # wiki, no un hueco permanente del juego).
        #
        # Decisión de producto (ver doc 03): NO se filtran. Se muestran
        # parcialmente vía el campo resultName (ver test siguiente). Este
        # test solo vigila que el conteo no cambie sin que nos enteremos —
        # si cambia, alguien debe revisar si sigue siendo el mismo caso
        # conocido o es un problema nuevo.
        KNOWN_ORPHAN_COUNT = 67
        huerfanas = [r for r in recipes if r["resultItemId"] not in item_ids]
        assert len(huerfanas) == KNOWN_ORPHAN_COUNT, (
            f"{len(huerfanas)} recipes huérfanas encontradas, distinto al valor "
            f"conocido de {KNOWN_ORPHAN_COUNT}. Si subió: revisar si son casos "
            f"nuevos del mismo tipo (sets de muebles sin migrar en la wiki) o un "
            f"bug distinto. Si bajó: la wiki completó infoboxes que faltaban, "
            f"buena noticia -- actualizar KNOWN_ORPHAN_COUNT en este test."
        )

    def test_result_item_id_huerfanas_tienen_result_name(self, recipes, item_ids):
        # Contrato de datos (ver doc 03, "Decisión: mostrar huérfanas
        # parcial"): toda recipe cuyo resultItemId no existe en items.json
        # DEBE tener resultName no vacío, para que la app tenga algo que
        # mostrar (nombre en inglés desde Recipes.result) aunque no pueda
        # resolver ícono/rareza/categoría vía items.json.
        huerfanas = [r for r in recipes if r["resultItemId"] not in item_ids]
        sin_result_name = [
            r for r in huerfanas
            if not r.get("resultName") or not r["resultName"].strip()
        ]
        assert not sin_result_name, (
            f"{len(sin_result_name)} recipe(s) huérfana(s) sin resultName "
            f"(o vacío) -- la app no tendría nada que mostrar para estas. "
            f"Ejemplos: {[r['id'] for r in sin_result_name[:5]]}"
        )

    def test_result_name_solo_aparece_en_huerfanas(self, recipes, item_ids):
        # El campo resultName es una excepción puntual, no parte del
        # contrato normal de recipes.json (ver nota en process.py) -- no
        # debería aparecer en recetas cuyo resultItemId sí resuelve bien,
        # para no duplicar información que ya se resuelve vía items.json.
        con_result_name_normal = [
            r for r in recipes
            if r["resultItemId"] in item_ids and r.get("resultName")
        ]
        assert not con_result_name_normal, (
            f"{len(con_result_name_normal)} recipe(s) NO huérfana(s) tienen "
            f"resultName de todas formas -- inesperado, revisar process.py."
        )

    def test_result_image_url_solo_aparece_en_huerfanas_y_es_https(self, recipes, item_ids):
        # resultImageUrl (ver doc 03, "Resuelto: imágenes de las recetas
        # huérfanas") es opcional -- solo está presente si
        # verify_orphan_images.py confirmó con HTTP real que el archivo
        # existe (no toda huérfana tiene que tenerlo, a diferencia de
        # resultName). Igual que resultName, no debería filtrarse a
        # recetas normales, y cuando está presente debe ser una URL https
        # bien formada, no un valor vacío o roto.
        con_image_url_normal = [
            r for r in recipes
            if r["resultItemId"] in item_ids and r.get("resultImageUrl")
        ]
        assert not con_image_url_normal, (
            f"{len(con_image_url_normal)} recipe(s) NO huérfana(s) tienen "
            f"resultImageUrl de todas formas -- inesperado, revisar process.py."
        )

        huerfanas_con_imagen = [
            r for r in recipes
            if r["resultItemId"] not in item_ids and r.get("resultImageUrl")
        ]
        mal_formadas = [
            r for r in huerfanas_con_imagen
            if not r["resultImageUrl"].startswith("https://terraria.wiki.gg/images/")
        ]
        assert not mal_formadas, (
            f"{len(mal_formadas)} resultImageUrl con formato inesperado. "
            f"Ejemplos: {[r['resultImageUrl'] for r in mal_formadas[:3]]}"
        )

        # Umbral mínimo, no solo "no debe estar mal formado". Detectado en
        # revisión externa: si process.py corre ANTES de que
        # orphan_image_urls.json exista (orden de pasos incorrecto), todas
        # las huérfanas quedan sin resultImageUrl y el chequeo de arriba
        # (que solo valida formato) pasa igual, en falso positivo. Este
        # umbral evita que ese desfase de timing pase desapercibido:
        # verify_orphan_images.py confirmó 65/67 en la corrida real (ver
        # doc 03), así que un número muy menor indica que orphan_image_urls.json
        # no se cargó, no un cambio legítimo en los datos.
        total_huerfanas = [r for r in recipes if r["resultItemId"] not in item_ids]
        MIN_EXPECTED_WITH_IMAGE = 60
        assert len(huerfanas_con_imagen) >= MIN_EXPECTED_WITH_IMAGE, (
            f"Solo {len(huerfanas_con_imagen)} de {len(total_huerfanas)} recetas "
            f"huérfanas tienen resultImageUrl (mínimo esperado: {MIN_EXPECTED_WITH_IMAGE}). "
            f"Causa más probable: process.py corrió antes de que "
            f"orphan_image_urls.json existiera -- correr verify_orphan_images.py "
            f"y luego process.py de nuevo, en ese orden."
        )

    def test_ingredientes_sin_itemid_tienen_categoryhint(self, recipes):
        # Contrato de datos (ver doc 03, "Resuelto: mapeo de ingredientes
        # 'Any X'..."): un ingrediente sin itemId directo (categorías tipo
        # "Any Iron Bar", donde varias alternativas son válidas) debe tener
        # categoryHint con el nombre del grupo, para que la app pueda
        # resolverlo contra ingredient_categories.json. Si un ingrediente
        # queda sin itemId Y sin categoryHint, es una referencia rota que
        # la app no puede mostrar de ninguna forma.
        sin_ninguno = [
            (r["id"], ing) for r in recipes for ing in r["ingredients"]
            if ing["itemId"] is None and "categoryHint" not in ing
        ]
        assert not sin_ninguno, (
            f"{len(sin_ninguno)} ingrediente(s) sin itemId Y sin categoryHint "
            f"(referencia irresoluble para la app). Ejemplos: {sin_ninguno[:5]}. "
            f"Si son nombres nuevos tipo '(bait)' o categorías abiertas, "
            f"agregar a manual_extras en load_ingredient_categories() (process.py)."
        )

    def test_porcentaje_de_ingredientes_sin_resolver_es_razonable(self, recipes):
        # Se espera que un puñado de ingredientes queden sin itemId por ser
        # placeholders de categoría del juego ("Any Iron Bar", "Any Wood",
        # etc. — no tienen itemId individual por diseño, ver doc 03).
        # Este test NO exige cero unresolved (sería incorrecto pedirlo),
        # pero sí pone un techo: si el número sube mucho, probablemente
        # indica un bug de matching de nombres, no más placeholders nuevos.
        total_ingredients = sum(len(r["ingredients"]) for r in recipes)
        unresolved = sum(
            1 for r in recipes for ing in r["ingredients"] if ing["itemId"] is None
        )
        assert unresolved <= MAX_EXPECTED_UNRESOLVED_INGREDIENTS, (
            f"{unresolved} ingredientes sin itemId resuelto de {total_ingredients} "
            f"totales — supera el umbral esperado de {MAX_EXPECTED_UNRESOLVED_INGREDIENTS}. "
            f"Revisar si es un bug de matching nuevo, no solo placeholders "
            f"tipo 'Any X'."
        )

    def test_item_ids_de_ingredientes_resueltos_existen(self, recipes, item_ids):
        # Si un ingrediente SÍ tiene itemId (no None), ese id debe existir
        # de verdad en items.json — si no, el diccionario name->itemid de
        # process.py generó una referencia inválida.
        invalidos = [
            (r["id"], ing) for r in recipes for ing in r["ingredients"]
            if ing["itemId"] is not None and ing["itemId"] not in item_ids
        ]
        assert not invalidos, (
            f"{len(invalidos)} ingrediente(s) con itemId que no existe en "
            f"items.json: {invalidos[:5]}"
        )
