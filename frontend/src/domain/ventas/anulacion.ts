import Decimal from "decimal.js";

import { formatearMonto } from "../cuentas-corrientes/presentacion";

export type MovimientoAnulacion = {
  tipo: "ANULACION_VENTA" | "ANULACION_COBRANZA";
  importe: string;
};

export type EfectoCuentaAnulacion = {
  movimientos: MovimientoAnulacion[];
  saldoFinalRelativo: string;
};

function toDecimal(v: string | number | Decimal): Decimal {
  if (v instanceof Decimal) return v;
  return new Decimal(String(v));
}

function formatMoney(v: Decimal): string {
  return v.toDecimalPlaces(2, Decimal.ROUND_HALF_UP).toFixed(2);
}

export function efectoEnCuenta(
  totalVenta: string | number | Decimal,
  importeCobranza: string | number | Decimal | null | undefined,
  devuelveDinero: boolean | null | undefined,
): EfectoCuentaAnulacion {
  const total = toDecimal(totalVenta);
  let cobro = importeCobranza === null || importeCobranza === undefined ? new Decimal(0) : toDecimal(importeCobranza);
  if (cobro.lt(0)) cobro = new Decimal(0);

  const movimientos: MovimientoAnulacion[] = [];
  movimientos.push({ tipo: "ANULACION_VENTA", importe: formatMoney(total) });

  if (devuelveDinero === true && cobro.gt(0)) {
    movimientos.push({ tipo: "ANULACION_COBRANZA", importe: formatMoney(cobro) });
  }

  let saldo: Decimal;
  if (cobro.eq(0)) {
    saldo = total.neg();
  } else if (devuelveDinero === true) {
    saldo = new Decimal(0);
  } else {
    saldo = cobro.neg();
  }
  return { movimientos, saldoFinalRelativo: formatMoney(saldo) };
}

export function debePreguntarPorDinero(tieneCobranza: boolean): boolean {
  return tieneCobranza;
}

// --- Pantalla de anulación (change 19, tarea 9.1; `design.md` D2, D3, D16) -------------------

/** Ámbito de los motivos de anulación de una venta (VTA-20, TR-09). */
export const AMBITO_DE_ANULACION_DE_VENTA = "ANULACION_VENTA";

/** "Anular venta" solo con `ANULAR_VENTA` y sobre una venta `CONFIRMADA` (VTA-20, D16). */
export function puedeAnularVenta(estado: string, tienePermiso: boolean): boolean {
  return tienePermiso && estado === "CONFIRMADA";
}

/**
 * Lo que viaja en `devuelve_dinero` (VTA-22, CLI-03, D2, D3): sin cobranza confirmada se omite
 * (nulo: el servidor lo prohíbe, `DEVOLUCION_INVALIDA`); con cobranza es la elección del usuario;
 * el consumidor final con cobranza devuelve siempre.
 */
export function devuelveDineroAEnviar(datos: {
  tieneCobranza: boolean;
  esConsumidorFinal: boolean;
  eleccion: boolean | null;
}): boolean | null {
  if (!debePreguntarPorDinero(datos.tieneCobranza)) return null;
  if (datos.esConsumidorFinal) return true;
  return datos.eleccion;
}

/**
 * Qué hace la anulación en la cuenta del cliente, en frases (D16), con el mismo cálculo que el
 * servidor (`efectoEnCuenta`, casos `vta22`). No muestra saldos absolutos: quien solo tiene
 * `ANULAR_VENTA` no los lee. Con cobro y sin elegir todavía no hay efecto que mostrar.
 */
export function textosDelEfectoEnCuenta(
  totalVenta: string,
  importeCobranza: string | null,
  devuelveDinero: boolean | null,
): string[] {
  const hayCobro = importeCobranza !== null && toDecimal(importeCobranza).gt(0);
  if (hayCobro && devuelveDinero === null) return [];
  const efecto = efectoEnCuenta(totalVenta, importeCobranza, devuelveDinero);
  const textos: string[] = [];
  for (const movimiento of efecto.movimientos) {
    textos.push(
      movimiento.tipo === "ANULACION_VENTA"
        ? `La cuenta del cliente baja ${formatearMonto(movimiento.importe)}.`
        : `Y sube ${formatearMonto(movimiento.importe)} por el cobro devuelto.`,
    );
  }
  if (hayCobro && devuelveDinero === false) {
    textos.push(`El cobro de ${formatearMonto(importeCobranza)} queda a favor del cliente.`);
  }
  return textos;
}

const TEXTO_POR_CODIGO_DE_ANULACION: Record<string, string> = {
  VENTA_YA_ANULADA: "La venta ya estaba anulada: se anula una sola vez. Se actualizó el detalle.",
  UBICACION_TOMADA:
    "La ubicación de la venta está tomada por la jornada de otro vendedor. Solo puede anular quien tiene permiso para mover una ubicación tomada.",
  UBICACION_INACTIVA: "La ubicación de la venta está inactiva: no se le puede devolver la mercadería. Activala y volvé a intentar.",
  MOTIVO_INVALIDO: "El motivo elegido ya no es válido. Elegí otro motivo de la lista.",
};

/** Texto del error de la anulación (D16); un código sin texto propio usa el mensaje del servidor. */
export function textoDeErrorDeAnulacion(codigo: string, mensajeDelServidor: string): string {
  return TEXTO_POR_CODIGO_DE_ANULACION[codigo] ?? mensajeDelServidor;
}
