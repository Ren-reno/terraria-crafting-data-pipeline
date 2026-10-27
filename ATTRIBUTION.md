# Atribución y licencia de los datos

## Fuente

Los datos en `data/items.json` y `data/recipes.json` fueron extraídos de la
**[Official Terraria Wiki](https://terraria.wiki.gg/)** (terraria.wiki.gg) vía su
API pública de MediaWiki (`action=cargoquery`, extensión Cargo). La extracción
vigente es del 15 de octubre de 2026 (la extracción inicial fue el 07 de agosto
de 2026). Los crudos intermedios (`data/raw/`) no se versionan en este
repositorio.

## Licencia de los datos

**Los datos estructurados** (nombres, stats, recetas — todo lo que sale de la API Cargo hacia `data/items.json` y `data/recipes.json`) están cubiertos por la licencia general de contenido textual de terraria.wiki.gg:
**[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/)**,
según su página oficial de derechos de autor:
https://terraria.wiki.gg/wiki/Terraria_Wiki:Copyrights

Esto significa que **los archivos de datos derivados de la wiki**
(`data/items.json` y `data/recipes.json`) se distribuyen en este repositorio
bajo esa misma licencia CC BY-NC-SA 4.0:

- ✅ Podés usar, compartir y adaptar estos datos.
- ✅ Con atribución a la Official Terraria Wiki (ver arriba).
- ❌ **No** para uso comercial.
- 🔄 Cualquier trabajo derivado de estos datos debe compartirse bajo la
  misma licencia (ShareAlike).

**Las imágenes (`imageUrl`, `resultImageUrl`) son un caso aparte, y merecen más cuidado.** A diferencia del texto, wiki.gg **no aplica una única licencia a todos los archivos**: cada imagen subida a la wiki puede llevar una de 13 plantillas de licencia distintas (CC BY, CC BY-SA, CC BY-NC, CC BY-NC-SA, "fair use"/copyright, sin licencia asignada, etc. — ver `https://terraria.wiki.gg/wiki/Template:License`), asignada archivo por archivo por quien lo subió. Se verificó puntualmente que la categoría de "fair use" (`Category:Files_under_copyright_(fair_use)`, 43 archivos en total al momento de revisar) contiene logos, fotos de personas y fan-art — **no** íconos de ítems del juego — lo cual sugiere que los sprites de ítems (assets originales de Re-Logic, subidos en masa por editores para ilustrar cada artículo) probablemente no están categorizados ahí, pero **no se confirmó la plantilla exacta de un ícono de ítem individual** antes de este documento.

**Antes de publicar el proyecto en un dominio propio o destacarlo fuera de un repo de portafolio de uso personal**, conviene abrir la ficha de un archivo puntual (ej. buscar `File:Torch.png` en la wiki) y confirmar qué plantilla de licencia tiene realmente, en vez de asumir que todas las imágenes comparten la licencia general CC BY-NC-SA del texto.

**Nota:** existe un sitio distinto, `terrariawiki.org`, que es un fan site no oficial y no afiliado a wiki.gg — no confundir con `terraria.wiki.gg` (la fuente real usada en este proyecto). Sus términos son otros y no aplican acá.

**Nota importante:** el contenido y los materiales de Terraria (nombres de
ítems, mecánicas, arte, etc.) son propiedad intelectual de
**[Re-Logic](https://re-logic.com/)**. Este repositorio es un proyecto no
oficial, hecho por fans, sin afiliación ni respaldo de Re-Logic ni de
wiki.gg. La licencia de la wiki cubre la forma en que la wiki
presenta esa información — no transfiere derechos sobre el juego en sí.

## Licencia del código

El código de este repositorio (scripts de extracción, procesamiento y
verificación, y los tests) es de mi autoría y se distribuye bajo licencia
[MIT](./LICENSE) — independiente de la licencia de los datos
mencionada arriba, que aplica solo a los archivos JSON con contenido
extraído de la wiki.

## Cómo se obtuvieron los datos

Ver [`docs/03-avance-extraccion-cargo.md`](./docs/03-avance-extraccion-cargo.md)
para el proceso completo (la serie de documentos está incompleta: los números
02, 04, 05 y 07 no están en este repositorio): extracción vía `action=cargoquery` (API de
MediaWiki), paginada con `limit=500`/`offset`, corrida localmente (no desde
un entorno que respete `robots.txt` de forma automática, dado que
`terraria.wiki.gg/robots.txt` restringe el acceso automatizado estándar a
`/api.php`). El script se identifica con un User-Agent honesto y respeta
rate limiting (delay entre requests) — ver `src/extract.py`.
