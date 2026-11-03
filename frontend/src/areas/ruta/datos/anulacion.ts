import { liveQuery } from 'dexie'
import { useEffect, useState } from 'react'

import { motivoDeNoAnular, type MotivoDeNoAnular } from '../../../domain/ruta/habilitacionDeAnulacion'
import { AMBITO_DE_ANULACION_DE_VENTA } from '../../../domain/ventas/anulacion'
import type { MotivoLocal } from '../../../domain/ruta/armadoDeVentaLocal'
import { parsearImporteDesdeApi } from '../../../lib/money'
import { baseLocal, type AnulacionLocal, type VentaLocal } from '../../../lib/dispositivo/db'
import { APP_VERSION } from '../../../sync/appVersion'
import { leerJornadaNoAbierta, type JornadaNoAbierta } from '../../../sync/estadoDeJornada'
import { ventaBloqueadaPorVersion } from '../../../sync/versionMinima'
import { useConsultaLocal } from './lecturas'

/**
 * Lecturas de Dexie para anular una venta desde el teléfono y mostrar su anulación (change 22d,
 * `design.md` D5, D9, D10; VTA-20, VTA-24, RUT-09). Solo leen; las reglas de habilitación son
 * funciones puras de `domain/ruta/habilitacionDeAnulacion.ts`.
 */
export interface DatosParaAnular {
  venta: VentaLocal
  /** La anulación ya hecha en el teléfono, si hay. */
  anulacion: AnulacionLocal | null
  permisos: string[]
  jornadaDeLaSesionId: string
  usuarioId: string
  /** Motivos activos del ámbito `ANULACION_VENTA` de los datos del día. */
  motivos: MotivoLocal[]
  esConsumidorFinal: boolean
  /** Importe cobrado en el acto (string de dos decimales) o `null` si no hubo cobro. */
  cobrado: string | null
  jornadaNoAbierta: JornadaNoAbierta | null
  versionBloqueada: boolean
}

/** Por qué no se ofrece «Anular venta» con estos datos (D5); `null` si se ofrece. */
export function motivoDeNoAnularDeDatos(datos: DatosParaAnular): MotivoDeNoAnular | null {
  return motivoDeNoAnular({
    permisos: datos.permisos,
    venta: datos.venta,
    jornadaDeLaSesionId: datos.jornadaDeLaSesionId,
    tieneAnulacion: datos.anulacion !== null,
    jornadaNoAbierta: datos.jornadaNoAbierta !== null,
    versionBloqueada: datos.versionBloqueada,
  })
}

export type LecturaParaAnular = { estado: 'cargando' } | { estado: 'no_encontrada' } | ({ estado: 'lista' } & DatosParaAnular)

export function useDatosParaAnular(ventaId: string): LecturaParaAnular {
  const lectura = useConsultaLocal<{ datos: DatosParaAnular } | { faltan: true }>(async () => {
    const [venta, sesion] = await Promise.all([baseLocal.ventas.get(ventaId), baseLocal.sesion.get('actual')])
    if (venta === undefined || sesion === undefined) return { estado: 'listo', faltan: true }
    const [anulacion, cobranza, catalogos, cliente, jornadaNoAbierta, versionBloqueada] = await Promise.all([
      baseLocal.anulaciones.get(ventaId),
      baseLocal.cobranzas.where('venta_id').equals(ventaId).first(),
      baseLocal.catalogos.toArray(),
      baseLocal.clientes.get(venta.cliente_id),
      leerJornadaNoAbierta(),
      ventaBloqueadaPorVersion(APP_VERSION),
    ])
    const motivos: MotivoLocal[] = []
    for (const catalogo of catalogos) {
      if (catalogo.clave === 'motivos') motivos.push(...catalogo.items.filter((m) => m.ambito === AMBITO_DE_ANULACION_DE_VENTA))
    }
    const cobrado = cobranza === undefined || !parsearImporteDesdeApi(cobranza.total).greaterThan(0) ? null : cobranza.total
    return {
      estado: 'listo',
      datos: {
        venta,
        anulacion: anulacion ?? null,
        permisos: sesion.permisos,
        jornadaDeLaSesionId: sesion.jornada.id,
        usuarioId: sesion.usuario.id,
        motivos,
        esConsumidorFinal: venta.nota?.cliente.es_consumidor_final ?? cliente?.es_consumidor_final ?? false,
        cobrado,
        jornadaNoAbierta,
        versionBloqueada,
      },
    }
  }, [ventaId])
  if (lectura.estado === 'cargando') return { estado: 'cargando' }
  if (lectura.estado === 'sin_datos' || 'faltan' in lectura) return { estado: 'no_encontrada' }
  return { estado: 'lista', ...lectura.datos }
}

/** La anulación local de una venta; `undefined` mientras carga, `null` si no hay. */
export function useAnulacionDeVenta(ventaId: string): AnulacionLocal | null | undefined {
  const [anulacion, setAnulacion] = useState<AnulacionLocal | null | undefined>(undefined)
  useEffect(() => {
    const suscripcion = liveQuery(() => baseLocal.anulaciones.get(ventaId)).subscribe({
      next: (a) => setAnulacion(a ?? null),
      error: () => setAnulacion(null),
    })
    return () => suscripcion.unsubscribe()
  }, [ventaId])
  return anulacion
}

/**
 * Lo que el teléfono sabe de la jornada de la sesión cuando ya no está abierta (D8, D9); `null`
 * si está abierta o no se sabe nada. `undefined` mientras carga. Vale sin señal y tras recargar.
 */
export function useJornadaNoAbierta(): JornadaNoAbierta | null | undefined {
  const [estado, setEstado] = useState<JornadaNoAbierta | null | undefined>(undefined)
  useEffect(() => {
    const suscripcion = liveQuery(() => leerJornadaNoAbierta()).subscribe({
      next: setEstado,
      error: () => setEstado(null),
    })
    return () => suscripcion.unsubscribe()
  }, [])
  return estado
}
