# Primera actualización de versión real del juego — impacto en los tests

> Continúa la serie de docs numerados (02, 03, 05, 07). Registra el primer caso real de que los "known counts" de los tests de calidad de datos quedaron desactualizados por una causa externa legítima (una actualización del juego), no por un bug del pipeline — sirve como caso de referencia para la próxima vez que esto pase.

## Contexto

Al correr `python -m pytest tests/ -v` después de agregar `damageType`/`defense` (ver doc 07) y re-extraer datos, fallaron 2 tests que **no tenían relación** con ese cambio:

- `test_category_null_tiene_count_conocido_y_pocos_crafteables`: esperaba 7 ítems crafteables sin categoría, encontró 9.
- `test_ingredientes_sin_itemid_tienen_categoryhint`: encontró 2 ingredientes sin `itemId` ni `categoryHint` (`"Any Gold Bar"`, en la receta de "Format:C" y "Harpy Charm").

## Investigación

Se identificaron los 2 `itemId` nuevos en la lista de crafteables sin categoría: `1338` ("Explosive Bunny") y `6174` ("Trusty Digtoise"). "Trusty Digtoise" no correspondía a nada conocido — señal de contenido muy reciente.

**Confirmado con evidencia externa (búsqueda web, no solo la wiki de datos)**: Terraria lanzó la actualización **1.4.5 ("Bigger & Boulder")** el 27 de enero de 2026 — un crossover con Palworld que agregó "Pals" (compañeros invocables: Digtoise, Cattiva, Foxparks, Chillet). El juego siguió recibiendo parches hasta la versión **1.4.5.7/1.4.5.8**, publicados muy poco antes de esta sesión. La wiki oficial (`terraria.wiki.gg/wiki/Digtoise`) confirma explícitamente que "Trusty Digtoise" es una mejora **crafteable** del Digtoise base, agregada recientemente vía un ítem llamado "Little Kinship Peach".

Esto explica ambos fallos con el mismo patrón que ya se documentó varias veces en este proyecto (recetas huérfanas, `rarity` sin parsear, `itemid` duplicados): **contenido nuevo del juego, con receta ya cargada en Cargo, pero cuya ficha de ítem (categoría) y/o categorización de ingredientes todavía no está 100% migrada** en la wiki.

## Cambios aplicados

- **`process.py`**: se agregó `"Any Gold Bar": [19, 706]` (Gold Bar + Platinum Bar, mismo patrón que `Any Iron Bar` = [Iron Bar, Lead Bar]) a `manual_extras` en `load_ingredient_categories()`. IDs confirmados contra `items.json` real, no adivinados.
- **`tests/test_data_quality.py`**: `KNOWN_CRAFTEABLE_COUNT` en `test_category_null_tiene_count_conocido_y_pocos_crafteables` actualizado de 7 a 9, con comentario explicando la causa real (actualización de versión, con link conceptual a este doc). `KNOWN_NULL_CATEGORY_COUNT` (107) **no cambió** — el total de ítems sin categoría se mantuvo igual; lo que cambió es cuántos de esos 107 ahora tienen receta.

## Lección para el futuro

El resto de los "known counts" del proyecto (`rarity="quest"`=45, recetas huérfanas=67, `itemid` duplicados=11, nombres repetidos=7) **no se vieron afectados** por esta actualización — se mantuvieron exactos en la re-extracción. Esto confirma que el enfoque de "número conocido y vigilado" funciona como se esperaba: cuando el juego cambia de verdad, el test correspondiente avisa con precisión (no en bloque, no con falsos positivos en tests no relacionados), y la investigación puntual confirma rápido si es una actualización legítima o un bug real. Frente a un fallo de este tipo, el primer paso siempre debería ser preguntar "¿salió una versión nueva del juego?" antes de asumir un problema de datos o de código.
