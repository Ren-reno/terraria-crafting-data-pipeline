#!/usr/bin/env python3
"""
Verifica, uno por uno, si existe realmente el archivo de imagen en
terraria.wiki.gg para cada uno de los 65 ítems "huérfanos" (los que tienen
receta en Cargo pero no fila en la tabla Items, ver doc 03).

Por qué hace falta esto: para el resto de items.json, imageUrl viene del
campo `imagefile` de la tabla Items (dato real de Cargo). Para los
huérfanos no hay ese campo -- la alternativa es construir la URL por
CONVENCIÓN (mismo patrón que el resto: "https://terraria.wiki.gg/images/"
+ nombre.replace(" ", "_") + ".png"), pero eso es una suposición, no un
dato confirmado. Este script confirma cada uno con una petición HTTP real
antes de confiar en la convención.

Uso:
    pip install requests
    python verify_orphan_images.py

Requiere recipes.json en la misma carpeta (para sacar los 65 resultName).

Salida:
    orphan_image_urls.json  -> { "5552": "https://.../Aetherium_Candelabra.png", ... }
        (solo los confirmados que SÍ existen)
    orphan_images_not_found.json  -> lista de los que dieron 404, para
        revisión manual (puede que el nombre de archivo real difiera del
        nombre del ítem)
"""

import json
import time
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": "TerrariaCrafteosBot/0.1 (uso personal, no comercial; "
                  "verificacion puntual de existencia de imagenes)"
}
DELAY_SECONDS = 1.0


def build_candidate_url(name: str) -> str:
    return "https://terraria.wiki.gg/images/" + name.replace(" ", "_") + ".png"


def image_exists(url: str) -> bool:
    """HEAD request: solo pregunta si existe, no descarga la imagen."""
    try:
        resp = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def main():
    base = Path(__file__).parent
    recipes_path = base / "recipes.json"
    if not recipes_path.exists():
        print("❌ Falta recipes.json. Correr process.py primero.")
        return

    recipes = json.loads(recipes_path.read_text(encoding="utf-8"))

    # Sacar los pares (resultItemId, resultName) únicos de las recetas huérfanas
    orphans = {}
    for r in recipes:
        if "resultName" in r:
            orphans[r["resultItemId"]] = r["resultName"]

    print(f"Verificando {len(orphans)} ítems huérfanos contra la wiki real...\n")

    confirmed = {}
    not_found = []

    for i, (item_id, name) in enumerate(sorted(orphans.items()), 1):
        url = build_candidate_url(name)
        exists = image_exists(url)
        status = "✅" if exists else "❌"
        print(f"[{i}/{len(orphans)}] {status} {name} -> {url}")

        if exists:
            confirmed[str(item_id)] = url
        else:
            not_found.append({"itemId": item_id, "name": name, "triedUrl": url})

        time.sleep(DELAY_SECONDS)

    (base / "orphan_image_urls.json").write_text(
        json.dumps(confirmed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ {len(confirmed)} imágenes confirmadas -> orphan_image_urls.json")

    if not_found:
        (base / "orphan_images_not_found.json").write_text(
            json.dumps(not_found, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"⚠️  {len(not_found)} NO encontradas -> orphan_images_not_found.json "
              f"(revisar manualmente, el nombre de archivo real puede diferir)")


if __name__ == "__main__":
    main()
