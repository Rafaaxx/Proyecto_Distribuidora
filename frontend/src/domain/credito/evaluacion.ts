/**
 * Evaluación de crédito de la venta: disponible, saldo resultante, exceso, tolerancia y
 * resolución por política y modo (CRE-01 a CRE-07, INV-03, ADR-016, ADR-032; `design.md` D5, D6,
 * D8 del change 18b). Espejo de `backend/app/modules/clientes/domain/credito.py`: mismos casos de
 * `shared/fixtures/calculo/cre-01-credito.json` (`"motor": "cre01"`).
 *
 * Función pura. Recibe límite, política y tolerancia YA resueltos con la herencia (cliente, si no
 * organización). No verifica ningún PIN: que `autorizador` llegue acá significa que ya se
 * verificó. Nada se convierte a `number` (INV-03); todo el cálculo usa `Importe` con
 * `lib/money.ts`.
 */

import type { Importe } from '../../lib/money'
import { parsearImporteDesdeApi, redondearImporte } from '../../lib/money'
import { ErrorDeCredito } from './errores'

export const PERMISO_SUPERAR_CREDITO = 'SUPERAR_CREDITO'

const POLITICAS = ['ADVERTIR', 'AUTORIZAR', 'BLOQUEAR'] as const
const TIPOS_TOLERANCIA = ['IMPORTE', 'PORCENTAJE'] as const
const MODOS = ['CON_CONEXION', 'SIN_CONEXION'] as const
const DECIMALES = 2

export type ResolucionCredito =
  | 'SIN_EXCESO'
  | 'ADVERTENCIA_ACEPTADA'
  | 'PERMISO_PROPIO'
  | 'PIN_SUPERVISOR'
  | 'TOLERANCIA_OFFLINE'

/** Otro usuario de la organización que autoriza (con PIN), con los permisos que tiene hoy. */
export interface AutorizadorCredito {
  usuarioId: string
  permisos: readonly string[]
}

export interface EntradaCredito {
  /** Nulo = sin control de crédito. */
  limite: string | null
  saldoActual: string
  totalVenta: string
  cobranza: string
  politica: string
  toleranciaTipo: string | null
  toleranciaValor: string | null
  modo: string
  aceptaExceso: boolean
  usuarioId: string
  permisosUsuario: readonly string[]
  autorizador: AutorizadorCredito | null
}

/** Lo que la venta congela (CRE-01 a CRE-03, D5). */
export interface ResultadoCredito {
  /** Nulo sin límite. */
  disponible: Importe | null
  saldoResultante: Importe
  exceso: Importe
  tolerancia: Importe
  resolucion: ResolucionCredito
  autorizadorId: string | null
}

/** Un importe entra como cadena decimal exacta; un número nativo o un booleano se rechaza. */
function aImporteExacto(valor: unknown, nombre: string): Importe {
  if (typeof valor !== 'string') {
    throw new ErrorDeCredito(
      'ENTRADA_NO_ES_DINERO_EXACTO',
      `${nombre} debe ser una cadena decimal exacta, no ${typeof valor} (INV-03).`,
    )
  }
  try {
    return parsearImporteDesdeApi(valor)
  } catch {
    throw new ErrorDeCredito(
      'ENTRADA_NO_ES_DINERO_EXACTO',
      `${nombre} no es un valor decimal exacto: "${valor}" (INV-03).`,
    )
  }
}

function enCatalogo<T extends string>(catalogo: readonly T[], valor: unknown): valor is T {
  return typeof valor === 'string' && (catalogo as readonly string[]).includes(valor)
}

function maximo(a: Importe, b: Importe): Importe {
  return a.greaterThan(b) ? a : b
}

function minimo(a: Importe, b: Importe): Importe {
  return a.lessThan(b) ? a : b
}

/** D8: `IMPORTE` es el valor; `PORCENTAJE` (`2.50` = 2,50 %) es sobre el límite, redondeado una
 * sola vez, mitad hacia arriba (ADR-032, TR-03). Sin tolerancia o sin límite, cero. */
function toleranciaEnImporte(
  limite: Importe | null,
  tipo: string | null,
  valor: Importe | null,
  cero: Importe,
): Importe {
  if (tipo === null || valor === null || limite === null) return cero
  if (tipo === 'IMPORTE') return redondearImporte(valor)
  return redondearImporte(limite.times(valor).dividedBy(100))
}

/** Lo que dan los números de una venta sobre el límite, sin política ni resolución. */
export interface CalculoDeExceso {
  /** Nulo sin límite (CRE-01). */
  disponible: Importe | null
  saldoResultante: Importe
  exceso: Importe
}

export interface EntradaDeExceso {
  /** Nulo = sin control de crédito. */
  limite: string | null
  saldoActual: string
  totalVenta: string
  cobranza: string
}

/**
 * CRE-01, CRE-02, D5: disponible = límite − saldo; resultante = saldo + total − cobranza;
 * exceso = `mín(máx(0, total − cobranza), máx(0, resultante − límite))`. Sin límite no hay control
 * ni exceso. Gemela de `clientes/domain/credito.py::calcular_exceso`; la usa `evaluarCredito` y
 * el panel de crédito de la pantalla de venta.
 */
export function calcularExceso(entrada: EntradaDeExceso): CalculoDeExceso {
  const saldoActual = aImporteExacto(entrada.saldoActual, 'El saldo actual')
  const totalVenta = aImporteExacto(entrada.totalVenta, 'El total de la venta')
  const cobranza = aImporteExacto(entrada.cobranza, 'La cobranza')
  const limite =
    entrada.limite === null ? null : aImporteExacto(entrada.limite, 'El límite de crédito')
  const cero = redondearImporte('0')
  const saldoResultante = redondearImporte(saldoActual.plus(totalVenta).minus(cobranza))
  const disponible = limite === null ? null : redondearImporte(limite.minus(saldoActual))
  if (limite === null) return { disponible, saldoResultante, exceso: cero }
  const exceso = redondearImporte(
    minimo(maximo(cero, totalVenta.minus(cobranza)), maximo(cero, saldoResultante.minus(limite))),
  )
  return { disponible, saldoResultante, exceso }
}

export function evaluarCredito(entrada: EntradaCredito): ResultadoCredito {
  const limite =
    entrada.limite === null ? null : aImporteExacto(entrada.limite, 'El límite de crédito')
  // Valida los tres importes de la entrada antes que el resto (INV-03).
  const { disponible, saldoResultante, exceso } = calcularExceso({
    limite: entrada.limite,
    saldoActual: entrada.saldoActual,
    totalVenta: entrada.totalVenta,
    cobranza: entrada.cobranza,
  })
  const valorTolerancia =
    entrada.toleranciaValor === null
      ? null
      : aImporteExacto(entrada.toleranciaValor, 'El valor de la tolerancia')

  if (limite !== null && (limite.isNegative() || limite.decimalPlaces() > DECIMALES)) {
    throw new ErrorDeCredito(
      'LIMITE_CREDITO_INVALIDO',
      'El límite de crédito no puede ser negativo ni tener más de dos decimales (CRE-01).',
    )
  }
  if (!enCatalogo(POLITICAS, entrada.politica)) {
    throw new ErrorDeCredito(
      'POLITICA_CREDITO_INVALIDA',
      `La política "${entrada.politica}" no está en el catálogo (CRE-03).`,
    )
  }
  const tipoTolerancia = entrada.toleranciaTipo
  if ((tipoTolerancia === null) !== (valorTolerancia === null)) {
    throw new ErrorDeCredito(
      'TOLERANCIA_OFFLINE_INVALIDA',
      'La tolerancia offline se informa en pareja: tipo y valor, o ninguno (CRE-06).',
    )
  }
  if (tipoTolerancia !== null && !enCatalogo(TIPOS_TOLERANCIA, tipoTolerancia)) {
    throw new ErrorDeCredito(
      'TOLERANCIA_OFFLINE_INVALIDA',
      `El tipo de tolerancia "${tipoTolerancia}" no está en el catálogo (CRE-06).`,
    )
  }
  if (
    valorTolerancia !== null &&
    (valorTolerancia.isNegative() || valorTolerancia.decimalPlaces() > DECIMALES)
  ) {
    throw new ErrorDeCredito(
      'TOLERANCIA_OFFLINE_INVALIDA',
      'El valor de la tolerancia no puede ser negativo ni tener más de dos decimales (CRE-06).',
    )
  }
  if (!enCatalogo(MODOS, entrada.modo)) {
    throw new ErrorDeCredito(
      'MODO_CREDITO_INVALIDO',
      `El modo "${entrada.modo}" no está en el catálogo (CRE-06).`,
    )
  }

  const cero = redondearImporte('0')
  const tolerancia = toleranciaEnImporte(limite, tipoTolerancia, valorTolerancia, cero)

  const resultado = (
    resolucion: ResolucionCredito,
    autorizadorId: string | null = null,
  ): ResultadoCredito => ({
    disponible,
    saldoResultante,
    exceso,
    tolerancia,
    resolucion,
    autorizadorId,
  })

  if (exceso.isZero()) return resultado('SIN_EXCESO')

  if (entrada.politica === 'ADVERTIR') {
    if (!entrada.aceptaExceso) {
      throw new ErrorDeCredito(
        'EXCESO_CREDITO_SIN_ACEPTAR',
        `La venta deja un exceso de ${exceso.toFixed(2)} sobre el límite y no se aceptó (CRE-04).`,
      )
    }
    return resultado('ADVERTENCIA_ACEPTADA')
  }

  if (entrada.politica === 'BLOQUEAR') {
    throw new ErrorDeCredito(
      'CREDITO_EXCEDIDO',
      `La venta deja un exceso de ${exceso.toFixed(2)} sobre el límite y la política bloquea (CRE-07).`,
    )
  }

  // AUTORIZAR
  const conConexion = entrada.modo === 'CON_CONEXION'
  if (!conConexion && exceso.lessThanOrEqualTo(tolerancia)) return resultado('TOLERANCIA_OFFLINE')
  if (entrada.permisosUsuario.includes(PERMISO_SUPERAR_CREDITO)) {
    return resultado('PERMISO_PROPIO', entrada.usuarioId)
  }
  if (entrada.autorizador !== null) {
    if (!entrada.autorizador.permisos.includes(PERMISO_SUPERAR_CREDITO)) {
      throw new ErrorDeCredito(
        'AUTORIZADOR_SIN_PERMISO',
        `El autorizador no tiene el permiso ${PERMISO_SUPERAR_CREDITO} (CRE-05).`,
      )
    }
    return resultado('PIN_SUPERVISOR', entrada.autorizador.usuarioId)
  }
  if (conConexion) {
    throw new ErrorDeCredito(
      'AUTORIZACION_CREDITO_REQUERIDA',
      `El exceso de ${exceso.toFixed(2)} necesita permiso propio o un supervisor con PIN (CRE-05).`,
    )
  }
  throw new ErrorDeCredito(
    'CREDITO_EXCEDIDO',
    `El exceso de ${exceso.toFixed(2)} supera la tolerancia de ${tolerancia.toFixed(2)} y no hay permiso propio ni PIN: se comporta como BLOQUEAR (CRE-06).`,
  )
}
