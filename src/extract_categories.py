#!/usr/bin/env python3
"""
Extrae los ~30 grupos de "ingredientes alternativos" (Any Wood, Any Iron Bar,
etc.) desde la página oficial de la wiki, y cruza los nombres contra
raw_items.json para armar ingredient_categories.json con itemId reales.

Por qué un script aparte en vez de sumarlo a extract.py: esta página NO es
una tabla Cargo, es una página wiki normal con HTML — se parsea distinto
(BeautifulSoup) y es un proceso puntual de una sola vez (estos grupos casi
no cambian entre versiones del juego), no algo que haga falta re-scrapear
en cada corrida.

Uso:
    pip install beautifulsoup4 requests
    python src/extract_categories.py

Requiere data/raw/raw_items.json (generado por extract.py).

Salida:
    ingredient_categories.json  ->  { "Any Iron Bar": [22, 704], ... }
    unmatched_category_members.json  -> nombres que no matchearon con
        ningún itemId (para revisión manual — puede pasar si el nombre en
        la wiki difiere levemente del nombre en la tabla Items)
"""

import json
import re
import time
import html

import requests
from bs4 import BeautifulSoup

from paths import AUDIT_DIR, DATA_DIR, RAW_DIR

URL = "https://terraria.wiki.gg/wiki/Alternative_crafting_ingredients"
HEADERS = {
    "User-Agent": "TerrariaCrafteosBot/0.1 (uso personal, no comercial; "
                  "extraccion puntual de grupos de ingredientes alternativos)"
}


def load_name_to_id():
    raw_items_path = RAW_DIR / "raw_items.json"
    raw_items = json.loads(raw_items_path.read_text(encoding="utf-8"))
    name_to_id = {}
    for it in raw_items:
        if it.get("itemid") not in (None, ""):
            name = html.unescape(it.get("name", "")).strip()
            name_to_id[name] = int(it["itemid"])
    return name_to_id


# Excepciones confirmadas: nombres "Any X" usados en recipes.json que NO
# tienen su propia sección en la página wiki de grupos (probablemente por
# tener muy pocos miembros / uso muy puntual -- "Any Torch" aparece una
# sola vez en todo el dataset de recetas). Se completan a mano porque no
# hay fuente estructurada de la que extraerlos automáticamente.
MANUAL_CATEGORY_OVERRIDES = {
    "Any Torch": ["Torch"],  # ver nota arriba; ampliar si aparecen más casos
}


def fetch_page():
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_groups(html_text):
    """Parsea las secciones 'Any X' de la página y devuelve
    {group_name: [(member_name, internal_item_id_or_None)]}.

    Estructura REAL confirmada inspeccionando el HTML (ver debug_page.html):
        <h3><span class="mw-headline" id="Any_Iron_Bar">Any Iron Bar</span></h3>
        <div class="terraria">
        <div class="itemlist"><ul>
            <li><span class="i -w">
                <a href="/wiki/Iron_Bar" title="Iron Bar">...</a>
                <span><span><a title="Iron Bar">Iron Bar</a></span>
                <span class="id">Internal <a>Item ID</a>: 22</span></span>
            </span></li>
            ...
        </ul></div>
        ... (después sigue una tabla enorme de recetas que NO nos interesa)

    Notas de diseño:
    - El id real vive en <span class="mw-headline" id="Any_X">, NO en el <h3>
      (mi primer intento asumía que estaba en el h3 y por eso encontraba 0
      grupos).
    - La lista de miembros es <div class="itemlist"><ul>, no un <ul> suelto
      cualquiera -- hay que anclarse a esa clase para no confundirse con
      otras listas de la página (ej. la tabla de recetas más abajo también
      tiene <ul> dentro de cada celda de ingredientes).
    - El Internal Item ID viene como texto plano "Internal Item ID: N" en
      un <span class="id"> -- se extrae con regex en vez de depender de
      raw_items.json, así no dependemos de que el nombre matchee
      exactamente (es más confiable que cruzar por nombre).
    """
    soup = BeautifulSoup(html_text, "html.parser")
    groups = {}

    # El id real está en el <span class="mw-headline">, no en el <h3> padre.
    headlines = soup.find_all("span", class_="mw-headline", id=re.compile(r"^Any_"))

    for headline in headlines:
        group_id = headline.get("id")
        group_name = group_id.replace("_", " ")

        # El header es el <h3> padre del span; la lista de miembros es el
        # primer <div class="itemlist"> después de ese header.
        header = headline.find_parent(["h3", "h2"])
        itemlist_div = header.find_next("div", class_="itemlist") if header else None
        if not itemlist_div:
            continue

        members = []
        for li in itemlist_div.find_all("li"):
            link = li.find("a", title=True)
            if not link:
                continue
            member_name = link.get("title", "").strip()

            # Internal Item ID vive en un <span class="id"> como texto
            # "Internal Item ID: N" (a veces con un <a> en el medio, por
            # eso se usa get_text() y regex en vez de asumir texto plano).
            id_span = li.find("span", class_="id")
            item_id = None
            if id_span:
                match = re.search(r"Item ID:\s*(\d+)", id_span.get_text())
                if match:
                    item_id = int(match.group(1))

            if member_name and member_name not in [m[0] for m in members]:
                members.append((member_name, item_id))

        if members:
            groups[group_name] = members

    return groups


def main():
    print("Cargando raw_items.json...")
    name_to_id = load_name_to_id()

    print(f"Descargando {URL} ...")
    html_text = fetch_page()

    # Guarda el HTML crudo por si en el futuro la wiki cambia de estructura
    # y hay que re-diagnosticar el parser (ver historial: la primera versión
    # de este parser asumía mal dónde vivía el id del header y devolvía 0
    # grupos hasta inspeccionar este archivo).
    debug_path = RAW_DIR / "debug_page.html"
    debug_path.write_text(html_text, encoding="utf-8")

    print("Parseando grupos...")
    groups = parse_groups(html_text)
    print(f"-> {len(groups)} grupos encontrados.")

    if len(groups) < 25:
        print("⚠️  Muy pocos grupos encontrados comparado con lo esperado (~30). "
              "Revisar debug_page.html: la estructura HTML de la wiki puede "
              "haber cambiado.")

    categories = {}
    unmatched = {}

    for group_name, members in groups.items():
        ids = []
        for member_name, item_id in members:
            if item_id is None:
                # Fallback: la página no traía el Internal Item ID para
                # este miembro (no debería pasar según la estructura
                # observada, pero por las dudas) -> cruzar por nombre.
                item_id = name_to_id.get(member_name)
            if item_id is not None:
                ids.append(item_id)
            else:
                unmatched.setdefault(group_name, []).append(member_name)
        categories[group_name] = ids

    out_dir = DATA_DIR
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (out_dir / "ingredient_categories.json").write_text(
        json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ ingredient_categories.json generado con {len(categories)} grupos.")

    # Completar con las excepciones manuales conocidas (grupos que la wiki
    # no expone como sección propia, ver MANUAL_CATEGORY_OVERRIDES).
    added_manual = []
    for group_name, member_names in MANUAL_CATEGORY_OVERRIDES.items():
        if group_name in categories:
            continue  # ya vino del scrape, no pisar
        ids = [name_to_id[n] for n in member_names if n in name_to_id]
        if ids:
            categories[group_name] = ids
            added_manual.append(group_name)
    if added_manual:
        (out_dir / "ingredient_categories.json").write_text(
            json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"✅ Agregadas {len(added_manual)} excepciones manuales: {added_manual}")
        print(f"✅ Total final: {len(categories)} grupos en ingredient_categories.json")

    if unmatched:
        (AUDIT_DIR / "unmatched_category_members.json").write_text(
            json.dumps(unmatched, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        total_unmatched = sum(len(v) for v in unmatched.values())
        print(f"\n⚠️  {total_unmatched} miembros de grupo sin itemId resuelto. "
              f"Detalle en unmatched_category_members.json — revisar manualmente, "
              f"probablemente nombres con capitalización o acentos distintos.")

    # Muestra rápida para verificar a ojo
    print("\n--- Muestra ---")
    for k in list(categories.keys())[:5]:
        print(f"{k}: {categories[k]}")


if __name__ == "__main__":
    main()
