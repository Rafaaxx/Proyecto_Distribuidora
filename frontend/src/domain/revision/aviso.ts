/**
 * El aviso de lo pendiente de `/admin` (change 25, tarea 15.1; D5, D12; CRE-09): el contador del menú y las líneas
 * de la tarjeta «Para revisar». Lógica pura, sin React. Los excesos de crédito detectados al sincronizar van
 * aparte (CRE-09); las cuarentenas se cuentan con las rechazadas porque se resuelven en la misma pestaña.
 */

export const CODIGO_DE_EXCESO_AL_SINCRONIZAR = 'EXCESO_CREDITO_DETECTADO_SYNC'

export interface ResumenDePendientesParaAviso {
  observaciones_por_codigo: { [codigo: string]: number }
  observaciones_pendientes: number
  rechazos_pendientes: number
  cuarentenas_pendientes: number
  total_pendiente: number
}

export interface LineaDeAviso {
  texto: string
  cantidad: number
}

/** El total del menú; `null` (sin contador) si no hay nada pendiente o todavía no se sabe. */
export function contadorDelMenu(resumen: ResumenDePendientesParaAviso | undefined): number | null {
  if (resumen === undefined || resumen.total_pendiente <= 0) return null
  return resumen.total_pendiente
}

function linea(cantidad: number, singular: string, plural: string): LineaDeAviso | null {
  if (cantidad <= 0) return null
  return { cantidad, texto: `${String(cantidad)} ${cantidad === 1 ? singular : plural}` }
}

/** Las tres líneas de la tarjeta; `null` en la que no tiene nada. */
export function lineasDeAviso(resumen: ResumenDePendientesParaAviso): {
  avisos: LineaDeAviso | null
  rechazadas: LineaDeAviso | null
  excesos: LineaDeAviso | null
} {
  return {
    avisos: linea(resumen.observaciones_pendientes, 'aviso pendiente', 'avisos pendientes'),
    rechazadas: linea(
      resumen.rechazos_pendientes + resumen.cuarentenas_pendientes,
      'operación rechazada sin resolver',
      'operaciones rechazadas sin resolver',
    ),
    excesos: linea(
      resumen.observaciones_por_codigo[CODIGO_DE_EXCESO_AL_SINCRONIZAR] ?? 0,
      'exceso de crédito detectado al sincronizar',
      'excesos de crédito detectados al sincronizar',
    ),
  }
}
