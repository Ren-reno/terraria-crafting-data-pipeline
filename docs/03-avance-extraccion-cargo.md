# Avance: Extracción de datos vía Cargo — Terraria Crafteos

> Este documento continúa a `02-contexto-obtencion-de-datos.md`. Resume lo validado en vivo contra `terraria.wiki.gg` (endpoint Cargo Export) y deja el plan de extracción listo para ejecutar. Está pensado para que otro chat/LLM lo retome sin necesitar el historial completo.
>
> **Si estás por construir la app y no el pipeline de datos en sí, andá directo a la sección "CIERRE — Estado final de los datos" al final de este documento.** El resto es el registro cronológico de la investigación (útil si algo necesita revisarse), pero esa sección final tiene todo lo necesario para empezar a consumir `items.json`/`recipes.json` sin leer lo anterior.

## Estado general

Ya NO hace falta seguir "explorando" la estructura de las tablas — está confirmada al 100% para `Items` y `Recipes`, con ejemplos reales de datos, incluyendo el patrón de `imageUrl`. La extracción completa ya se ejecutó (`items.json`: 6071 filas, `recipes.json`: 3905 filas) y tiene una suite de tests de calidad de datos corriendo en verde (ver secciones "Actualización: extracción completa ejecutada" y "Tests de calidad de datos" más abajo). El mapeo de ingredientes "Any X" a itemIds reales (`ingredient_categories.json` + `categoryHint`) está **completo y conectado en `process.py`**. Las 67 recetas huérfanas también están **resueltas** (nombre e imagen, ver sección "Cerrado: decisión sobre las 67 recetas huérfanas" y "Cerrado: imágenes de las recetas huérfanas"). La traducción al español sigue en el backlog de v2 y no bloquea el lanzamiento. **No quedan decisiones de producto pendientes para dar la v1 por cerrada** — suite de tests: 26 passed.

## Restricción importante de acceso

El `robots.txt` de `terraria.wiki.gg` bloquea el acceso automatizado estándar (confirmado: un `web_fetch`/script simple a `Special:CargoExport` devuelve `ROBOTS_DISALLOWED`). Sin embargo, **la URL funciona perfecto pegada directamente en un navegador normal** (confirmado con capturas reales, ver ejemplos abajo). Esto significa que la extracción real probablemente deba hacerse:
- Manualmente por lotes desde un navegador, o
- Con un script que use un user-agent/headers de navegador real y respete rate limits, o
- Pidiéndole al usuario que pegue los resultados de URLs específicas (como se hizo en esta sesión de validación)

No asumir que un simple `fetch`/`curl` va a funcionar sin más.

## Endpoint confirmado

```
https://terraria.wiki.gg/wiki/Special:CargoExport?tables=<tabla>&fields=<campo1,campo2,...>&format=json&limit=<N>&offset=<N>&where=<condición>
```

Funciona con `format=json`. Parámetros útiles confirmados:
- `fields=` — lista de columnas separadas por coma (si se omite, no se probó qué devuelve por defecto)
- `limit=` — probado hasta 5 filas; **falta confirmar el límite máximo real por request** (pendiente probar `limit=500`)
- `offset=` — para paginar, no probado aún en vivo pero es sintaxis estándar de Cargo
- `where=` — filtros tipo SQL, ej. `where=resultid=4231` o `where=itemid>0` (ambos confirmados funcionando)

## Tabla `Items` — estructura confirmada (43 columnas totales)

Fuente: `Special:CargoTables/Items` (documentación oficial de la wiki).

```
itemid          Integer   (indexado)
name            String
internalname    String
image           Wikitext
imagefile       String
imageplaced     Wikitext
imageequipped   Wikitext
autoswing       Boolean
stack           Wikitext
consumable      Boolean
hardmode        Boolean
type            List of String, delimiter: ^
listcat         List of String, delimiter: ^
tag             List of String, delimiter: ^
damage          Wikitext
damagetype      String
defense         Wikitext
velocity        Wikitext
knockback       Wikitext
research        Wikitext
rare            Wikitext   (pero en la práctica devuelve INT limpio, ver abajo)
buy             Wikitext
sell            Wikitext   (HTML escapado, ver parseo abajo)
axe             Wikitext
pick            Wikitext
hammer          Wikitext
fishing         Wikitext
bait            Integer
bonus           Wikitext
toolspeed       Wikitext
usetime         Wikitext
unobtainable    Boolean
critical        Wikitext
tooltip         Wikitext
placeable       Boolean
placedwidth     Integer
placedheight    Integer
mana            Wikitext
hheal           Wikitext
mheal           Wikitext
bodyslot        String
buffs           List of String, delimiter: ^
debuffs         List of String, delimiter: ^
```

### Comportamiento real confirmado (con datos de ejemplo)

- **`itemid`**: `null` en páginas de "sets" (armaduras compuestas, vanity sets — no son un ítem individual real). Funciona perfecto (entero limpio) en ítems reales/individuales. **Filtrar con `where=itemid>0` o similar para descartar sets.**
- **`rare`**: a pesar de estar tipado "Wikitext", devuelve un entero limpio (`0`, `4`, `9`, etc.) o `null`. No necesita parseo especial.
- **`damage`**: entero limpio (`5`, `12`) cuando aplica, `null` cuando el ítem no hace daño (bloques, materiales, etc. — esto es *esperado*, no un error).
- **`type`**: lista de strings en minúscula (ej. `["tool"]`, `["armor","set"]`, `["block","crafting material"]`). Buena base directa para `category`/`subcategory`.
- **`sell`**: viene con HTML **doble-escapado** (entidades tipo `&lt;span...&gt;`, `&amp;#32;`) envolviendo el markup real generado por el template `{{coin}}`. **No intentar parsear el texto visual.** El valor numérico limpio está en el atributo `data-sort-value="N"` dentro de ese HTML — extraerlo con una regex simple: `data-sort-value="(\d+)"`. Esa `N` es el valor en la unidad mínima del juego (copper coins, donde 100 copper = 1 silver, 10000 copper = 1 gold). `sell: null` cuando el ítem no tiene valor de venta (correcto/esperado). **Confirmado que la estructura interna del HTML varía entre ítems** (ej. Torch usa `<span class="t">Copper</span>` en vez del `<i>` que usan otros) — el parseo debe depender únicamente del atributo `data-sort-value`, nunca de la estructura HTML circundante, porque no es uniforme.
- **`type`**: confirmado que puede traer 3 o más valores simultáneos, no solo 1-2 (ej. Torch: `["furniture", "light source", "crafting material"]`).

### Ejemplo real (ítems individuales, `where=itemid>0`)

```json
[
    {
        "itemid": 1,
        "name": "Iron Pickaxe",
        "type": ["tool"],
        "rare": 0,
        "damage": 5,
        "sell": "...data-sort-value=\"400\"..."
    },
    {
        "itemid": 2,
        "name": "Dirt Block",
        "type": ["block", "crafting material"],
        "rare": 0,
        "damage": null,
        "sell": null
    }
]
```

### Pendiente de resolver para `Items`

- **Entidades HTML en `name`** (y probablemente otros campos de texto): confirmado en `Recipes` que el exportador JSON no decodifica entidades HTML (ej. `&#039;` = comilla simple). Aplicar decodificador de entidades HTML a **todos los campos de texto libre**, no solo a `sell`.
- **`imageUrl`**: `imagefile` da el nombre de archivo (ej. `"Iron Pickaxe.png"`), no una URL completa. **Patrón CONFIRMADO en vivo** (probado con `Special:FilePath/Iron_Pickaxe.png`, que redirige a la URL real):

  ```
  https://terraria.wiki.gg/images/<Nombre_Archivo_Con_Guiones_Bajos>.png?<hash-corto>
  ```

  Ejemplo real confirmado: `https://terraria.wiki.gg/images/Iron_Pickaxe.png?c4d254`

  A diferencia del patrón estándar de Wikimedia (que usa una subcarpeta de hash de 2 niveles, ej. `/a/a3/`), esta wiki **no tiene subcarpeta de hash** — la imagen está directo en `/images/`. Sí tiene un **query string corto al final** (`?c4d254` en el ejemplo), que parece ser un hash/versión de cache-busting.

  **Confirmado: el query string es OPCIONAL.** `https://terraria.wiki.gg/images/Iron_Pickaxe.png` (sin el `?c4d254`) carga la imagen correctamente. Esto significa que **`imageUrl` se puede armar con un simple string replace desde `imagefile`, sin necesitar ningún fetch adicional por ítem**:

  ```
  imageUrl = "https://terraria.wiki.gg/images/" + imagefile.replace(/ /g, "_")
  ```

  Con esto, el patrón de `imageUrl` queda cerrado del todo — no requiere pasar por `Special:FilePath` ni resolver ningún hash en tiempo de extracción.

## Tabla `Recipes` — estructura confirmada (11 columnas totales)

Fuente: `Special:CargoTables/Recipes` (documentación oficial de la wiki). 4,221 filas totales.

```
result          String    (indexado, max 300 chars)
resultid        String    (indexado — aunque el valor es numérico)
resultimage     String    (indexado, max 300 chars)
resulttext      String    (indexado, max 300 chars — vacío en casi todos los ejemplos vistos)
amount          Integer   (indexado)
version         String    (indexado — plataforma: "desktop console mobile", "old-gen 3ds", etc. Vacío/null = todas las plataformas)
station         String    (indexado)
ingredients     List of String, delimiter: ^   (indexado, max 300 chars — nombres únicos "bonitos" para mostrar, sin cantidad; separador visual real es " • ")
ings            String    (indexado, max 600 chars — nombre+cantidad, formato ¦Nombre¦Cantidad^¦Nombre¦Cantidad..., orden alfabético)
args            Text      (NO indexado — mismo tipo de dato que `ings` pero en el orden original de registro y SIN los `¦` decorativos extra alrededor de cada nombre; formato: `Nombre¦Cantidad^Nombre¦Cantidad`)
legacy          Boolean   (indexado — ver sección clave abajo)
```

### CLAVE: campo `legacy` — filtro obligatorio

El namespace `Legacy:Recipes/.../register` (nótese el prefijo `Legacy:` en `_pageName`) contiene recetas históricas/descontinuadas: versiones viejas de ítems (marcadas con sufijo `#i:old` dentro de `args`), recetas exclusivas de plataformas descontinuadas (`old-gen`, `3ds`), etc.

**Regla de extracción: descartar toda fila donde `legacy` sea `true`/`1`. Quedarse solo con `legacy: 0`/`false`/`null` para tener las recetas vigentes en la versión actual del juego.**

Confirmado con ejemplo real: las variantes viejas de "Bloody Spine", "Slime Crown", "Night's Edge" (con ingredientes tipo "Light's Bane" pre-fusión, o "Fiery Greatsword" que ya no existe con ese nombre) tienen `legacy: Yes`. Las versiones actuales de esas mismas recetas (no mostradas aún en este documento, pero se infieren por exclusión) deberían tener `legacy: 0`.

### `args` es el campo a usar para parsear ingredientes (no `ings`)

`args` no tiene el ruido de `¦` extra que sí tiene `ings`, y preserva el orden original de registro (potencialmente más natural para mostrar en UI). Formato confirmado en JSON real (el separador `¦` aparece como `\u00a6` al escapar unicode):

```
"Stone Block\u00a610^Nebula Fragment\u00a61"
```

Parseo: split por `^` → por cada elemento, split por `¦` (o `\u00a6`) → `[nombre, cantidad]`.

**Cuidado con sufijos tipo `#i:old`** dentro de nombres de ingrediente en filas legacy (ej. `"Stinger#i:old"`) — de nuevo, esto solo debería aparecer en filas ya descartadas por el filtro `legacy`, pero vale la pena limpiar el sufijo como defensa adicional por si aparece en algún caso raro no legacy.

### Ningún campo de `Recipes` trae `itemId` de los ingredientes — solo nombres

Ni `ingredients`, ni `ings`, ni `args` traen un ID numérico de ingrediente. Todos dan el **nombre** del ítem. Esto obliga a un paso de cruce obligatorio: **construir primero un diccionario `{ name → itemid }` desde la tabla `Items` completa, y usarlo para resolver el `itemId` de cada ingrediente parseado desde `Recipes`.**

`resultid`, en cambio, **sí** viene numérico y confiable directo desde `Recipes` — no hace falta cruzarlo, usarlo tal cual.

### DECISIÓN DE PRODUCTO YA TOMADA: múltiples recetas por mismo `resultid`

Confirmado con el caso real de "Nebula Brick" (`resultid: 4231`), que tiene 3 filas simultáneamente vigentes (`legacy: 0` en las 3):

```json
[
    { "result": "Nebula Brick", "resultid": 4231, "amount": 1, "station": "By Hand", "args": "Nebula Platform\u00a62", "legacy": 0 },
    { "result": "Nebula Brick", "resultid": 4231, "amount": 1, "station": "Work Bench", "args": "Nebula Brick Wall\u00a64", "legacy": 0 },
    { "result": "Nebula Brick", "resultid": 4231, "amount": 10, "station": "Ancient Manipulator", "args": "Stone Block\u00a610^Nebula Fragment\u00a61", "legacy": 0 }
]
```

Esto no es un error ni un caso raro aislado — Terraria permite genuinamente craftear muchos bloques tanto "desde cero" (con materiales base) como "por reciclado" (deconstruyendo su forma de pared/plataforma ya craftada). Un mismo `resultItemId` puede tener N recetas vigentes en simultáneo.

**Decisión tomada: NO elegir una sola receta "principal" ni descartar las triviales. Guardar TODAS las recetas vigentes como entradas independientes en `recipes.json`, cada una con su propio `id` único, todas compartiendo el mismo `resultItemId`.** El modelo de datos original (ver doc `02-...md`) ya soporta esto sin cambios — un array plano de recetas donde varias pueden compartir `resultItemId`. La app consumidora debe usar `.filter()` (no `.find()`) al buscar recetas de un ítem, esperando 0, 1 o N resultados.

## Modelo de datos objetivo — ACTUALIZADO respecto al doc original

```
items.json    → { id, category, subcategory?, imageUrl, rarity (number), damage (number, opcional), sellValue (number, opcional) }
recipes.json  → { id, resultItemId, resultQuantity, ingredients: [{ itemId, quantity }], station: string[] | null, requiredCondition: string | null }
i18n/es.json  → { "id_del_item": "Nombre en español" }   [v2 — no bloquea la v1, ver sección "Alcance de la v1"]
```

**Cambios respecto al doc `02-...md`:**
- `station` pasó de `string | null` a `string[] | null`, porque se confirmó que puede venir compuesto (ver hallazgo de "Heavy Assembler and Ecto Mist"). Decisión tomada: guardar como array, split por `" and "`.
- Se agregó `requiredCondition: string | null`, para separar condiciones ambientales (ej. "Ecto Mist") de muebles/objetos reales dentro de `station`. Ver sección "station compuesto: distinguir mueble real de condición ambiental" para la heurística de clasificación acordada.

Confirmado que ambas tablas de Cargo dan todo lo necesario para llenar este modelo, con los pasos de limpieza/cruce descritos arriba.

## Alcance de la v1 — DECISIÓN TOMADA: traducciones al español quedan para una v2 posterior

Se decidió **no bloquear el lanzamiento de la v1 con la traducción al español**. La v1 sale solo con nombres en inglés (usando `Items.name` directo, o un `i18n/en.json` equivalente como fallback), y la traducción se agrega después sin requerir cambios estructurales — porque el modelo de datos ya está diseñado para esto: `name` vive fuera de `items.json`, en el diccionario `i18n/*.json` separado. Sumar `i18n/es.json` en una v2 es un archivo nuevo, no una migración.

**Implicación práctica: por ahora no hace falta validar `es.terraria.wiki.gg`.** Queda pendiente para cuando se aborde la v2. El resto del plan (extracción de `Items` y `Recipes`, post-procesamiento, armado de JSON finales) no depende de esto y puede avanzar sin bloqueos.

## Licencia de datos — confirmado

El footer de `terraria.wiki.gg` (visto en `Terraria_Wiki:Cargo_tables`) confirma: contenido bajo **Creative Commons Attribution-NonCommercial-ShareAlike 4.0** (CC BY-NC-SA 4.0). Implicaciones para el proyecto:
- **Uso no comercial únicamente**
- **Atribución requerida** (mencionar la wiki como fuente)
- **ShareAlike**: si se republican/derivan los datos, probablemente deban compartirse bajo la misma licencia — revisar términos exactos antes de publicar el proyecto

## Validación de volumen (`limit=500`) — confirmado

Se probó `Special:CargoExport?tables=Recipes&fields=result,resultid,amount,version,station,args&format=json&limit=500` (sin filtro `legacy`) y devolvió correctamente ~490 filas sin cortarse. **`limit=500` es un tamaño de página seguro y funcional.** Con esto, la extracción completa de `Recipes` (4,221 filas) necesitaría ~9 requests paginados con `offset`, y `Items` (6,286 filas) ~13 requests. (Aún no se probó `offset` en vivo, pero es sintaxis estándar de Cargo y no debería fallar.)

## Hallazgos adicionales confirmados con la muestra grande (sin filtrar `legacy`)

Esta muestra (sin `where=legacy=0` ni `fields` incluyendo `legacy`) expuso varios patrones nuevos importantes:

### Patrón dominante: recetas circulares bloque ↔ pared ↔ plataforma ↔ cerca

Lo que parecía un caso raro con "Nebula Brick" (ver sección de decisión de producto) es en realidad **el patrón más común de todos** en materiales de construcción. Decenas de ejemplos en la muestra: Ash Wood, Aquarium Block, Bamboo, Boreal Wood, Blue Brick, etc. — todos tienen múltiples recetas vigentes simultáneas que permiten craftear tanto desde materiales base como revirtiendo desde su forma de pared/plataforma/cerca ya construida. **Esto refuerza (no cambia) la decisión de producto ya tomada: guardar todas las recetas alternativas, sin elegir una "principal".** Intentar detectar y descartar las triviales sería arbitrario y afectaría a una fracción grande del dataset, no a casos excepcionales.

### El sufijo `#i:old` puede aparecer en el campo `result`, no solo en ingredientes dentro de `args`

Ejemplo real: `"result": "Black Dye#i:old"` con `"resultid": 1050` (mismo ID que la versión vigente "Black Dye"), `"version": "old-gen"`. Esto confirma que **el filtro `legacy` es obligatorio, no una limpieza opcional** — sin filtrarlo, aparecen nombres de resultado literalmente sucios con el sufijo, no solo ingredientes. Reforzar el paso: excluir toda fila con `legacy: true/1`, y como defensa adicional, limpiar cualquier sufijo `#i:...` residual que se cuele en nombres (de `result` o de ingredientes en `args`) antes de usarlos para cruzar contra `Items` o mostrar en la UI.

### Campo `station` puede venir compuesto (dos requisitos simultáneos) — DECISIÓN TOMADA

Confirmado en varios ejemplos: `"station": "Heavy Assembler and Ecto Mist"`, `"station": "Work Bench and Ecto Mist"`, `"station": "Tinkerer's Workshop and Ecto Mist"`. No es una sola estación — es una combinación de dos condiciones requeridas a la vez (estación + bioma/entorno especial, en el caso de "Ecto Mist" que es un efecto de Halloween).

**Decisión tomada: guardar como array de estaciones/requisitos.** Esto SÍ cambia el modelo de datos original respecto al doc `02-...md`, que definía `station: string | null`. Modelo actualizado:

```
station: string[] | null
```

Parseo: split el string original por `" and "` (con espacios a los lados, para evitar falsos positivos si algún nombre de estación contuviera la palabra "and" — no se vio ningún caso así hasta ahora, pero queda como riesgo menor a vigilar). Ejemplo: `"Heavy Assembler and Ecto Mist"` → `["Heavy Assembler", "Ecto Mist"]`. Estaciones simples (la mayoría) quedan como array de un solo elemento, ej. `"Work Bench"` → `["Work Bench"]`.

### `station` compuesto: distinguir mueble real de condición ambiental (ej. Ecto Mist) — DECISIÓN TOMADA

`"Ecto Mist"` no es un mueble craftable/colocable — es un efecto de clima especial de Halloween que debe estar activo en el mundo para habilitar ciertas recetas (típicamente variantes "fantasma"/translúcidas de bloques de gema). La app necesita distinguir esto de un mueble real para no intentar renderizarlo como un ítem craftable (sin imagen, sin itemId, etc.).

**Decisión tomada: separar en dos campos en el modelo de datos.**

```
station: string[] | null            // muebles/objetos reales requeridos
requiredCondition: string | null    // condición ambiental, ej. "Ecto Mist"
```

**Cómo clasificar cada elemento del array parseado de `station` (heurística híbrida acordada):**

1. Si el nombre del elemento coincide con un `name` en la tabla `Items` ya extraída → es un mueble normal, va a `station`.
2. Si NO coincide con `Items`, pero está en una lista corta de excepciones conocidas y curadas a mano (objetos/estaciones especiales del mundo que no son ítems poseíbles, ej. `Demon Altar`, `Crimson Altar`, `Shimmer`, `By Hand`, y cualquier otra que aparezca al revisar los valores únicos reales de `station` en la extracción completa) → también va a `station` (es un requisito real, solo que no tiene imagen de ítem).
3. Si NO coincide con `Items` NI está en esa lista de excepciones conocidas → se clasifica como `requiredCondition` (caso confirmado hasta ahora: `Ecto Mist`; revisar si aparecen otras condiciones ambientales similares al hacer la extracción completa, ej. Blood Moon, Solar Eclipse, Party, etc.).

Esta lista de excepciones (paso 2) debe armarse revisando los valores únicos reales de `station` una vez extraído todo `Recipes` (`SELECT DISTINCT station`), no se puede inferir solo del cruce automático contra `Items`.

### Patrón "or" (alternativas de bioma Corrupción/Cremisí, etc.) — CONFIRMADO, no necesita parseo especial

La wiki muestra visualmente algunos requisitos como "Demon Altar **or** Crimson Altar" (capturas de pantalla revisadas en el chat). Se sospechaba que podía ser un valor compuesto dentro de `station`, similar al "and" — pero **se confirmó con datos reales que NO es así**.

Consulta de prueba (`where=station='Demon Altar' OR station='Crimson Altar'`) mostró el caso real de **"Deer Thing"** (`resultid: 5120`), que expresa el mismo patrón "or" pero en el ingrediente, no en la estación:

```json
{ "result": "Deer Thing", "resultid": 5120, "station": "Demon Altar", "args": "Flinx Fur¦3^Crimtane Ore¦5^Lens¦1", "legacy": 0 }
{ "result": "Deer Thing", "resultid": 5120, "station": "Demon Altar", "args": "Flinx Fur¦3^Demonite Ore¦5^Lens¦1", "legacy": 0 }
```

Mismo `resultid`, misma estación, pero **dos filas separadas**: una con `Crimtane Ore` (Cremisí) y otra con `Demonite Ore` (Corrupción). Mismo patrón confirmado en "Slime Crown" (`Gold Crown` vs `Platinum Crown`) y en las dos ramas de "Night's Edge" (`Blade of Grass` vs `Light's Bane`).

**Conclusión: el "or" (en estación o en ingredientes) se resuelve automáticamente con la decisión de producto ya tomada de "guardar todas las recetas alternativas como filas independientes por `resultId`".** No requiere parseo especial — cada alternativa ya llega como fila separada de Cargo. El caso puntual de "Demon Altar or Crimson Altar" de la captura no se encontró literal en esta consulta (el ítem real puede tener otro `result`), pero el patrón general queda confirmado y no necesita más validación.

### `resulttext` sigue sin verse con contenido en ningún ejemplo

En todas las muestras vistas hasta ahora (chicas y esta grande de ~490 filas), `resulttext` viene vacío/ausente. Puede ser un campo que casi nunca tiene valor en la práctica — no descartarlo del modelo todavía, pero no depender de que traiga algo.

### El campo `legacy` sigue siendo indispensable en el `fields=` de cualquier extracción real

Esta muestra grande NO incluía `legacy` en el `fields=` solicitado, lo cual dificultó distinguir filas legacy de vigentes a simple vista (solo se detectaron por pistas indirectas: sufijo `#i:old`, `version: "old-gen"`, etc.). **Recordatorio para la extracción real: siempre incluir `legacy` explícitamente en `fields=`, y filtrarlo en post-proceso (o directo con `where=legacy=0` si se confirma que ese filtro funciona en el exportador — no probado aún en vivo).**

## Validación de paginación (`offset`) — confirmado

Se probó `Special:CargoExport?tables=Recipes&fields=result,resultid,amount,station,args,legacy&format=json&limit=500&offset=500` y la primera fila devuelta ("Boreal Wood Greaves") continúa exactamente donde terminó la tanda anterior sin `offset` (que llegaba hasta "Boreal Wood Fence") — sin cortes, sin saltos, sin duplicados. **`limit=500` + `offset` es una estrategia de paginación confirmada y segura para la extracción completa.** El orden es alfabético por `result` de forma consistente entre páginas.

## Más excepciones de `station` detectadas (para la lista curada de objetos/líquidos especiales)

Además de `Demon Altar`, `Crimson Altar`, `Shimmer`, `By Hand` (ya anotados), esta tanda reveló más valores de `station` que no son muebles craftables y deben sumarse a la lista curada a mano (ver sección "station compuesto: distinguir mueble real de condición ambiental"):

- **`Honey`** y **`Water`** — líquidos del mundo (mismo concepto que `Shimmer`). Ejemplos: "Bottled Honey" requiere estar parado en `Honey`, "Bottled Water" y "Coralstone Block" requieren `Water`.
- **`Placed Bottle`** y **`Placed Bottle only`** — aparecen como dos valores de texto *distintos* para lo que es conceptualmente el mismo requisito (una botella ya colocada en el mundo, usada para pociones). **Normalizar ambos al mismo valor en el post-proceso** para no duplicar entradas en la lista de estaciones únicas — probablemente unificar a `"Placed Bottle"`.
- **`Table and Chair`** — visto en una fila `legacy: 1` (Copper Watch, versión vieja). Es un combo de dos muebles a la vez, mismo patrón que "X and Ecto Mist" pero con dos muebles reales en vez de mueble+condición. Como esta fila específica es legacy, no afecta el dataset final, pero vale la pena vigilar si aparece en alguna fila vigente al hacer la extracción completa — de ser así, ambos elementos (`Table`, `Chair`) irían al array `station`, ninguno es una condición ambiental.

Esta lista probablemente crezca al ver el dataset completo — el paso de post-procesamiento ya contempla revisar `SELECT DISTINCT station` para armarla con confianza.

## Qué falta hacer (próximos pasos, en orden sugerido)

1. ~~Confirmar límite máximo de filas por request~~ — ✅ **Confirmado: `limit=500` funciona bien, y `offset` pagina correctamente sin cortes/duplicados (verificado con `offset=500`).**
2. **Extraer `Items` completo** (paginado con `limit=500`/`offset`), con los campos: `itemid, name, type, rare, damage, sell, imagefile` como mínimo (agregar más si se decide enriquecer el modelo).
3. **Extraer `Recipes` completo** (paginado con `limit=500`/`offset`), con los campos: `result, resultid, amount, station, args, legacy` como mínimo — **`legacy` es obligatorio en el `fields=`, confirmado que sin él es difícil distinguir filas vigentes de descontinuadas**. Filtrar `legacy != true` en el post-procesamiento (o probar si `where=legacy=0` funciona directo en la query, no confirmado aún).
4. **Post-procesamiento**:
   - Decodificar entidades HTML en todos los campos de texto (`name`, `result`, etc.)
   - Parsear `sell` con regex `data-sort-value="(\d+)"` → `sellValue`
   - Parsear `args` (split `^` luego `¦`) → lista de `{ name, quantity }` por receta
   - Construir diccionario `{ name → itemid }` desde `Items` ya extraído
   - Resolver `itemId` de cada ingrediente parseado usando ese diccionario
   - Parsear `station` (split por `" and "`) → array de strings
   - Revisar los valores únicos reales de `station` en todo el dataset extraído (`SELECT DISTINCT`), armar la lista corta de excepciones conocidas (objetos/estaciones especiales que no son ítems: `Demon Altar`, `Crimson Altar`, `Shimmer`, `By Hand`, `Honey`, `Water`, `Placed Bottle`, etc.)
   - Clasificar cada elemento de `station` como mueble real (queda en `station`) o condición ambiental (se mueve a `requiredCondition`) usando la heurística híbrida acordada (cruce contra `Items` + lista de excepciones)
   - Armar `imageUrl` a partir de `imagefile`: `"https://terraria.wiki.gg/images/" + imagefile.replace(/ /g, "_")` — patrón confirmado, query string de cache-busting es opcional, no requiere fetch adicional.
5. **Armar los 2 archivos JSON de la v1** (`items.json`, `recipes.json`) siguiendo el modelo de datos exacto. Nombres en inglés directo desde `Items.name` (sin `i18n/es.json` todavía, ver "Alcance de la v1").
6. **Verificar términos de licencia exactos** (CC BY-NC-SA 4.0) antes de publicar el proyecto — agregar atribución donde corresponda.

## Backlog para v2 (no bloquea la v1)

- **Extraer traducciones en español** desde `es.terraria.wiki.gg` (mismo sistema Cargo, cruzar por `itemid` — no probado aún en ninguna sesión). Arma el archivo `i18n/es.json` sin requerir cambios en `items.json`/`recipes.json`.

## Nota sobre acceso automatizado

Dado que `robots.txt` bloquea fetches automatizados estándar, si el siguiente chat/LLM tiene herramientas de scraping, debe:
- Verificar primero si su entorno puede acceder igual (algunos headers/user-agents de navegador sí funcionan)
- Si no, plantear al usuario un flujo manual por lotes: el usuario pega URLs en su navegador y comparte los resultados JSON, como se hizo en esta sesión
- Respetar rate limits en cualquier caso — no automatizar peticiones agresivas contra la wiki

## Actualización: extracción completa ejecutada

Se ejecutó `extract.py` (script Python corrido localmente por el usuario, no desde el entorno del chat — ver nota anterior sobre `robots.txt`) contra `action=cargoquery` con `limit=500` paginado. Resultado real:

- **`Items`**: 6082 filas crudas extraídas.
- **`Recipes`**: 4221 filas crudas extraídas (3905 vigentes tras filtrar `legacy=1`).

El post-procesamiento (`process.py`) tuvo que corregirse respecto a lo asumido en este documento, porque los datos reales revelaron comportamientos no previstos:

- **`type` no viene como lista ya parseada** — viene como string plano con `^` literal (ej. `"furniture^light source^crafting material"`), igual que `station`. Afectaba al 37% de los items (2230 de 6082) antes de corregirse.
- **`rare` no siempre es un entero limpio** — 12 items (todos en el rango de itemid 5036–5376, contenido reciente) traen el wikitext crudo sin resolver, ej. `<span class="rarity">...Rarity color N.png...`. Se agregó fallback de regex para extraer el número de ahí.
- **11 `itemid` duplicados** — mismo rango 5036–5376, dos ítems distintos comparten el mismo id (ej. `5036` = "Otherworldly Music Box (Lunar Boss)" y "Ocram Trophy" a la vez). Se conserva la primera aparición y se descarta la segunda; el detalle queda en `duplicate_itemids.json` para revisión manual. Probable causa: contenido nuevo cuya migración a Cargo en la wiki está incompleta.
- **5 `resultid` vacíos** en Recipes — todos correspondían a filas `legacy=1`, así que no afectan el dataset final, pero el parseo tuvo que blindarse para no cortar el script si esto cambia en una futura re-extracción.
- **2 valores de `station` no anticipados**: `Lava` (líquido del mundo, mismo patrón que `Water`/`Honey` → va a `station`) y `Snow Biome` (condición de bioma, mismo patrón que `Ecto Mist` → va a `requiredCondition`). Se suman a las listas curadas.

`items.json` (6071 filas) y `recipes.json` (3905 filas) ya están generados con el `process.py` corregido.

## ✅ Decisiones de producto — todas resueltas

1. ~~Los 335 ingredientes tipo "Any X"...~~ — ✅ **Resuelto por completo.** Ver sección "Cerrado: categoryHint conectado en process.py". Los 335 ingredientes sin `itemId` directo ahora tienen `categoryHint` con el nombre del grupo, resolviendo tanto los casos scrapeados de la wiki (31 grupos) como 4 excepciones manuales confirmadas (`(bait)`, `Recorded Music Boxes`).
2. ~~Las 67 recetas huérfanas...~~ — ✅ **Resuelto por completo.** Ver sección "Cerrado: decisión sobre las 67 recetas huérfanas". Se decidió mostrarlas parcial en vez de filtrarlas (son 22 sets de muebles reales, receta completa, solo falta el infobox en la wiki). Se agregó el campo `resultName` a esas recetas específicas.
3. **Hallazgo documentado, sin acción requerida**: 7 filas de `Recipes` (todas `legacy=1`, así que no afectan el dataset final) traen `resultid` en formato roto, no numérico puro — ej. `"5004 / 1870"` (Dragon Breastplate, dos ids alternativos separados por `/`), `"5035sp"` (Sparkly Wings, sufijo `sp`). `process.py` ya se blindó para descartar esa fila puntual en vez de crashear si esto aparece en una fila vigente en una futura re-extracción.

## Tests de calidad de datos

Se armó `tests/test_data_quality.py` (pytest, 20 tests) que valida el contrato de datos de `items.json`/`recipes.json` contra el dataset real: tipos correctos, unicidad de `id`, ausencia de HTML sin parsear en `rarity`, formato de `imageUrl`, integridad referencial entre `recipes.json` e `items.json`, y un techo de tolerancia para ingredientes tipo "Any X" sin `itemId` resuelto (para detectar si en el futuro aparece un bug de matching real, no solo más placeholders del juego). Correr con `pytest tests/ -v` desde la carpeta del proyecto, después de tener `items.json`/`recipes.json` generados.

**Confirmado corriendo en la máquina real del usuario (Windows)**: 19 passed, 1 xfailed — resultado idéntico al validado en el entorno de desarrollo. Nota para futuras sesiones: en Windows, si `pip install` reporta éxito pero luego `python -m pytest` dice "No module named pytest", es casi siempre por tener más de un Python instalado (ej. `C:\Python314\python.exe` a nivel de sistema vs. uno en `AppData\Roaming\Python`, cada uno con su propio `site-packages`). Se soluciona forzando que la instalación vaya al mismo intérprete que después ejecuta el comando: `python -m pip install pytest` (usando `-m` en vez de invocar `pip`/`pytest` como comandos sueltos, que pueden resolver a instalaciones distintas).

## Resuelto: mapeo de ingredientes "Any X" a itemIds reales (`extract_categories.py`)

Retomando el pendiente #1 de la sección anterior. Se investigó cómo la wiki modela estos grupos y se encontró la página oficial **`https://terraria.wiki.gg/wiki/Alternative_crafting_ingredients`**, que lista cada grupo "Any X" con sus miembros exactos e Internal Item ID — justo lo necesario para construir el mapeo sin adivinar.

**Decisión de modelo de datos**: en vez de intentar resolver cada ingrediente "Any X" a un único `itemId` (imposible, son categorías con múltiples alternativas válidas — y el juego además permite mezclar cantidades entre miembros del mismo grupo, confirmado en la propia página de la wiki), se agrega un archivo nuevo **`ingredient_categories.json`** como diccionario aparte (mismo patrón que `i18n/es.json`: una tabla de referencia separada, no repetida en cada receta). Las recetas mantienen `itemId: null` pero ganan un campo `categoryHint` con el nombre del grupo (ej. `"Any Iron Bar"`), que la app resuelve consultando `ingredient_categories.json`.

```
ingredient_categories.json → { "Any Iron Bar": [22, 704], "Any Wood": [9, 619, 620, ...], ... }
```

### Intento 1: fallido, 0 grupos encontrados

Primer intento de `extract_categories.py` asumía que el `id="Any_X"` vivía directo en el tag `<h3>` del header de cada sección. El usuario corrió el script en su máquina (`pip install beautifulsoup4 requests` + `python extract_categories.py`) y dio **0 grupos encontrados** — el fetch y el parseo corrieron sin error, pero el selector no matcheaba nada.

### Diagnóstico con HTML real

Se agregó un paso de debug a `extract_categories.py` para volcar el HTML crudo descargado a `debug_page.html`, y el usuario lo compartió de vuelta. Inspeccionándolo se confirmó el bug exacto: el `id="Any_Iron_Bar"` vive en un `<span class="mw-headline">` **dentro** del `<h3>`, no en el `<h3>` mismo:

```html
<h3><span class="mw-headline" id="Any_Iron_Bar">Any Iron Bar</span></h3>
<div class="terraria">
<div class="itemlist"><ul>
  <li><span class="i -w">
    <a href="/wiki/Iron_Bar" title="Iron Bar">...</a>
    <span><span><a title="Iron Bar">Iron Bar</a></span>
    <span class="id">Internal <a href="/wiki/Item_IDs">Item ID</a>: 22</span></span>
  </span></li>
  ...
</ul></div>
```

Detalle clave adicional: el Internal Item ID de cada miembro viene como texto plano (`"Internal Item ID: N"`) directo en el HTML de cada `<li>`, dentro de `<div class="itemlist">`. Esto es **mejor fuente que cruzar por nombre** contra `raw_items.json` (evita fallos por variantes de capitalización/acentos) — se usa como fuente primaria, con fallback a cruce por nombre solo si por algún motivo faltara.

### Parser corregido y validado

Se corrigió el selector (`soup.find_all("span", class_="mw-headline", id=re.compile(r"^Any_"))`, ancla a `<div class="itemlist">` en vez de cualquier `<ul>` suelto) y se validó contra el `debug_page.html` real compartido por el usuario:

- **30 de 30 grupos** parseados correctamente, con itemIds reales extraídos del propio HTML.
- **0 miembros sin resolver** (`unmatched_category_members.json` vacío).
- Verificación cruzada: de los 35 nombres "Any X" distintos vistos en `recipes.json` (ver sección "Alcance de la v1"), 34 coinciden con un grupo scrapeado. El único faltante, **`Any Torch`**, no tiene sección propia en la wiki (tiene una sola ocurrencia en todo el dataset de recetas) — se resuelve con una excepción manual chica en el propio script (`MANUAL_CATEGORY_OVERRIDES`), documentada inline para ampliar si aparecen más casos así en el futuro.

**Estado**: `extract_categories.py` ya está corregido y listo para que el usuario lo corra de nuevo en su máquina. Pendiente confirmar que genera `ingredient_categories.json` con 31 grupos (30 scrapeados + `Any Torch` manual) en su entorno real — la lógica ya está validada contra el HTML real, así que se espera que corra limpio.

### Próximo paso pendiente

Una vez confirmado `ingredient_categories.json` en la máquina del usuario, falta actualizar `process.py` para que:
1. Cargue `ingredient_categories.json`.
2. Cuando un ingrediente de receta no matchee ningún `itemId` (los ~335 casos "Any X" y variantes como `(bait)`), en vez de dejarlo con `itemId: null` sin más, agregue `categoryHint: "<nombre del grupo>"` si el nombre coincide con una clave de `ingredient_categories.json`.
3. Ajustar `tests/test_data_quality.py` para reflejar el nuevo campo `categoryHint` en el contrato de datos.

Esto cerraría el pendiente #1 de la lista de decisiones (el #2, las 67 recetas huérfanas, y el hallazgo #3 de `resultid` malformado siguen abiertos igual que antes, ver sección anterior).

## Cerrado: `categoryHint` conectado en `process.py`

El usuario confirmó `ingredient_categories.json` generado en su máquina (31 grupos, coincide exacto con lo validado). Se conectó en `process.py`:

- `load_ingredient_categories()` carga el archivo y le suma **4 excepciones manuales** confirmadas al correr el pipeline completo por primera vez: quedaron 4 ingredientes sin resolver (`Blue/Green/Pink Jellyfish (bait)` y `Recorded Music Boxes`), ninguno cubierto por `extract_categories.py` porque ninguno tiene sección propia en la página wiki de grupos (mismo patrón que `Any Torch`, ver sección anterior).
  - Los 3 `(bait)` se resuelven a un **único** `itemId` real (`Blue Jellyfish` = 2436, etc. — son el mismo ítem, la wiki solo agrega el sufijo para aclarar contexto de uso como carnada).
  - `Recorded Music Boxes` es distinto: hay **75 ítems** `Music Box (X)` en `Items` (uno por canción grabable), una categoría abierta/dinámica del juego, no un set finito. Se deja con `alternatives: []` en vez de fingir una lista cerrada — la app deberá manejar este caso mostrando el nombre sin resolver a un ítem concreto.
- Cada ingrediente sin `itemId` gana `categoryHint: "<nombre del grupo>"` cuando el nombre coincide con una clave del diccionario (ya sea de `ingredient_categories.json` o de las excepciones manuales).

**Resultado final confirmado**: de 335 ingredientes sin `itemId` directo, **335 quedaron resueltos con `categoryHint`** (0 sin ninguna resolución). Ejemplo real del dataset:

```json
{
  "itemId": null,
  "quantity": 10,
  "categoryHint": "Any Iron Bar"
}
```

Se agregó también `tests/test_ingredientes_sin_itemid_tienen_categoryhint` (nuevo test, valida que ningún ingrediente quede sin `itemId` Y sin `categoryHint` a la vez) y se ajustó el test de umbral existente para que sea coherente con el nuevo contrato. **Suite completa: 20 passed, 1 xfailed** (el xfail sigue siendo el conocido de las 67 recetas huérfanas, pendiente #2, sin cambios).

Con esto, el pendiente #1 de la lista de decisiones queda **cerrado**. Pendientes restantes: #2 (67 recetas huérfanas, decisión de producto sobre filtrar o mostrar parcial) y el hallazgo #3 (documentado, sin acción requerida).

## Cerrado: decisión sobre las 67 recetas huérfanas — mostrar parcial con `resultName`

Se investigó primero **qué son específicamente** los 65 `resultItemId` huérfanos antes de decidir, cruzando `orphan_result_ids.json` contra `raw_recipes.json` para sacar los nombres reales. Resultado: son **22 sets temáticos completos de muebles decorativos**, patrón `[Tema] Candelabra / Candle / Door` — Aetherium, Aquarium, Boulder, Cloud, Crimtane, Demonite, Duskware, Easter, Fallen Star, Feywood, Flinx Fur, Forbidden, Gothic, Hallowed, Harpy, Jellyfish, Librarian, Office, Pine, Snow, Spike, Stone — más un caso suelto (`Magic Shimmer Dropper`).

Se confirmó contra la wiki oficial (`https://terraria.wiki.gg/wiki/Candelabras` y `/Candles`) que estos exact 22 sets se agregaron en la versión **Desktop 1.4.5.0**, y que la wiki sí los documenta en texto completo (páginas "Candelabras"/"Candles" con lore y mecánica). Esto descarta la hipótesis de "receta sin terminar de definir en el juego": la receta está completa y confirmada en Cargo, lo que falta es específicamente el infobox individual de cada ítem migrado a la tabla `Items` — un hueco de mantenimiento de la wiki (contenido relativamente nuevo, migración manual pendiente), no un hueco del juego. Es coherente con que estos 65 ids caen en el mismo rango (5492–6120) donde también aparecían los 12 `rarity` sin parsear y los 11 `itemid` duplicados.

**Decisión de producto**: no filtrar. Mostrarlos parcialmente — la receta es válida y completa, solo falta la ficha visual del resultado. Es razonable esperar que una futura re-extracción los traiga completos si la wiki termina de migrar esos infoboxes.

**Implementación en `process.py`**: se agrega un campo `resultName` (string) **solo** en las recetas cuyo `resultItemId` no resuelve contra `items.json`, tomado directo de `Recipes.result` (el nombre en inglés, ya presente en la tabla Cargo). Las ~3900 recetas normales no llevan este campo — se resuelve el nombre vía `items.json` + `i18n` como siempre, para no duplicar información innecesariamente.

```json
{
  "id": "5552-91",
  "resultItemId": 5552,
  "resultQuantity": 1,
  "ingredients": [...],
  "station": ["Work Bench"],
  "requiredCondition": null,
  "resultName": "Aetherium Candelabra"
}
```

Se reemplazó el test `xfail` anterior por tres tests que validan el contrato completo:
- `test_result_item_id_huerfanas_tiene_count_conocido` — vigila que el conteo de huérfanas (67) no cambie sin avisar (si baja, es buena noticia: la wiki completó infoboxes).
- `test_result_item_id_huerfanas_tienen_result_name` — garantiza que toda receta huérfana tiene `resultName` no vacío (la app siempre tiene algo que mostrar).
- `test_result_name_solo_aparece_en_huerfanas` — vigila que el campo no se filtre a recetas normales por error.

**Suite completa ahora: 23 passed, 0 xfailed** — ya no queda ningún test "esperando fallar"; el pendiente de producto se convirtió en garantía de datos real.

Con esto, **las dos decisiones de producto pendientes quedan cerradas**. Solo queda el hallazgo #3 documentado (formato roto de `resultid` en filas legacy, sin acción requerida) como nota histórica.

## Cerrado: imágenes de las 67 recetas huérfanas (`resultImageUrl`)

`resultName` resolvió el nombre, pero no el ícono: `imageUrl` es un campo de la tabla `Items` de Cargo, que es justo la fila que falta para estos 65 ítems. Antes de descartar mostrar imagen para ellos, se investigó si el mismo patrón de convención usado en `build_image_url()` para el resto del dataset (`"https://terraria.wiki.gg/images/" + nombre.replace(" ", "_") + ".png"`) también aplica acá — ya que la wiki no depende de Cargo para servir los archivos de imagen en sí, solo para tener el campo `imagefile` indexado.

**Verificación, no suposición**: se confirmó primero un caso puntual (`Aetherium Candelabra.png`) contra la categoría oficial de imágenes de la wiki (`Category:Item_images`), que sí lista el archivo con su tamaño real en bytes. Dado que automatizar la verificación de los 65 restantes no era viable de forma confiable desde el entorno del asistente (paginación de la categoría, 5619 archivos totales, sin acceso directo a `Special:FilePath`), se armó `verify_orphan_images.py` para que el usuario lo corra localmente: hace un `HEAD` request real (liviano, no descarga la imagen) contra cada una de las 65 URLs candidatas, con rate limiting.

**Resultado real, confirmado por el usuario en su máquina**: **65 de 65 imágenes existen**, la convención se cumplió sin ninguna excepción.

**Implementación en `process.py`**: se agrega `resultImageUrl` (opcional, solo si `orphan_image_urls.json` — generado por `verify_orphan_images.py` — tiene la entrada confirmada) junto a `resultName`, mismo patrón de "solo en huérfanas, nunca en recetas normales":

```json
{
  "resultItemId": 5552,
  "resultName": "Aetherium Candelabra",
  "resultImageUrl": "https://terraria.wiki.gg/images/Aetherium_Candelabra.png",
  ...
}
```

Se agregó `test_result_image_url_solo_aparece_en_huerfanas_y_es_https` (valida que no se filtre a recetas normales y que la URL tenga el formato esperado). **Suite final: 24 passed, 0 xfailed.**

Con esto, las recetas huérfanas quedan con la misma calidad de datos visual que el resto del dataset (nombre + ícono), pese a no tener fila en `Items`.

---

# CIERRE — Estado final de los datos, para quien continúe el proyecto

> Esta sección es el punto de entrada si estás retomando el proyecto para construir la app (React u otra). Resume todo lo de arriba en un formato consumible sin tener que leer la investigación completa. Los datos están **completos, validados y estables** — no hay extracción pendiente ni decisiones de producto abiertas sobre el pipeline en sí.

## Qué hay y cómo usarlo

Dos archivos finales, en la raíz del proyecto de datos:

- **`items.json`** — 6.071 ítems del juego.
- **`recipes.json`** — 3.905 recetas de crafteo.

Ambos ya pasaron por 26 tests automatizados de calidad de datos (`tests/test_data_quality.py`, corridos con `pytest`, **26 passed** en la última verificación). Si volvés a correr el pipeline (`extract.py` → `process.py`) por cualquier motivo, correr `python -m pytest tests/ -v` después es la forma de confirmar que el resultado sigue siendo válido — los tests documentan el contrato de datos esperado con más precisión que cualquier resumen en prosa.

## Forma real de `items.json`

```json
{
  "id": 1,
  "category": "tool",
  "subcategory": null,
  "imageUrl": "https://terraria.wiki.gg/images/Iron_Pickaxe.png",
  "rarity": 0,
  "damage": 5,
  "sellValue": 400
}
```

Notas sobre los campos, a tener en cuenta al construir la UI:
- `subcategory`, `damage`, `sellValue` son opcionales — no todos los ítems los tienen (ej. bloques no tienen `damage`).
- `rarity` normalmente es un número (0 en adelante, también puede ser negativo), pero **45 ítems tienen el string `"quest"`** en vez de número — es un tier de rareza real del juego (peces del Angler, Strange Plants), no un dato roto. Ninguno de esos 45 participa en ninguna receta, así que no afecta pantallas de crafteo, pero si se construye un listado general de ítems, hay que manejar ese caso (no asumir que `rarity` siempre es sorteable como número).
- `category` es `null` en 107 ítems (falta ese dato en la wiki). De esos, solo 7 son crafteables — el resto no aparece en ninguna receta. Si se necesita mostrar categoría en un listado general, definir un valor de respaldo (ej. `"Otros"`) para estos casos.

## Forma real de `recipes.json`

La mayoría de las recetas (la gran mayoría de las 3.905) tienen esta forma simple:

```json
{
  "id": "2702-0",
  "resultItemId": 2702,
  "resultQuantity": 1,
  "ingredients": [
    { "itemId": 3, "quantity": 50 }
  ],
  "station": ["Heavy Assembler"],
  "requiredCondition": null
}
```

- `resultItemId` referencia un `id` de `items.json` — casi siempre existe (ver excepción de recetas "huérfanas" más abajo).
- `station` es un array de nombres de estación (puede tener más de uno, ej. `["Table", "Chair"]`) o `null` si no requiere ninguna.
- `requiredCondition` es una condición ambiental (ej. `"Ecto Mist"`, `"Snow Biome"`) distinta de una estación física, o `null`.

**Dos casos especiales** que la UI necesita contemplar, ambos ya resueltos en los datos, no requieren lógica adicional de fetch:

### 1. Ingredientes de categoría intercambiable (`categoryHint`)

335 ingredientes, en vez de un ítem único, representan "cualquiera de estos sirve" (ej. cualquier lingote de hierro):

```json
{ "itemId": null, "quantity": 10, "categoryHint": "Any Iron Bar" }
```

Cuando `itemId` es `null` y aparece `categoryHint`, buscar esa clave en **`ingredient_categories.json`** (31 grupos) para obtener la lista real de `itemId` alternativos:

```json
"Any Iron Bar": [22, 704]
```

Ese archivo debe copiarse junto con `items.json`/`recipes.json` a donde sea que la app lo consuma — no está embebido en `recipes.json` para no repetir la lista en cada una de las 172 recetas que usan "Any Iron Bar", por ejemplo.

### 2. Recetas "huérfanas" (`resultName` / `resultImageUrl`)

67 recetas (65 ítems únicos) tienen una receta completa pero su `resultItemId` **no** existe en `items.json` — son sets de muebles decorativos de una actualización reciente del juego cuya ficha individual la wiki todavía no completó. Para que la UI no se rompa buscando un ítem que no está, estas recetas traen el nombre y la imagen ya resueltos directamente:

```json
{
  "id": "5552-91",
  "resultItemId": 5552,
  "resultQuantity": 1,
  "ingredients": [...],
  "station": ["Work Bench"],
  "requiredCondition": null,
  "resultName": "Aetherium Candelabra",
  "resultImageUrl": "https://terraria.wiki.gg/images/Aetherium_Candelabra.png"
}
```

**Regla práctica para la UI**: al mostrar el resultado de una receta, primero intentar resolver `resultItemId` contra `items.json`; si no se encuentra, usar `resultName`/`resultImageUrl` de la propia receta como respaldo. `rarity` y `sellValue` no están disponibles para estos 65 casos (no hay ficha de ítem), así que esos campos deben tratarse como ausentes en la UI para ese caso puntual, no como un error.

## Archivos que viajan junto con `items.json`/`recipes.json`

Además de los dos archivos principales, la app necesita:
- **`ingredient_categories.json`** — obligatorio, para resolver `categoryHint` (ver arriba).
- **`ATTRIBUTION.md`** — no lo consume la app, pero debe acompañar el proyecto/repo por requisito de licencia de los datos (CC BY-NC-SA 4.0 sobre el texto; licencia de imágenes con matices, ver el propio archivo).

Los demás archivos generados durante el pipeline (`raw_items.json`, `raw_recipes.json`, `duplicate_itemids.json`, `orphan_result_ids.json`, `orphan_image_urls.json`, `unknown_stations.json` si existiera) son artefactos intermedios o de auditoría — no hacen falta para correr la app, solo para reproducir o volver a auditar el pipeline de datos.

## Qué NO está resuelto (y está bien que no lo esté)

- **Traducción al español** (`i18n/es.json` del modelo de datos original) — explícitamente en el backlog de v2, no bloquea nada de lo anterior.
- **La plantilla de licencia exacta de un ícono de ítem individual** en la wiki — no se pudo confirmar con certeza (ver `ATTRIBUTION.md`). No bloquea seguir desarrollando en un proyecto de portafolio no comercial, pero sí conviene revisarlo antes de publicar el proyecto en un dominio propio o destacarlo públicamente.

Fuera de esos dos puntos (explícitamente fuera de alcance, no pendientes olvidados), **los datos están terminados**. No hace falta volver a correr `extract.py` ni re-investigar ninguno de los casos documentados arriba salvo que cambie la versión del juego o la wiki.
