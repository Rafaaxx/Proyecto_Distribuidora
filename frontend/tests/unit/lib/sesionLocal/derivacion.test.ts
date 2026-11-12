/**
 * Change 21, tarea 4.2 (`design.md` D8, D13; `02` §12.4): la derivación PBKDF2-SHA256 con Web Crypto
 * del PIN da el mismo hash que el servidor con el vector compartido
 * `shared/fixtures/pin/derivacion.json` (el mismo que verifica Python en
 * `backend/tests/unit/test_pin_vector_compartido.py`). Reglas: ADR-011, ADR-019, SEG-05.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  compararEnTiempoConstante,
  derivarPin,
  verificarPin,
} from "../../../../src/lib/sesionLocal/derivacion";

interface CasoDeVector {
  id: string;
  pin: string;
  sal_hex: string;
  iteraciones: number;
  hash_hex: string;
}

const aqui = dirname(fileURLToPath(import.meta.url));
const RUTA_VECTOR = join(
  aqui,
  "..",
  "..",
  "..",
  "..",
  "..",
  "shared",
  "fixtures",
  "pin",
  "derivacion.json",
);
const casos = (
  JSON.parse(readFileSync(RUTA_VECTOR, "utf-8")) as { casos: CasoDeVector[] }
).casos;

if (casos.length < 2) {
  throw new Error(
    "El vector compartido de PIN necesita al menos dos casos para triangular",
  );
}

describe("derivación del PIN con Web Crypto (vector compartido con el servidor)", () => {
  it.each(casos.map((caso) => [caso.id, caso] as const))(
    "%s: da el hash del servidor",
    async (_id, caso) => {
      const hash = await derivarPin(caso.pin, caso.sal_hex, caso.iteraciones);

      expect(hash).toBe(caso.hash_hex);
    },
  );

  it.each(casos.map((caso) => [caso.id, caso] as const))(
    "%s: verifica el PIN y rechaza otro",
    async (_id, caso) => {
      expect(
        await verificarPin(
          caso.pin,
          caso.sal_hex,
          caso.iteraciones,
          caso.hash_hex,
        ),
      ).toBe(true);
      expect(
        await verificarPin(
          "000000",
          caso.sal_hex,
          caso.iteraciones,
          caso.hash_hex,
        ),
      ).toBe(false);
    },
  );

  it("con otra sal el hash cambia", async () => {
    const [caso] = casos;
    if (caso === undefined) throw new Error("vector vacío");
    const otraSal = caso.sal_hex.replace(/^../, (par) =>
      par === "ff" ? "00" : "ff",
    );

    expect(await derivarPin(caso.pin, otraSal, caso.iteraciones)).not.toBe(
      caso.hash_hex,
    );
  });
});

describe("comparación en tiempo constante", () => {
  it("iguales -> verdadero; distinto contenido o largo -> falso", () => {
    expect(compararEnTiempoConstante("abc123", "abc123")).toBe(true);
    expect(compararEnTiempoConstante("abc123", "abc124")).toBe(false);
    expect(compararEnTiempoConstante("abc", "abc123")).toBe(false);
    expect(compararEnTiempoConstante("", "")).toBe(true);
  });
});
