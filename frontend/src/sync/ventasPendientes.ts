import { baseLocal } from '../lib/dispositivo/db'

/**
 * Ventas sin enviar del teléfono (change 22a, `design.md` D13, D16; SYN-09, `02` §6.4). La cola
 * es del usuario que la generó: cada comando guarda su `usuario_id`. En el 22a todas están
 * `PENDIENTE`. Solo lectura: nada de acá borra operaciones.
 */
export async function contarVentasSinEnviar(usuarioId: string): Promise<number> {
  const comandos = await baseLocal.cola.where('estado').equals('PENDIENTE').toArray()
  return comandos.filter((c) => c.sobre.usuario_id === usuarioId).length
}

export interface PendientesDeUnVendedor {
  vendedor: string
  cantidad: number
}

/** Las ventas sin enviar que dejó OTRO usuario en este teléfono, por nombre del vendedor (nota congelada). */
export async function pendientesDeOtrosUsuarios(usuarioId: string): Promise<PendientesDeUnVendedor[]> {
  const comandos = (await baseLocal.cola.where('estado').equals('PENDIENTE').toArray()).filter(
    (c) => c.sobre.usuario_id !== usuarioId,
  )
  const cuenta = new Map<string, number>()
  for (const comando of comandos) {
    const venta = await baseLocal.ventas.where('operation_id').equals(comando.operation_id).first()
    const nombre = venta?.nota?.vendedor_nombre ?? 'otro usuario'
    cuenta.set(nombre, (cuenta.get(nombre) ?? 0) + 1)
  }
  return [...cuenta.entries()].map(([vendedor, cantidad]) => ({ vendedor, cantidad }))
}

/** "Tenés 1 venta sin enviar. Queda guardada ..." (cerrar sesión, D16). */
export function avisoDeCierreConPendientes(cantidad: number): string {
  return cantidad === 1
    ? 'Tenés 1 venta sin enviar. Queda guardada en el teléfono y se envía cuando vuelvas a entrar vos.'
    : `Tenés ${cantidad} ventas sin enviar. Quedan guardadas en el teléfono y se envían cuando vuelvas a entrar vos.`
}

/** "Hay 1 venta sin enviar de {nombre}..." (otro usuario inicia sesión, D16). */
export function avisoDePendientesDeOtro(pendientes: PendientesDeUnVendedor): string {
  return pendientes.cantidad === 1
    ? `Hay 1 venta sin enviar de ${pendientes.vendedor}. Queda guardada en el teléfono.`
    : `Hay ${pendientes.cantidad} ventas sin enviar de ${pendientes.vendedor}. Quedan guardadas en el teléfono.`
}
