import { z } from 'zod'

import { sinCerosFinales } from '../precios/decimales'
import { construirVigencia, instante } from '../precios/publicacionSchema'
import type { ReglaPresentable } from './presentacion'
import { porcentajeDesdeFraccion, type AlcanceDeFormulario, type DatosReglaDescuentoEntrada } from './reglaSchema'

/**
 * Auxiliares del formulario de regla de descuento (change 16, tarea 15.2): lo que los componentes
 * necesitan para no llevar lógica de negocio. Valores iniciales desde una regla guardada, alta y
 * baja de alcances (DSC-02), fecha local de un instante y el esquema de "Poner fin" (D15, D16).
 * Nada se convierte a `number` (INV-03).
 */

function conDosDigitos(valor: number): string {
  return String(valor).padStart(2, '0')
}

/** Instante ISO -> `aaaa-mm-ddThh:mm` en hora local (`<input type="datetime-local">`); vacío si no hay. */
export function valorLocalDeFecha(iso: string | null): string {
  if (iso === null) return ''
  const fecha = new Date(iso)
  return `${fecha.getFullYear()}-${conDosDigitos(fecha.getMonth() + 1)}-${conDosDigitos(fecha.getDate())}T${conDosDigitos(fecha.getHours())}:${conDosDigitos(fecha.getMinutes())}`
}

/** Lo que la persona escribiría para obtener la regla guardada (`0.050000` -> `5`). */
export function formularioDesdeRegla(regla: ReglaPresentable & { nombre: string }): DatosReglaDescuentoEntrada {
  const valor =
    regla.accion_tipo === 'PORCENTAJE'
      ? porcentajeDesdeFraccion(regla.accion_porcentaje ?? '0')
      : sinCerosFinales(regla.accion_importe ?? '0')
  return {
    nombre: regla.nombre,
    tipo: regla.tipo,
    medida: regla.medida,
    operador: regla.operador,
    umbral: sinCerosFinales(regla.umbral),
    accion_tipo: regla.accion_tipo,
    accion_valor: valor,
    prioridad: String(regla.prioridad),
    acumulable: regla.acumulable,
    alcances: regla.alcances.map((a) => ({ tipo: a.tipo, entidad_id: a.entidad_id })),
    vigencia_desde: valorLocalDeFecha(regla.vigencia_desde),
    vigencia_hasta: valorLocalDeFecha(regla.vigencia_hasta),
  }
}

function mismoAlcance(a: AlcanceDeFormulario, b: AlcanceDeFormulario): boolean {
  return a.tipo === b.tipo && a.entidad_id === b.entidad_id
}

/** Agrega un alcance al final; no repite uno que ya está ni agrega uno sin entidad elegida. */
export function agregarAlcance(
  alcances: readonly AlcanceDeFormulario[],
  nuevo: AlcanceDeFormulario,
): AlcanceDeFormulario[] {
  if (nuevo.entidad_id === '' || alcances.some((a) => mismoAlcance(a, nuevo))) return [...alcances]
  return [...alcances, nuevo]
}

export function quitarAlcance(
  alcances: readonly AlcanceDeFormulario[],
  quitado: AlcanceDeFormulario,
): AlcanceDeFormulario[] {
  return alcances.filter((a) => !mismoAlcance(a, quitado))
}

export function etiquetaDeValorDeAccion(accionTipo: string): string {
  return accionTipo === 'PORCENTAJE' ? 'Porcentaje de descuento (%)' : 'Importe fijo ($)'
}

/**
 * "Poner fin": fija la vigencia hasta de una regla ya activada (D15, D16). Pide una fecha válida,
 * posterior a la vigencia desde cuando la regla ya la tiene; que no sea pasada lo valida el
 * servidor con su reloj (`VIGENCIA_INVALIDA`).
 */
export function crearEsquemaFinDeVigencia(vigenciaDesde: string | null) {
  return z
    .object({ vigencia_hasta: z.string() })
    .superRefine((datos, contexto) => {
      const hasta = instante(datos.vigencia_hasta)
      if (hasta === null) {
        contexto.addIssue({ code: 'custom', path: ['vigencia_hasta'], message: 'Ingresá una fecha y hora válidas.' })
        return
      }
      if (vigenciaDesde !== null && hasta.getTime() <= new Date(vigenciaDesde).getTime()) {
        contexto.addIssue({
          code: 'custom',
          path: ['vigencia_hasta'],
          message: 'La vigencia hasta debe ser posterior a la vigencia desde.',
        })
      }
    })
    .transform((datos) => ({ vigencia_hasta: construirVigencia({ vigencia_desde: '', vigencia_hasta: datos.vigencia_hasta }).vigencia_hasta }))
}
