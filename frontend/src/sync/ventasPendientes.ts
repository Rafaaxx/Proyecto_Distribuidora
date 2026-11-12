import { baseLocal } from '../lib/dispositivo/db'

/**
 * Ventas, anulaciones y cobranzas sin enviar del teléfono (change 22a, `design.md` D13, D16; change
 * 22d, D10; change 23, D10; SYN-09, `02` §6.4). La cola es del usuario que la generó: cada comando guarda su
 * `usuario_id`. Las anulaciones (`VENTA_ANULAR`) y las cobranzas (`COBRANZA_REGISTRAR`) se cuentan aparte de las ventas. Solo lectura:
 * nada de acá borra operaciones.
 */
const TIPO_DE_ANULACION = 'VENTA_ANULAR'
const TIPO_DE_COBRANZA = 'COBRANZA_REGISTRAR'
/** Change 24: la entrega del día va por la cola pero no es una venta, una anulación ni una cobranza. */
const TIPO_DE_ENTREGA = 'JORNADA_ENTREGAR'

export interface Pendientes {
  ventas: number
  anulaciones: number
  cobranzas: number
}

function contarPorTipo(tipos: readonly string[]): Pendientes {
  const anulaciones = tipos.filter((t) => t === TIPO_DE_ANULACION).length
  const cobranzas = tipos.filter((t) => t === TIPO_DE_COBRANZA).length
  const entregas = tipos.filter((t) => t === TIPO_DE_ENTREGA).length
  return { ventas: tipos.length - anulaciones - cobranzas - entregas, anulaciones, cobranzas }
}

export async function contarPendientes(usuarioId: string): Promise<Pendientes> {
  const comandos = (await baseLocal.cola.where('estado').equals('PENDIENTE').toArray()).filter(
    (c) => c.sobre.usuario_id === usuarioId,
  )
  return contarPorTipo(comandos.map((c) => c.sobre.tipo))
}

/** Solo las ventas sin enviar (las anulaciones se cuentan con `contarPendientes`). */
export async function contarVentasSinEnviar(usuarioId: string): Promise<number> {
  return (await contarPendientes(usuarioId)).ventas
}

export interface PendientesDeUnVendedor extends Pendientes {
  vendedor: string
}

/** Lo que sin enviar dejó OTRO usuario en este teléfono, por nombre del vendedor (nota congelada de la venta o de la cobranza). */
export async function pendientesDeOtrosUsuarios(usuarioId: string): Promise<PendientesDeUnVendedor[]> {
  const comandos = (await baseLocal.cola.where('estado').equals('PENDIENTE').toArray()).filter(
    (c) => c.sobre.usuario_id !== usuarioId && c.sobre.tipo !== TIPO_DE_ENTREGA,
  )
  const cuenta = new Map<string, Pendientes>()
  for (const comando of comandos) {
    const nombre = (await vendedorDeLaOperacion(comando.sobre.tipo, comando.operation_id)) ?? 'otro usuario'
    const actual = cuenta.get(nombre) ?? { ventas: 0, anulaciones: 0, cobranzas: 0 }
    const suma = contarPorTipo([comando.sobre.tipo])
    cuenta.set(nombre, {
      ventas: actual.ventas + suma.ventas,
      anulaciones: actual.anulaciones + suma.anulaciones,
      cobranzas: actual.cobranzas + suma.cobranzas,
    })
  }
  return [...cuenta.entries()].map(([vendedor, pendientes]) => ({ vendedor, ...pendientes }))
}

async function vendedorDeLaOperacion(tipo: string, operationId: string): Promise<string | undefined> {
  if (tipo === TIPO_DE_COBRANZA) {
    return (await baseLocal.cobranzas.where('operation_id').equals(operationId).first())?.vendedor_nombre
  }
  const venta = tipo === TIPO_DE_ANULACION ? await ventaDeLaAnulacion(operationId) : await ventaDeLaOperacion(operationId)
  return venta?.nota?.vendedor_nombre
}

function ventaDeLaOperacion(operationId: string) {
  return baseLocal.ventas.where('operation_id').equals(operationId).first()
}

async function ventaDeLaAnulacion(operationId: string) {
  const anulacion = await baseLocal.anulaciones.where('operation_id').equals(operationId).first()
  return anulacion === undefined ? undefined : baseLocal.ventas.get(anulacion.venta_id)
}

/** «2 ventas, 1 anulación y 1 cobranza»: une las partes que no son cero (change 23, D10). */
export function nombreDeLoPendiente({ ventas, anulaciones, cobranzas }: Pendientes): string {
  const partes = [
    ventas === 0 ? null : `${ventas} ${ventas === 1 ? 'venta' : 'ventas'}`,
    anulaciones === 0 ? null : `${anulaciones} ${anulaciones === 1 ? 'anulación' : 'anulaciones'}`,
    cobranzas === 0 ? null : `${cobranzas} ${cobranzas === 1 ? 'cobranza' : 'cobranzas'}`,
  ].filter((parte): parte is string => parte !== null)
  const ultima = partes.pop()
  return partes.length === 0 ? (ultima ?? '') : `${partes.join(', ')} y ${ultima}`
}

function esUno({ ventas, anulaciones, cobranzas }: Pendientes): boolean {
  return ventas + anulaciones + cobranzas === 1
}

/** "Tenés 1 venta sin enviar. Queda guardada ..." (cerrar sesión, D16; con anulaciones y cobranzas, D10). */
export function avisoDeCierreConPendientes(pendientes: Pendientes): string {
  const cola = esUno(pendientes)
    ? 'Queda guardada en el teléfono y se envía cuando vuelvas a entrar vos.'
    : 'Quedan guardadas en el teléfono y se envían cuando vuelvas a entrar vos.'
  return `Tenés ${nombreDeLoPendiente(pendientes)} sin enviar. ${cola}`
}

/** "Hay 1 venta sin enviar de {nombre}..." (otro usuario inicia sesión, D16; con anulaciones, D10). */
export function avisoDePendientesDeOtro(pendientes: PendientesDeUnVendedor): string {
  const cola = esUno(pendientes) ? 'Queda guardada en el teléfono.' : 'Quedan guardadas en el teléfono.'
  return `Hay ${nombreDeLoPendiente(pendientes)} sin enviar de ${pendientes.vendedor}. ${cola}`
}
