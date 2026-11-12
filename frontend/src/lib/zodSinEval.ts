/**
 * Zod sin `eval` (change 28, Lote 4; D9; docs/02 §18). La política de contenido de Caddy no admite
 * `unsafe-eval`: Zod 4 prueba si puede compilar validadores con `new Function("")` y, aunque el
 * navegador lo rechace y Zod siga con su camino normal, lo informa como violación de la política.
 * Con `jitless` Zod no hace esa prueba. Se importa primero en `main.tsx`, antes que cualquier
 * esquema. Cuesta una validación algo más lenta, imperceptible con los formularios de la aplicación.
 */
import { z } from 'zod'

z.config({ jitless: true })
