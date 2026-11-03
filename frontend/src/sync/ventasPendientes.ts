import { baseLocal } from '../lib/dispositivo/db'

/**
 * Ventas y anulaciones sin enviar del teléfono (change 22a, `design.md` D13, D16; change 22d,
 * D10; SYN-09, `02` §6.4). La cola es del usuario que la generó: cada comando guarda su
 * `usuario_id`. Las anulaciones (`VENTA_ANULAR`) se cuentan aparte de las ventas. Solo lectura:
 * nada de acá borra operaciones.
 */
const TIPO_DE_ANULACION = 'VENTA_ANULAR'

export interface Pendientes {
  ventas: number
  anulaciones: number
}

export async function contarPendientes(usuarioId: string): Promise<Pendientes> {
  const comandos = (await baseLocal.cola.where('estado').equals('PENDIENTE').toArray()).filter(
    (c) => c.sobre.usuario_id === usuarioId,
  )
  const anulaciones = comandos.filter((c) => c.sobre.tipo === TIPO_DE_ANULACION).length
  return { ventas: comandos.length - anulaciones, anulaciones }
}

/** Solo las ventas sin enviar (las anulaciones se cuentan con `contarPendientes`). */
export async function contarVentasSinEnviar(usuarioId: string): Promise<number> {
  return (await contarPendientes(usuarioId)).ventas
}

export interface PendientesDeUnVendedor extends Pendientes {
  vendedor: string
}

/** Las ventas y anulaciones sin enviar que dejó OTRO usuario en este teléfono, por nombre del vendedor (nota congelada). */
export async function pendientesDeOtrosUsuarios(usuarioId: string): Promise<PendientesDeUnVendedor[]> {
  const comandos = (await baseLocal.cola.where('estado').equals('PENDIENTE').toArray()).filter(
    (c) => c.sobre.usuario_id !== usuarioId,
  )
  const cuenta = new Map<string, Pendientes>()
  for (const comando of comandos) {
    const esAnulacion = comando.sobre.tipo === TIPO_DE_ANULACION
    const venta = esAnulacion ? await ventaDeLaAnulacion(comando.operation_id) : await ventaDeLaOperacion(comando.operation_id)
    const nombre = venta?.nota?.vendedor_nombre ?? 'otro usuario'
    const actual = cuenta.get(nombre) ?? { ventas: 0, anulaciones: 0 }
    cuenta.set(nombre, esAnulacion ? { ...actual, anulaciones: actual.anulaciones + 1 } : { ...actual, ventas: actual.ventas + 1 })
  }
  return [...cuenta.entries()].map(([vendedor, pendientes]) => ({ vendedor, ...pendientes }))
}

function ventaDeLaOperacion(operationId: string) {
  return baseLocal.ventas.where('operation_id').equals(operationId).first()
}

async function ventaDeLaAnulacion(operationId: string) {
  const anulacion = await baseLocal.anulaciones.where('operation_id').equals(operationId).first()
  return anulacion === undefined ? undefined : baseLocal.ventas.get(anulacion.venta_id)
}

function nombreDeLoPendiente({ ventas, anulaciones }: Pendientes): string {
  const parteDeVentas = `${ventas} ${ventas === 1 ? 'venta' : 'ventas'}`
  const parteDeAnulaciones = `${anulaciones} ${anulaciones === 1 ? 'anulación' : 'anulaciones'}`
  if (anulaciones === 0) return parteDeVentas
  if (ventas === 0) return parteDeAnulaciones
  return `${parteDeVentas} y ${parteDeAnulaciones}`
}

function esUno({ ventas, anulaciones }: Pendientes): boolean {
  return ventas + anulaciones === 1
}

/** "Tenés 1 venta sin enviar. Queda guardada ..." (cerrar sesión, D16; con anulaciones, D10). */
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
