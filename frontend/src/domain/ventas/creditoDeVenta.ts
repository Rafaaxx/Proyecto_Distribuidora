/**
 * Panel de crédito de la pantalla de venta (change 18b, tarea 13.1; CRE-01 a CRE-07, D5, D6, D16,
 * D20). Usa la gemela del motor `cre01` (`domain/credito/`): mismo exceso y mismas políticas que el
 * servidor, que decide igual (TR-10). Función pura; ningún importe pasa por `number` (INV-03).
 */

import { ErrorDeCredito } from '../credito/errores'
import { calcularExceso, evaluarCredito } from '../credito/evaluacion'
import { formatearMonto } from '../cuentas-corrientes/presentacion'

/** Lo que dice `GET /ventas/credito` (herencia de la organización ya resuelta). */
export interface DatosDeCreditoDeVenta {
  /** Nulo = sin control. */
  limite: string | null
  saldo: string
  politica: string
  toleranciaTipo: string | null
  toleranciaValor: string | null
}

export type DecisionDeCredito =
  | 'sin-control'
  | 'sin-exceso'
  | 'pide-aceptar'
  | 'aceptado'
  | 'permiso-propio'
  | 'pide-autorizador'
  | 'bloqueado'
  | 'no-evaluable'

export interface PanelDeCredito {
  decision: DecisionDeCredito
  limite: string | null
  saldo: string
  /** Nulo sin límite; negativo si el cliente ya está excedido. */
  disponible: string | null
  saldoResultante: string
  exceso: string
  politica: string
}

export interface EntradaDelPanel {
  datos: DatosDeCreditoDeVenta
  total: string
  cobranza: string
  aceptaExceso: boolean
  /** El usuario tiene `SUPERAR_CREDITO` (de `GET /ventas/contexto`). */
  puedeSuperar: boolean
}

function sinEvaluar(datos: DatosDeCreditoDeVenta): PanelDeCredito {
  return {
    decision: 'no-evaluable',
    limite: datos.limite,
    saldo: datos.saldo,
    disponible: null,
    saldoResultante: datos.saldo,
    exceso: '0.00',
    politica: datos.politica,
  }
}

/** Disponible, saldo resultante, exceso y qué hay que hacer según la política (con conexión). */
export function evaluarPanelDeCredito(entrada: EntradaDelPanel): PanelDeCredito {
  const { datos } = entrada
  try {
    const numeros = calcularExceso({
      limite: datos.limite,
      saldoActual: datos.saldo,
      totalVenta: entrada.total,
      cobranza: entrada.cobranza,
    })
    const base = {
      limite: datos.limite,
      saldo: datos.saldo,
      disponible: numeros.disponible?.toFixed(2) ?? null,
      saldoResultante: numeros.saldoResultante.toFixed(2),
      exceso: numeros.exceso.toFixed(2),
      politica: datos.politica,
    }
    try {
      const resultado = evaluarCredito({
        limite: datos.limite,
        saldoActual: datos.saldo,
        totalVenta: entrada.total,
        cobranza: entrada.cobranza,
        politica: datos.politica,
        toleranciaTipo: datos.toleranciaTipo,
        toleranciaValor: datos.toleranciaValor,
        modo: 'CON_CONEXION',
        aceptaExceso: entrada.aceptaExceso,
        usuarioId: 'yo',
        permisosUsuario: entrada.puedeSuperar ? ['SUPERAR_CREDITO'] : [],
        autorizador: null,
      })
      switch (resultado.resolucion) {
        case 'SIN_EXCESO':
          return { ...base, decision: datos.limite === null ? 'sin-control' : 'sin-exceso' }
        case 'ADVERTENCIA_ACEPTADA':
          return { ...base, decision: 'aceptado' }
        case 'PERMISO_PROPIO':
          return { ...base, decision: 'permiso-propio' }
        default:
          return { ...base, decision: 'no-evaluable' }
      }
    } catch (error) {
      if (!(error instanceof ErrorDeCredito)) throw error
      if (error.codigo === 'EXCESO_CREDITO_SIN_ACEPTAR') return { ...base, decision: 'pide-aceptar' }
      if (error.codigo === 'CREDITO_EXCEDIDO') return { ...base, decision: 'bloqueado' }
      if (error.codigo === 'AUTORIZACION_CREDITO_REQUERIDA') return { ...base, decision: 'pide-autorizador' }
      return { ...base, decision: 'no-evaluable' }
    }
  } catch (error) {
    // Un dato que no es un importe exacto no puede romper la pantalla: el servidor decide igual.
    if (error instanceof ErrorDeCredito) return sinEvaluar(datos)
    throw error
  }
}

/** Qué dice el panel según la decisión. */
export function textoDeDecisionDeCredito(panel: PanelDeCredito): string {
  const exceso = formatearMonto(panel.exceso)
  switch (panel.decision) {
    case 'sin-control':
      return 'El cliente no tiene límite de crédito.'
    case 'sin-exceso':
      return 'Dentro del límite de crédito.'
    case 'pide-aceptar':
      return `La venta se pasa del límite por ${exceso}.`
    case 'aceptado':
      return `La venta se pasa del límite por ${exceso}; confirmaste venderla igual.`
    case 'permiso-propio':
      return `La venta deja al cliente ${exceso} sobre su límite; la autorizás vos con tu permiso.`
    case 'pide-autorizador':
      return `La venta deja al cliente ${exceso} sobre su límite y necesita autorización.`
    case 'bloqueado':
      return `No se puede confirmar: el cliente se pasa del límite por ${exceso}. Aumentá la cobranza o sacá productos.`
    case 'no-evaluable':
      return 'No pudimos calcular el crédito; el sistema lo revisa al confirmar.'
  }
}
