# Terraria Data Pipeline

Pipeline de extracción, limpieza y validación de datos que convierte el catálogo completo de ítems y recetas de crafteo de Terraria (v1.4.5.x) en dos archivos JSON estructurados, listos para consumir desde una aplicación.

**Resultado final:** 6.071 ítems y 3.905 recetas, validados por una suite de 26 tests automatizados de calidad de datos.

## Por qué este proyecto

No es un scraper de "bajar y listo". La fuente de datos (la [Terraria Wiki oficial](https://terraria.wiki.gg/), vía su extensión Cargo) resultó tener más matices de los que la documentación sugería: campos con formatos inconsistentes, IDs duplicados, referencias rotas, HTML sin escapar mezclado con datos numéricos. Cada uno de esos problemas se investigó hasta la causa raíz, no se parcheó a ciegas — y quedó documentado en el proceso.

Ese proceso de investigación es, en buena parte, el objetivo de este repo: mostrar cómo se trabaja con una fuente de datos real e imperfecta, no solo el resultado final.

## Qué hace el pipeline

```
terraria.wiki.gg (API Cargo)
        │
        ▼
   extract.py            → extrae Items y Recipes, paginado, con rate limiting
        │
        ▼
raw_items.json / raw_recipes.json     (datos crudos, sin transformar)
        │
        ▼
   process.py             → limpia, valida tipos, cruza referencias
        │
        ▼
   items.json / recipes.json          (datos finales, listos para consumir)
        │
        ▼
   tests/test_data_quality.py         → 26 tests validan el resultado
```

Dos scripts auxiliares resuelven casos especiales del dataset:
- `extract_categories.py` — mapea los ~30 grupos de ingredientes "intercambiables" del juego (p. ej. cualquier tipo de madera sirve para una receta) a sus IDs reales, scrapeando y parseando la página correspondiente de la wiki.
- `verify_orphan_images.py` — confirma con peticiones HTTP reales, uno por uno, que existen las imágenes de un conjunto de ítems que el pipeline detectó como incompletos en la fuente (ver más abajo).
## Problemas de datos reales, encontrados y resueltos

Esta es la parte que más vale la pena leer. Cada punto es un caso concreto donde el dato no era lo que la documentación de la fuente sugería, y cómo se resolvió con evidencia en vez de suposiciones.

**Formato inconsistente en campos "de lista".** El campo `type` de cada ítem se documentaba como una lista, pero llegaba como un string plano separado por `^` (`"furniture^light source^crafting material"`). Afectaba al 37% de los ítems del dataset. Se detectó comparando el resultado real contra una muestra esperada, no asumiendo que la documentación era correcta.

**IDs duplicados en la fuente.** 11 `itemId` de la tabla `Items` estaban repetidos entre dos ítems distintos — rompía la clave primaria del modelo de datos. Se investigó el patrón (todos caían en el mismo rango de IDs, correspondiente a contenido reciente del juego) antes de decidir cómo resolverlo: se conserva la primera aparición y se reporta el resto para auditoría, en vez de perder el dato silenciosamente.

**Referencias rotas entre tablas.** 67 recetas señalaban un ítem resultado que no existía en la tabla de ítems — la receta estaba completa, pero el ítem no tenía ficha propia. En vez de asumir un bug y descartarlas, se investigó qué eran realmente: 22 sets temáticos de muebles decorativos agregados en una actualización reciente del juego, confirmado cruzando contra la documentación pública de la wiki. La decisión de producto fue no ocultarlos: se completa su nombre y su imagen desde fuentes alternativas (recuperando el nombre directo de la tabla de recetas, y confirmando con peticiones HTTP reales que la imagen correspondiente existe en el servidor) en vez de perder 67 recetas válidas del dataset.

**Categorías de ingredientes "intercambiables".** 335 ingredientes en las recetas no correspondían a un ítem único sino a una categoría del propio juego (p. ej. "cualquier lingote de hierro sirve"). En vez de forzarlos a un ítem arbitrario o descartar la información, se modeló como una relación de uno a muchos, resuelta contra el listado oficial de categorías de la wiki.

**Datos corruptos en filas descontinuadas.** Un pequeño número de filas traía identificadores en formatos no válidos (ej. dos IDs separados por `/`, sufijos inesperados). Se blindó el parseo para descartar esas filas puntuales sin interrumpir la ejecución completa, en lugar de dejar que un caso extremo tumbe todo el proceso.

El registro completo de esta investigación — con evidencia, números exactos y el razonamiento detrás de cada decisión — está en [`docs/03-avance-extraccion-cargo.md`](./docs/03-avance-extraccion-cargo.md).

## Validación de datos, no solo extracción

`tests/test_data_quality.py` corre 26 tests con `pytest` sobre el resultado final: tipos de dato correctos, unicidad de identificadores, ausencia de HTML sin procesar, integridad referencial entre archivos, y límites de tolerancia para los casos especiales documentados arriba. No son tests de código — son tests sobre el contrato del propio dataset, para que cualquier cambio futuro en la fuente (una nueva versión del juego, un cambio en la wiki) se detecte automáticamente en lugar de corromper el resultado en silencio.

## Estructura del repositorio

```
extract.py                    # Extracción desde la API Cargo (paginada, con rate limiting)
extract_categories.py         # Mapeo de categorías de ingredientes intercambiables
verify_orphan_images.py       # Verificación HTTP de imágenes para ítems incompletos en la fuente
process.py                    # Limpieza, validación y transformación al modelo final
tests/test_data_quality.py    # Suite de validación de datos (pytest)

items.json                    # 6.071 ítems del juego
recipes.json                  # 3.905 recetas de crafteo
ingredient_categories.json    # Grupos de ingredientes intercambiables (requerido para leer recipes.json)

duplicate_itemids.json        # Auditoría: IDs duplicados en la fuente, ver README y docs/
orphan_result_ids.json        # Auditoría: recetas sin ítem correspondiente en la fuente
orphan_image_urls.json        # Auditoría: imágenes verificadas para esos casos

docs/03-avance-extraccion-cargo.md   # Registro completo de la investigación, decisión por decisión
ATTRIBUTION.md                 # Fuente, licencia y atribución de los datos
LICENSE                        # Licencia del código (MIT)
```

## Cómo correrlo

Los datos ya están generados (`items.json`, `recipes.json`) — no hace falta correr nada para usarlos. Para reproducir el pipeline desde cero:

```bash
pip install -r requirements.txt

python extract.py              # genera raw_items.json y raw_recipes.json (no versionados, ~2.5 MB)
python extract_categories.py   # genera ingredient_categories.json
python process.py              # genera items.json y recipes.json
python verify_orphan_images.py # genera orphan_image_urls.json

python -m pytest tests/ -v     # corre la suite de validación — 26 passed
```

## Modelo de datos

```
items.json    → { id, category, subcategory, imageUrl, rarity, damage?, sellValue? }
recipes.json  → { id, resultItemId, resultQuantity, ingredients[], station, requiredCondition,
                   resultName?, resultImageUrl? }   ← estos dos últimos, solo en casos incompletos en la fuente
```

`ingredients[]` es una lista de `{ itemId, quantity }`, o `{ itemId: null, quantity, categoryHint }` cuando el ingrediente es una categoría intercambiable en vez de un ítem específico.

## Fuente y licencia de los datos

Extraído de la [Official Terraria Wiki](https://terraria.wiki.gg/) vía su API pública de MediaWiki (extensión Cargo). Los datos se distribuyen bajo la misma licencia CC BY-NC-SA 4.0 de la fuente — ver [ATTRIBUTION.md](./ATTRIBUTION.md) para el detalle completo. El código de este repositorio es de mi autoría.

Terraria es propiedad de Re-Logic. Este es un proyecto independiente, sin afiliación oficial.
