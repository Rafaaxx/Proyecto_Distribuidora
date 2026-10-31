import type { components } from '../../api/schema.gen'
import { evaluarCredito, type AutorizadorCredito } from '../credito/evaluacion'

/**
 * El objeto `credito` del comando de venta sin conexión (change 22a, `design.md` D9; CRE-09,
 * CRE-10): evaluación `SIN_CONEXION` con el saldo local, completa y coherente consigo misma. Si
 * la política bloquea o falta autorización, `evaluarCredito` lanza `ErrorDeCredito` y no hay
 * contenido que encolar. Los importes salen como string (INV-03).
 */
export type CreditoDeRuta = components['schemas']['CreditoRequest']

export interface EntradaCreditoDeRuta {
  /** Nulo = sin control de crédito. */
  limite: string | null
  saldoConsiderado: string
  politica: string
  toleranciaTipo: string | null
  toleranciaValor: string | null
  total: string
  cobranza: string
  aceptaExceso: boolean
  usuarioId: string
  permisosUsuario: readonly string[]
  /** Supervisor cuyo PIN ya se verificó en el teléfono (grupo 9). */
  autorizador: AutorizadorCredito | null
}

export function armarCreditoDeRuta(entrada: EntradaCreditoDeRuta): CreditoDeRuta {
  const r = evaluarCredito({
    limite: entrada.limite,
    saldoActual: entrada.saldoConsiderado,
    totalVenta: entrada.total,
    cobranza: entrada.cobranza,
    politica: entrada.politica,
    toleranciaTipo: entrada.toleranciaTipo,
    toleranciaValor: entrada.toleranciaValor,
    modo: 'SIN_CONEXION',
    aceptaExceso: entrada.aceptaExceso,
    usuarioId: entrada.usuarioId,
    permisosUsuario: entrada.permisosUsuario,
    autorizador: entrada.autorizador,
  })
  return {
    limite: entrada.limite,
    saldo_considerado: entrada.saldoConsiderado,
    politica: entrada.politica as CreditoDeRuta['politica'],
    resolucion: r.resolucion,
    // Hubo exceso y alguien lo resolvió (el usuario lo aceptó o lo cubrió la tolerancia / un permiso).
    acepta_exceso: r.resolucion !== 'SIN_EXCESO',
    ...(r.autorizadorId === null ? {} : { autorizador_id: r.autorizadorId }),
  }
}
