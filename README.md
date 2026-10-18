# Terraria Data Pipeline

Pipeline de extracción, limpieza y validación de datos que convierte el catálogo completo de ítems y recetas de crafteo de Terraria en dos archivos JSON estructurados, listos para consumir desde una aplicación.

**Resultado final:** 6.141 ítems y 3.942 recetas (extracción del 15 de octubre de 2026), validados por una suite de 36 tests automatizados de calidad de datos.

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
   tests/test_data_quality.py         → 36 tests validan el resultado
```

Dos scripts auxiliares resuelven casos especiales del dataset:
- `extract_categories.py` — mapea los grupos de ingredientes "intercambiables" del juego (p. ej. cualquier tipo de madera sirve para una receta) a sus IDs reales, scrapeando y parseando la página correspondiente de la wiki.
- `verify_orphan_images.py` — confirma con peticiones HTTP reales, uno por uno, que existen las imágenes de un conjunto de ítems que el pipeline detectó como incompletos en la fuente (ver más abajo).

## Problemas de datos reales, encontrados y resueltos

Esta es la parte que más vale la pena leer. Cada punto es un caso concreto donde el dato no era lo que la documentación de la fuente sugería, y cómo se resolvió con evidencia en vez de suposiciones.

**Formato inconsistente en campos "de lista".** El campo `type` de cada ítem se documentaba como una lista, pero llegaba como un string plano separado por `^` (`"furniture^light source^crafting material"`). Afectaba a más de un tercio de los ítems del dataset. Se detectó comparando el resultado real contra una muestra esperada, no asumiendo que la documentación era correcta.

**IDs duplicados en la fuente.** 12 `itemId` de la tabla `Items` están repetidos entre dos ítems distintos — rompe la clave primaria del modelo de datos. Se investigó el patrón (todos caen en el mismo rango de IDs, correspondiente a contenido reciente del juego) antes de decidir cómo resolverlo: se conserva la primera aparición y se reporta el resto para auditoría, en vez de perder el dato silenciosamente.

**Referencias rotas entre tablas.** En la extracción original, 67 recetas señalaban un ítem resultado que no existe en la tabla de ítems — la receta está completa, pero el ítem no tenía ficha propia. En vez de asumir un bug y descartarlas, se investigó qué eran realmente: 22 sets temáticos de muebles decorativos agregados en una actualización reciente del juego, confirmado cruzando contra la documentación pública de la wiki. La decisión de producto fue no ocultarlos: se completa su nombre y su imagen desde fuentes alternativas (recuperando el nombre directo de la tabla de recetas, y confirmando con peticiones HTTP reales que la imagen correspondiente existe en el servidor) en vez de perder recetas válidas del dataset. Con el tiempo la wiki fue completando esas fichas: en la extracción del 15 de octubre de 2026 quedan 46 recetas (45 ítems) en este caso, porque los 22 ítems "Candle" ya no aparecen entre los huérfanos. De esos 45 ítems, 43 tienen imagen confirmada; "Trusty Chillet" y "Trusty Chillet Ignis" quedaron sin imagen y están pendientes de investigar (en extracciones anteriores sí tenían ficha propia).

**Categorías de ingredientes "intercambiables".** Varios cientos de ingredientes en las recetas no corresponden a un ítem único sino a una categoría del propio juego (p. ej. "cualquier lingote de hierro sirve"). En vez de forzarlos a un ítem arbitrario o descartar la información, se modeló como una relación de uno a muchos, resuelta contra el listado oficial de categorías de la wiki.

**Un campo puede depender de otro campo de forma no obvia.** Al agregar `damageType` (clase de arma: Melee/Ranged/Magic/Summon) se encontró que no está limitado a ítems de categoría "arma" — herramientas como picos y hachas también lo tienen, porque hacen daño real a enemigos en el juego. Asumir la relación obvia ("solo las armas tienen tipo de daño") habría sido incorrecto; se confirmó con datos reales antes de escribir el test correspondiente.

**Datos corruptos en filas descontinuadas.** Un pequeño número de filas trae identificadores en formatos no válidos (ej. dos IDs separados por `/`, sufijos inesperados). Se blindó el parseo para descartar esas filas puntuales sin interrumpir la ejecución completa, en lugar de dejar que un caso extremo tumbe todo el proceso.

**Nombres que no son identificadores únicos.** Varios nombres de ítem aparecen repetidos en 2 o más filas distintas (ej. "Strange Plant" con 4 variantes según bioma). El nombre es un dato descriptivo, no una clave — solo `id` lo es, y el modelo de datos y los tests lo dejan explícito para evitar que una futura integración use el nombre como identificador por error.

**Distinguir un bug de un cambio legítimo en la fuente.** El juego y la wiki cambian durante la vida del proyecto. Una re-extracción posterior a una actualización de contenido hizo fallar tests que antes pasaban — no por un error del pipeline, sino porque el juego agregó ítems y recetas nuevas genuinas. Esos primeros fallos se investigaron con evidencia externa (confirmando la actualización real y el contenido involucrado) antes de actualizar los valores esperados. Al repetirse en una extracción posterior (la wiki completó fichas que faltaban), se cambió el diseño: los conteos exactos pasaron a ser límites relativos (p. ej. "no más de 5 % de recetas huérfanas") que solo fallan ante algo realmente anómalo, y el valor histórico se conserva como referencia que emite un warning de pytest cuando cambia. Así el pipeline no se rompe con cada parche del juego, pero cualquier desvío sigue siendo visible.

El registro de esta investigación — con evidencia, números exactos y el razonamiento detrás de cada decisión — está en [`docs/`](./docs/), empezando por [`03-avance-extraccion-cargo.md`](./docs/03-avance-extraccion-cargo.md), y en [`actualizacion-version-1-4-5-7.md`](./actualizacion-version-1-4-5-7.md) (el primer cambio de versión real del juego y su efecto en los tests). Los documentos son una bitácora: reflejan el estado del proyecto en cada momento (p. ej. los ids de receta de ejemplo usan el esquema anterior al actual) y la serie está incompleta — los números 02, 04, 05 y 07, que se citan en comentarios del código, no están en este repositorio.

## Validación de datos, no solo extracción

`tests/test_data_quality.py` corre 36 tests con `pytest` sobre el resultado final: tipos de dato correctos, unicidad de identificadores, ausencia de HTML sin procesar, integridad referencial entre archivos, y límites de tolerancia (relativos, no números exactos) para los casos especiales documentados arriba. También verifica que todo `categoryHint` de `recipes.json` exista en `ingredient_categories.json` y que los ids de receta sean únicos y no dependan del orden en que la wiki devuelve las filas. No son tests de código — son tests sobre el contrato del propio dataset, para que cualquier cambio futuro en la fuente (una nueva versión del juego, un cambio en la wiki) se detecte automáticamente en lugar de corromper el resultado en silencio.

## Estructura del repositorio

```
extract.py                    # Extracción desde la API Cargo (paginada, con rate limiting)
extract_categories.py         # Mapeo de categorías de ingredientes intercambiables
verify_orphan_images.py       # Verificación HTTP de imágenes para ítems incompletos en la fuente
process.py                    # Limpieza, validación y transformación al modelo final
tests/test_data_quality.py    # Suite de validación de datos (pytest)
requirements.txt              # Dependencias: requests, beautifulsoup4, pytest

items.json                    # Ítems del juego
recipes.json                  # Recetas de crafteo
ingredient_categories.json    # Grupos de ingredientes intercambiables (requerido para leer recipes.json)

duplicate_itemids.json        # Auditoría: IDs duplicados en la fuente
orphan_result_ids.json        # Auditoría: recetas sin ítem correspondiente en la fuente
orphan_image_urls.json        # Auditoría: imágenes verificadas para esos casos
orphan_images_not_found.json  # Auditoría: huérfanos cuya imagen NO se pudo confirmar (revisar a mano)

docs/                          # Bitácora de la investigación (documento 03: extracción y decisiones de modelado)
actualizacion-version-1-4-5-7.md  # Bitácora: primer cambio de versión real del juego y su efecto en los tests
ATTRIBUTION.md                 # Fuente, licencia y atribución de los datos
LICENSE                        # Licencia del código (MIT)
```

## Cómo correrlo

Los datos ya están generados (`items.json`, `recipes.json`) — no hace falta correr nada para usarlos. Para reproducir el pipeline desde cero:

```bash
pip install -r requirements.txt   # requests, beautifulsoup4 y pytest

python extract.py              # genera raw_items.json y raw_recipes.json (no versionados, ~2.5 MB)
python extract_categories.py   # genera ingredient_categories.json
python process.py              # genera items.json y recipes.json (1ª pasada)
python verify_orphan_images.py # genera orphan_image_urls.json (lee recipes.json)
python process.py              # 2ª pasada: incorpora resultImageUrl a las recetas huérfanas

python -m pytest tests/ -v     # corre la suite de validación — 36 passed
```

`process.py` va dos veces porque depende de `verify_orphan_images.py` y viceversa: la verificación de imágenes necesita `recipes.json` para saber qué ítems son huérfanos, y `process.py` necesita `orphan_image_urls.json` para completar sus recetas. En la primera pasada se usa el `orphan_image_urls.json` que ya esté en el repo; la segunda actualiza las recetas con el resultado de la verificación. `process.py` no usa la red, así que puede repetirse las veces que haga falta.

Si los tests emiten *warnings* de pytest (p. ej. "recetas huérfanas: 46 (referencia histórica: 67)"), no es un error: el dato cambió dentro de lo tolerado. Conviene revisar si es contenido nuevo de la wiki y, si lo es, actualizar el valor de referencia en `tests/test_data_quality.py`.

## Modelo de datos

```
items.json    → { id, name, category, subcategory, imageUrl, rarity, damage?, damageType?, defense?, sellValue? }
recipes.json  → { id, resultItemId, resultQuantity, ingredients[], station, requiredCondition,
                   resultName?, resultImageUrl? }   ← estos dos últimos, solo en casos incompletos en la fuente
```

`ingredients[]` es una lista de `{ itemId, quantity }`, o `{ itemId: null, quantity, categoryHint }` cuando el ingrediente es una categoría intercambiable en vez de un ítem específico.

El `id` de cada receta tiene el formato `{resultItemId}-{n}`, donde `n` es la posición de la receta entre las recetas de ese mismo ítem, ordenadas por contenido. No depende del orden en que la wiki devuelve las filas ni de las recetas de otros ítems, así que una app puede usarlo como clave estable (favoritos, progreso) entre extracciones. Solo puede cambiar si cambian las recetas del propio ítem (p. ej. la wiki agrega o quita una variante): en ese caso los ids de las recetas de ese ítem pueden reordenarse. En una comparación real entre dos extracciones, 3.917 de 3.942 recetas conservaron su id (las 25 restantes cambiaron de contenido); con el esquema anterior, un contador global, solo conservaron su id 125.

## Fuente y licencia de los datos

Extraído de la [Official Terraria Wiki](https://terraria.wiki.gg/) vía su API pública de MediaWiki (extensión Cargo). Los datos se distribuyen bajo la misma licencia CC BY-NC-SA 4.0 de la fuente — ver [ATTRIBUTION.md](./ATTRIBUTION.md) para el detalle completo. El código de este repositorio es de mi autoría.

Terraria es propiedad de Re-Logic. Este es un proyecto independiente, sin afiliación oficial.
