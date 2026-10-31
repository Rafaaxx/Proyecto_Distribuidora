import type { DatosParaVender, MedioPagoLocal, MotivoLocal } from '../../../domain/ruta/armadoDeVentaLocal'
import { baseLocal } from '../../../lib/dispositivo/db'
import { useConsultaLocal, type Lectura } from './lecturas'

/**
 * Lectura de Dexie de todo lo que necesita armar una venta de ruta (change 22a, `design.md` D14):
 * los maestros del bootstrap y los movimientos locales de la jornada. Solo lee; el armado y las
 * reglas son funciones puras de `domain/ruta/armadoDeVentaLocal.ts`.
 */
export async function leerDatosParaVender(): Promise<DatosParaVender | null> {
  const [sesion, configuracion] = await Promise.all([
    baseLocal.sesion.get('actual'),
    baseLocal.configuracion.get('organizacion'),
  ])
  if (sesion === undefined || configuracion === undefined) return null

  const [clientes, productos, presentaciones, listas, versiones, precios, reglas, stock, catalogos, autorizadores, movimientos] =
    await Promise.all([
      baseLocal.clientes.toArray(),
      baseLocal.productos.toArray(),
      baseLocal.presentaciones.toArray(),
      baseLocal.listas.toArray(),
      baseLocal.versiones.toArray(),
      baseLocal.precios.toArray(),
      baseLocal.reglas_descuento.toArray(),
      baseLocal.stock.toArray(),
      baseLocal.catalogos.toArray(),
      baseLocal.autorizadores.toArray(),
      baseLocal.movimientos_locales.filter((m) => m.jornada_id === sesion.jornada.id).toArray(),
    ])
  const medios: MedioPagoLocal[] = []
  const motivos: MotivoLocal[] = []
  for (const catalogo of catalogos) {
    if (catalogo.clave === 'medios_pago') medios.push(...catalogo.items)
    else if (catalogo.clave === 'motivos') motivos.push(...catalogo.items)
  }
  return {
    sesion,
    configuracion,
    clientes,
    productos,
    presentaciones,
    listas,
    versiones,
    precios,
    reglas,
    stock,
    mediosPago: medios,
    motivos,
    autorizadores,
    movimientos,
  }
}

export function useDatosParaVender(): Lectura<{ datos: DatosParaVender }> {
  return useConsultaLocal<{ datos: DatosParaVender }>(async () => {
    const datos = await leerDatosParaVender()
    return datos === null ? { estado: 'sin_datos' } : { estado: 'listo', datos }
  }, [])
}
