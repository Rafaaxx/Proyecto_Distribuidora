import { describe, expect, it } from "vitest";
import Decimal from "decimal.js";
import { debePreguntarPorDinero, efectoEnCuenta } from "../../../../src/domain/ventas/anulacion";

describe("dominio ventas/anulacion (triangulacion)", () => {
  it("efectoEnCuenta cobra mayor que total segun fixture", () => {
    const r = efectoEnCuenta("80000.00", "100000.00", true);
    expect(r.movimientos.map((m) => m.tipo)).toEqual(["ANULACION_VENTA", "ANULACION_COBRANZA"]);
    expect(r.movimientos[1].importe).toBe("100000.00");
    expect(r.saldoFinalRelativo).toBe("0.00");
  });

  it("sin cobro saldo negativo total", () => {
    const r = efectoEnCuenta("50000.00", null, null);
    expect(r.movimientos.length).toBe(1);
    expect(r.saldoFinalRelativo).toBe("-50000.00");
  });

  it("sin devolucion con cobro parcial queda a favor", () => {
    const r = efectoEnCuenta("150000.00", "20000.00", false);
    expect(r.movimientos.length).toBe(1);
    expect(r.saldoFinalRelativo).toBe("-20000.00");
  });

  it("debePreguntarPorDinero solo si tiene cobro", () => {
    expect(debePreguntarPorDinero(true)).toBe(true);
    expect(debePreguntarPorDinero(false)).toBe(false);
  });

  it("usa decimal.js sin convertir a number", () => {
    const r = efectoEnCuenta(new Decimal("80000.10"), new Decimal("20000.05"), true);
    expect(r.movimientos[0].importe).toBe("80000.10");
    expect(r.movimientos[1].importe).toBe("20000.05");
    expect(r.saldoFinalRelativo).toBe("0.00");
  });
});
