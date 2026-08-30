# Terraria Data Pipeline

Pipeline de extracción, limpieza y validación de datos que convierte el catálogo completo de ítems y recetas de crafteo de Terraria en dos archivos JSON estructurados, listos para consumir desde una aplicación.

**Resultado final:** 6.121 ítems y 3.954 recetas, validados por una suite de 31 tests automatizados de calidad de datos.

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
   tests/test_data_quality.py         → 31 tests validan el resultado
```

Dos scripts auxiliares resuelven casos especiales del dataset:
- `extract_categories.py` — mapea los grupos de ingredientes "intercambiables" del juego (p. ej. cualquier tipo de madera sirve para una receta) a sus IDs reales, scrapeando y parseando la página correspondiente de la wiki.
- `verify_orphan_images.py` — confirma con peticiones HTTP reales, uno por uno, que existen las imágenes de un conjunto de ítems que el pipeline detectó como incompletos en la fuente (ver más abajo).

## Problemas de datos reales, encontrados y resueltos

Esta es la parte que más vale la pena leer. Cada punto es un caso concreto donde el dato no era lo que la documentación de la fuente sugería, y cómo se resolvió con evidencia en vez de suposiciones.

**Formato inconsistente en campos "de lista".** El campo `type` de cada ítem se documentaba como una lista, pero llegaba como un string plano separado por `^` (`"furniture^light source^crafting material"`). Afectaba a más de un tercio de los ítems del dataset. Se detectó comparando el resultado real contra una muestra esperada, no asumiendo que la documentación era correcta.

**IDs duplicados en la fuente.** 12 `itemId` de la tabla `Items` están repetidos entre dos ítems distintos — rompe la clave primaria del modelo de datos. Se investigó el patrón (todos caen en el mismo rango de IDs, correspondiente a contenido reciente del juego) antes de decidir cómo resolverlo: se conserva la primera aparición y se reporta el resto para auditoría, en vez de perder el dato silenciosamente.

**Referencias rotas entre tablas.** 67 recetas señalan un ítem resultado que no existe en la tabla de ítems — la receta está completa, pero el ítem no tiene ficha propia. En vez de asumir un bug y descartarlas, se investigó qué eran realmente: 22 sets temáticos de muebles decorativos agregados en una actualización reciente del juego, confirmado cruzando contra la documentación pública de la wiki. La decisión de producto fue no ocultarlos: se completa su nombre y su imagen desde fuentes alternativas (recuperando el nombre directo de la tabla de recetas, y confirmando con peticiones HTTP reales que la imagen correspondiente existe en el servidor) en vez de perder 67 recetas válidas del dataset.

**Categorías de ingredientes "intercambiables".** Varios cientos de ingredientes en las recetas no corresponden a un ítem único sino a una categoría del propio juego (p. ej. "cualquier lingote de hierro sirve"). En vez de forzarlos a un ítem arbitrario o descartar la información, se modeló como una relación de uno a muchos, resuelta contra el listado oficial de categorías de la wiki.

**Un campo puede depender de otro campo de forma no obvia.** Al agregar `damageType` (clase de arma: Melee/Ranged/Magic/Summon) se encontró que no está limitado a ítems de categoría "arma" — herramientas como picos y hachas también lo tienen, porque hacen daño real a enemigos en el juego. Asumir la relación obvia ("solo las armas tienen tipo de daño") habría sido incorrecto; se confirmó con datos reales antes de escribir el test correspondiente.

**Datos corruptos en filas descontinuadas.** Un pequeño número de filas trae identificadores en formatos no válidos (ej. dos IDs separados por `/`, sufijos inesperados). Se blindó el parseo para descartar esas filas puntuales sin interrumpir la ejecución completa, en lugar de dejar que un caso extremo tumbe todo el proceso.

**Nombres que no son identificadores únicos.** Varios nombres de ítem aparecen repetidos en 2 o más filas distintas (ej. "Strange Plant" con 4 variantes según bioma). El nombre es un dato descriptivo, no una clave — solo `id` lo es, y el modelo de datos y los tests lo dejan explícito para evitar que una futura integración use el nombre como identificador por error.

**Distinguir un bug de un cambio legítimo en la fuente.** Terraria lanzó una actualización de contenido durante el desarrollo de este proyecto. Una re-extracción posterior hizo fallar 2 tests que antes pasaban — no por un error del pipeline, sino porque el juego agregó ítems y recetas nuevas genuinas. En vez de "arreglar" los tests bajándoles la exigencia, se investigó cada fallo con evidencia externa (confirmando la actualización real del juego y el contenido específico involucrado) antes de actualizar los valores esperados, dejando registrado el motivo de cada cambio.

El registro completo de esta investigación — con evidencia, números exactos y el razonamiento detrás de cada decisión — está en [`docs/`](./docs/), empezando por [`03-avance-extraccion-cargo.md`](./docs/03-avance-extraccion-cargo.md).

## Validación de datos, no solo extracción

`tests/test_data_quality.py` corre 31 tests con `pytest` sobre el resultado final: tipos de dato correctos, unicidad de identificadores, ausencia de HTML sin procesar, integridad referencial entre archivos, y límites de tolerancia para los casos especiales documentados arriba. No son tests de código — son tests sobre el contrato del propio dataset, para que cualquier cambio futuro en la fuente (una nueva versión del juego, un cambio en la wiki) se detecte automáticamente en lugar de corromper el resultado en silencio.

## Estructura del repositorio

```
extract.py                    # Extracción desde la API Cargo (paginada, con rate limiting)
extract_categories.py         # Mapeo de categorías de ingredientes intercambiables
verify_orphan_images.py       # Verificación HTTP de imágenes para ítems incompletos en la fuente
process.py                    # Limpieza, validación y transformación al modelo final
tests/test_data_quality.py    # Suite de validación de datos (pytest)

items.json                    # Ítems del juego
recipes.json                  # Recetas de crafteo
ingredient_categories.json    # Grupos de ingredientes intercambiables (requerido para leer recipes.json)

duplicate_itemids.json        # Auditoría: IDs duplicados en la fuente
orphan_result_ids.json        # Auditoría: recetas sin ítem correspondiente en la fuente
orphan_image_urls.json        # Auditoría: imágenes verificadas para esos casos

docs/                          # Registro completo de la investigación, decisión por decisión
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

python -m pytest tests/ -v     # corre la suite de validación — 31 passed
```

## Modelo de datos

```
items.json    → { id, name, category, subcategory, imageUrl, rarity, damage?, damageType?, defense?, sellValue? }
recipes.json  → { id, resultItemId, resultQuantity, ingredients[], station, requiredCondition,
                   resultName?, resultImageUrl? }   ← estos dos últimos, solo en casos incompletos en la fuente
```

`ingredients[]` es una lista de `{ itemId, quantity }`, o `{ itemId: null, quantity, categoryHint }` cuando el ingrediente es una categoría intercambiable en vez de un ítem específico.

## Fuente y licencia de los datos

Extraído de la [Official Terraria Wiki](https://terraria.wiki.gg/) vía su API pública de MediaWiki (extensión Cargo). Los datos se distribuyen bajo la misma licencia CC BY-NC-SA 4.0 de la fuente — ver [ATTRIBUTION.md](./ATTRIBUTION.md) para el detalle completo. El código de este repositorio es de mi autoría.

Terraria es propiedad de Re-Logic. Este es un proyecto independiente, sin afiliación oficial.
