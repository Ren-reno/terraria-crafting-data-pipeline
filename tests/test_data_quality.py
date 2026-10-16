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
import random
import sys
import warnings
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

# --- Política de conteos (leer antes de editar los tests de abajo) ----------
# La wiki cambia sola (parches del juego, migración de fichas). Un conteo
# EXACTO hace que el pipeline "se rompa" cada vez que eso pasa, aunque los
# datos estén bien. Por eso estos tests usan LÍMITES RELATIVOS (% del total)
# que solo fallan ante algo realmente anómalo (p. ej. un bug de parseo que
# deja miles de items sin categoría). El valor histórico conocido se conserva
# como referencia: si el número real se aleja de él, el test NO falla pero
# emite un warning visible en el resumen de pytest, para enterarse igual.
def avisar_si_cambio(nombre, actual, conocido):
    if actual != conocido:
        warnings.warn(
            f"{nombre}: {actual} (referencia histórica: {conocido}). Cambio "
            f"dentro de lo tolerado; revisar si es contenido nuevo de la wiki "
            f"y, si es así, actualizar la referencia.",
            UserWarning,
            stacklevel=2,
        )


def _pares_id_contenido(lista_recetas):
    """Lista ordenada de (id, contenido-sin-id): permite comparar dos asignaciones
    de ids sin depender del orden de las filas."""
    return sorted(
        (r["id"], json.dumps({k: v for k, v in r.items() if k != "id"}, sort_keys=True))
        for r in lista_recetas
    )


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
def assign_stable_ids():
    # process.py vive en la raíz del repo; se agrega al path para que el test
    # funcione igual con `pytest` que con `python -m pytest`.
    sys.path.insert(0, str(DATA_DIR))
    try:
        from process import assign_stable_ids as fn
    finally:
        sys.path.remove(str(DATA_DIR))
    return fn


@pytest.fixture(scope="module")
def ingredient_categories():
    path = DATA_DIR / "ingredient_categories.json"
    if not path.exists():
        pytest.skip(f"{path} no existe — correr extract_categories.py primero")
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
        KNOWN_DUPLICATE_NAME_COUNT = 7  # referencia histórica
        MAX_DUPLICATE_NAME_RATIO = 0.01  # tolerancia: hasta 1% de los items

        name_counts = Counter(item["name"] for item in items if item.get("name"))
        duplicated_names = {name: count for name, count in name_counts.items() if count > 1}
        limite = MAX_DUPLICATE_NAME_RATIO * len(items)
        assert len(duplicated_names) <= limite, (
            f"{len(duplicated_names)} nombres duplicados entre distintos id "
            f"(límite {limite:.0f}, histórico {KNOWN_DUPLICATE_NAME_COUNT}). "
            f"Ejemplos: {list(duplicated_names.items())[:5]}. Revisar si sigue "
            f"siendo solo variantes de bioma/reskins."
        )
        avisar_si_cambio("nombres duplicados", len(duplicated_names), KNOWN_DUPLICATE_NAME_COUNT)

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
        KNOWN_QUEST_COUNT = 45  # referencia histórica; banda 50%-200%
        quest_items = [i for i in items if i.get("rarity") == "quest"]
        assert 0.5 * KNOWN_QUEST_COUNT <= len(quest_items) <= 2 * KNOWN_QUEST_COUNT, (
            f"{len(quest_items)} items con rarity='quest', fuera de la banda "
            f"{0.5 * KNOWN_QUEST_COUNT:.0f}-{2 * KNOWN_QUEST_COUNT} (histórico "
            f"{KNOWN_QUEST_COUNT}). Revisar si sigue siendo el mismo caso "
            f"(peces del Angler / Strange Plants) o un bug de parseo de rarity."
        )
        avisar_si_cambio("items rarity='quest'", len(quest_items), KNOWN_QUEST_COUNT)

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
        #
        # Actualizado (ver doc 08): subió de 7 a 9 crafteables tras una
        # re-extracción posterior al lanzamiento de Terraria 1.4.5.7/1.4.5.8
        # (parches recientes de la actualización 1.4.5 "Bigger & Boulder",
        # crossover con Palworld, ~ene-ago 2026). Confirmado con evidencia
        # externa, no es un bug: "Trusty Digtoise" (id 6174) es una mejora
        # crafteable de un Pal, agregada en un parche muy reciente -- la
        # wiki oficial confirma "(Digtoise) can now be upgraded into its
        # 'trusty' variant... from crafting". Mismo patrón de siempre:
        # receta ya cargada en Cargo, ficha de ítem (category) sin migrar
        # todavía. El total de null-category (107) no cambió, solo subió
        # cuántos de esos 107 tienen receta.
        KNOWN_NULL_CATEGORY_COUNT = 107  # referencia histórica
        KNOWN_CRAFTEABLE_COUNT = 9  # referencia histórica
        MAX_NULL_CATEGORY_RATIO = 0.05  # hasta 5% de los items
        MAX_CRAFTEABLE_NULL_RATIO = 0.01  # hasta 1% de las recetas

        null_category_items = [i for i in items if i.get("category") is None]
        limite = MAX_NULL_CATEGORY_RATIO * len(items)
        assert len(null_category_items) <= limite, (
            f"{len(null_category_items)} items con category=null, sobre el "
            f"límite de {limite:.0f} (histórico {KNOWN_NULL_CATEGORY_COUNT}). "
            f"¿Se rompió el parseo de 'type' en process.py?"
        )
        avisar_si_cambio("items con category=null", len(null_category_items), KNOWN_NULL_CATEGORY_COUNT)

        null_ids = {i["id"] for i in null_category_items}
        crafteables = [r for r in recipes if r["resultItemId"] in null_ids]
        limite_c = MAX_CRAFTEABLE_NULL_RATIO * len(recipes)
        assert len(crafteables) <= limite_c, (
            f"{len(crafteables)} items con category=null SÍ son crafteables "
            f"(aparecen como resultado de receta), sobre el límite de "
            f"{limite_c:.0f} (histórico {KNOWN_CRAFTEABLE_COUNT}). Revisar si "
            f"es contenido nuevo del juego (ver doc 08) antes de asumir que "
            f"es un bug."
        )
        avisar_si_cambio("items category=null crafteables", len(crafteables), KNOWN_CRAFTEABLE_COUNT)

    def test_damage_type_tiene_valores_dentro_del_set_tolerado(self, items):
        # Confirmado contra datos reales (muestra de 500 items, itemid
        # 1-501, ver doc 07): los valores vistos son "Melee", "Ranged",
        # "Magic", "Summon" -- con mayúscula inicial (no en minúscula como
        # se asumía al principio del pedido). "Thrown" existe en la lógica
        # del módulo Iteminfo de la wiki, pero no se confirmó en una fila
        # real todavía y podría no existir como clase de daño vigente en
        # esta versión del juego (Rogue reemplazó a Thrown en 1.4.x) -- se
        # tolera como válido por si aparece, sin exigirlo.
        #
        # Este test valida que ningún valor FUERA de este set tolerado se
        # cuele (lo cual indicaría un valor nuevo real del juego, o un
        # problema de parseo) -- no exige que los 5 aparezcan.
        TOLERATED_DAMAGE_TYPES = {"Melee", "Ranged", "Magic", "Summon", "Thrown"}

        seen_values = {i["damageType"] for i in items if i.get("damageType")}
        unexpected = seen_values - TOLERATED_DAMAGE_TYPES
        assert not unexpected, (
            f"Valores de damageType no reconocidos: {unexpected}. "
            f"Revisar si es una clase de daño nueva del juego (ej. 'Rogue') "
            f"que haya que sumar al set tolerado, o un problema de parseo."
        )

    def test_damage_type_no_esta_limitado_a_category_weapon(self, items):
        # Hallazgo confirmado en la muestra real (ver doc 07): Iron Pickaxe
        # tiene category="tool", no "weapon", y sin embargo sí tiene
        # damageType="Melee" -- correcto según el juego real (picos/hachas
        # hacen daño de melee a los enemigos). Este test documenta que
        # damageType puede aparecer en categorías distintas a "weapon" a
        # propósito -- si en algún momento se quisiera "arreglar" esto
        # filtrando por category, este test avisaría que rompe un caso real.
        con_damage_type = [i for i in items if i.get("damageType")]
        if not con_damage_type:
            pytest.skip("Ningún item con damageType en este dataset -- nada que validar")

        categories_with_damage_type = {i.get("category") for i in con_damage_type}
        assert categories_with_damage_type != {"weapon"}, (
            "Todos los items con damageType tienen category='weapon' -- si "
            "esto es así en el dataset actual, revisar si sigue siendo cierto "
            "que herramientas (picos, hachas) también tienen damageType en "
            "esta versión de los datos; si de verdad cambió, este test puede "
            "ajustarse o eliminarse."
        )

    def test_defense_es_entero_no_negativo(self, items):
        # Confirmado contra datos reales (muestra de 500 items): defense
        # siempre viene como entero limpio, sin HTML mezclado -- a
        # diferencia de sellValue/rarity, no necesitó regex para parsear.
        for item in items:
            defense = item.get("defense")
            if defense is not None:
                assert isinstance(defense, int) and defense >= 0, (
                    f"defense inválido en item {item['id']}: {defense!r}"
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
        KNOWN_ORPHAN_COUNT = 67  # referencia histórica
        MAX_ORPHAN_RATIO = 0.05  # hasta 5% de las recetas
        huerfanas = [r for r in recipes if r["resultItemId"] not in item_ids]
        limite = MAX_ORPHAN_RATIO * len(recipes)
        assert len(huerfanas) <= limite, (
            f"{len(huerfanas)} recipes huérfanas, sobre el límite de {limite:.0f} "
            f"(histórico {KNOWN_ORPHAN_COUNT}). Revisar si son casos nuevos del "
            f"mismo tipo (sets de muebles sin migrar en la wiki) o un bug "
            f"distinto. Menos huérfanas es buena noticia (la wiki completó fichas)."
        )
        avisar_si_cambio("recetas huérfanas", len(huerfanas), KNOWN_ORPHAN_COUNT)

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
        MIN_IMAGE_COVERAGE = 0.8  # al menos 80% de las huérfanas con imagen
        minimo = MIN_IMAGE_COVERAGE * len(total_huerfanas)
        assert len(huerfanas_con_imagen) >= minimo, (
            f"Solo {len(huerfanas_con_imagen)} de {len(total_huerfanas)} recetas "
            f"huérfanas tienen resultImageUrl (mínimo esperado: {minimo:.0f}). "
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

    def test_todo_categoryhint_existe_en_ingredient_categories(self, recipes, ingredient_categories):
        # Contrato del README: ingredient_categories.json es "requerido para
        # leer recipes.json". Si un categoryHint no tiene entrada en ese
        # archivo, una app que lo consuma no puede resolver el ingrediente.
        # process.py combina el scrape con unas pocas excepciones manuales y
        # las guarda en el archivo (save_ingredient_categories); si este test
        # falla, correr `python process.py` de nuevo.
        hints = {
            ing["categoryHint"]
            for r in recipes for ing in r["ingredients"] if "categoryHint" in ing
        }
        faltan = sorted(hints - set(ingredient_categories))
        assert not faltan, (
            f"{len(faltan)} categoryHint sin entrada en ingredient_categories.json: "
            f"{faltan}. Correr `python process.py` (guarda las excepciones manuales "
            f"en ese archivo) y volver a correr los tests."
        )

    def test_recipe_ids_no_dependen_del_orden_de_entrada(self, recipes, assign_stable_ids):
        # Propiedad central del id de receta: el mismo contenido recibe el mismo
        # id aunque la fuente devuelva las filas en otro orden. (Antes el id
        # usaba un contador global y cambiaba en el 97% de las recetas entre dos
        # extracciones.) Las recetas de contenido idéntico son intercambiables,
        # por eso se compara el conjunto de pares (id, contenido), no fila a fila.
        base = [dict(r) for r in recipes]
        assign_stable_ids(base)
        for semilla in (1, 2, 3):
            barajadas = [dict(r) for r in recipes]
            random.Random(semilla).shuffle(barajadas)
            assign_stable_ids(barajadas)
            assert _pares_id_contenido(barajadas) == _pares_id_contenido(base), (
                "Los ids de receta dependen del orden de entrada: no son estables "
                "entre extracciones. Revisar assign_stable_ids() en process.py."
            )

    def test_recipe_ids_no_cambian_al_quitar_recetas_de_otros_items(self, recipes, assign_stable_ids):
        # Quitar o agregar recetas de OTROS ítems (lo que pasa cuando la wiki
        # cambia contenido ajeno) no debe alterar los ids de un ítem dado.
        completo = [dict(r) for r in recipes]
        assign_stable_ids(completo)

        items_resultado = sorted({r["resultItemId"] for r in recipes})
        conservados = set(items_resultado[::2])  # se queda con la mitad de los ítems
        parcial = [dict(r) for r in recipes if r["resultItemId"] in conservados]
        assign_stable_ids(parcial)

        esperado = [r for r in completo if r["resultItemId"] in conservados]
        assert _pares_id_contenido(parcial) == _pares_id_contenido(esperado), (
            "Quitar recetas de otros ítems cambió los ids de los ítems que se conservaron."
        )

    def test_recipe_ids_son_unicos_y_con_formato_esperado(self, recipes):
        import re
        ids = [r["id"] for r in recipes]
        assert len(ids) == len(set(ids)), "Hay ids de receta repetidos."
        malos = [r["id"] for r in recipes if not re.fullmatch(rf"{r['resultItemId']}-\d+", r["id"])]
        assert not malos, f"ids con formato inesperado (esperado '<resultItemId>-<n>'): {malos[:5]}"

    def test_recipe_ids_de_recipes_json_son_los_canonicos(self, recipes, assign_stable_ids):
        # Contrato: recipes.json fue generado con el esquema estable. Si este test
        # falla, recipes.json se generó con una versión anterior de process.py:
        # correr `python process.py` de nuevo (no usa la red) y volver a testear.
        recalculadas = [dict(r) for r in recipes]
        assign_stable_ids(recalculadas)
        distintos = [(a["id"], b["id"]) for a, b in zip(recipes, recalculadas) if a["id"] != b["id"]]
        assert not distintos, (
            f"{len(distintos)} ids de recipes.json no coinciden con el esquema estable "
            f"(ej. {distintos[:3]}). Correr `python process.py` para regenerar recipes.json."
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
