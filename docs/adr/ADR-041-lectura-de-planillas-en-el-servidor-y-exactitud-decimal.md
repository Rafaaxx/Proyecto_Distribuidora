# ADR-041 — Las planillas se leen en el servidor (CSV y `.xlsx` sin dependencia de planillas), con decimales exactos y una dependencia nueva: `python-multipart`

| Campo | Valor |
| --- | --- |
| Estado | Vigente |
| Fecha | 2026-10-01 |
| Referenciado en | `openspec/changes/10-importacion-inicial/design.md` D2, D3, D11 y D12 y `specs/importacion/planillas`; `01-dominio.md` INV-03, INV-04, TR-01, TR-02; ADR-001 (stack), ADR-016 (motor de cálculo compartido) |

**Decisiones D2, D3, D11 y D12 (opción A en cada una) y la dependencia `python-multipart` aprobadas por el usuario el 2026-10-01. Texto del ADR aprobado por el usuario el 2026-10-01; estado *Vigente*.**

## Contexto

ADR-001 no prevé ninguna biblioteca para leer planillas. Las celdas numéricas de un `.xlsx` se guardan en binario de punto flotante, lo que choca con INV-03 (ningún importe, costo o porcentaje se representa con `float`). Un CSV guardado por Excel en español usa `;` como separador, coma decimal y, según la versión, Windows-1252. Recibir un archivo por HTTP exige leer `multipart/form-data`, algo que FastAPI delega en `python-multipart`.

## Decisión

1. **La lectura ocurre en el servidor.** `POST /api/v1/importaciones/{tipo}` recibe el archivo por multipart; la API lo convierte en filas de texto y ese JSON es el contenido del comando (ADR-040). El navegador no lee ni interpreta el archivo.
2. **Formatos.** CSV (UTF-8 con o sin BOM y, si no decodifica, Windows-1252; separador `,` o `;` detectado en el encabezado; comillas) y `.xlsx` (primera hoja). Todo otro formato, incluido `.xls`, se rechaza con `ARCHIVO_INVALIDO`.
3. **Lector `.xlsx` propio de la biblioteca estándar** (`zipfile` más `xml.etree`): cadenas compartidas, celdas en línea y texto literal de cada celda. No se agrega `openpyxl`.
4. **Exactitud (INV-03).** De una celda numérica se toma el **texto literal guardado en el XML** (`<v>1239.669421</v>`) y se pasa como cadena al conversor decimal; ninguna ruta del lector produce `float`. Una celda con resultado de fórmula con decimales espurios (`1239.6694214876034`) se conserva literal y la regla del destino la rechaza (por ejemplo `COSTO_INVALIDO` por más de seis decimales), sin redondear. Las fechas solo se convierten si la celda tiene formato de fecha; si no, se exige texto (`FECHA_INVALIDA`).
5. **Números escritos como texto (D12).** Coma decimal y sin separador de miles; un punto se rechaza con `NUMERO_INVALIDO` (`1.500` no se interpreta ni como 1,5 ni como 1500). Las cantidades son enteros (`CANTIDAD_INVALIDA`, INV-04). La conversión vive en `importacion/domain` como funciones puras con una propiedad Hypothesis (todo decimal con hasta seis decimales escrito con coma vuelve igual).
6. **Límites (D11).** Hasta 2.000 filas de datos y 5 MB; columna desconocida, faltante o repetida rechaza el archivo (`COLUMNAS_INVALIDAS`); orden de columnas libre; filas vacías ignoradas. El tamaño se verifica sin leer el archivo entero en memoria.
7. **Dependencia nueva: `python-multipart==0.0.32`** en `backend/requirements.txt`. Solo la usa FastAPI para el cuerpo multipart; no se importa desde el código de la aplicación. Se acepta como excepción puntual a ADR-001 por no tener alternativa en la biblioteca estándar para ese cuerpo.

## Consecuencias

- Un `clientes.xlsx` de 300 filas se sube tal cual, sin exportarlo a CSV.
- El usuario debe escribir los decimales con coma y sin miles; el mensaje de error de la fila lo indica. A cambio no hay interpretaciones silenciosas de mil veces.
- Mantener un lector `.xlsx` propio implica cubrir su alcance con pruebas (planillas generadas en la prueba): no se soportan macros, hojas múltiples ni formatos propietarios, y se rechazan con `ARCHIVO_INVALIDO`.
- La superficie de ataque del archivo se acota con el límite de 5 MB, un tope de tamaño descomprimido por parte del zip (50 MB), el máximo de columnas de Excel y la lectura de solo las partes necesarias.

## Alternativas consideradas

- **Leer en el navegador con una biblioteca JS de planillas:** descartada: dependencia nueva en el front y las celdas numéricas llegan como `number` de JS, que es punto flotante.
- **Solo CSV en la etapa 1:** descartada: obliga al usuario a exportar desde Excel y a revisar la codificación.
- **`openpyxl` en el servidor:** descartada: dependencia nueva de gran tamaño; entrega `float` para las celdas numéricas salvo que se lea el XML crudo, que es lo que ya hace el lector propio.
- **Leer el `float` y convertir con `Decimal(repr(x))`:** descartada: pasa por binario (contradice INV-03).
- **Aceptar coma o punto decimal, o el formato argentino completo con punto de miles:** descartadas: `1.500` se leería 1,5 o 1500 según el criterio y, en el segundo caso, `1.5` se leería 15.
