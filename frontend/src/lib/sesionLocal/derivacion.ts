/**
 * Derivación del PIN con Web Crypto (change 21, `design.md` D8, D13; `02` §12.4; ADR-011, ADR-019).
 *
 * PBKDF2-HMAC-SHA256 con la sal y las iteraciones que se pasan, salida en hexadecimal: el mismo
 * resultado que `verificar_pin_autorizacion` del servidor para el mismo PIN, sal e iteraciones
 * (vector compartido `shared/fixtures/pin/derivacion.json`). El PIN nunca se guarda ni se envía:
 * solo se guarda la derivación.
 */

const BITS_DE_SALIDA = 256;

function desdeHexadecimal(hex: string): Uint8Array<ArrayBuffer> {
  if (hex.length % 2 !== 0 || /[^0-9a-fA-F]/.test(hex)) {
    throw new Error("La sal debe ser una cadena hexadecimal de largo par");
  }
  const bytes = new Uint8Array(new ArrayBuffer(hex.length / 2));
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

function aHexadecimal(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}

/** Deriva `pin` con PBKDF2-SHA256 y devuelve el hash en hexadecimal. */
export async function derivarPin(
  pin: string,
  salHex: string,
  iteraciones: number,
): Promise<string> {
  const material = await globalThis.crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(pin),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bits = await globalThis.crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      hash: "SHA-256",
      salt: desdeHexadecimal(salHex),
      iterations: iteraciones,
    },
    material,
    BITS_DE_SALIDA,
  );
  return aHexadecimal(new Uint8Array(bits));
}

/** Compara dos cadenas sin cortar en la primera diferencia (no filtra por tiempo dónde difieren). */
export function compararEnTiempoConstante(a: string, b: string): boolean {
  const largo = Math.max(a.length, b.length);
  let diferencia = a.length ^ b.length;
  for (let i = 0; i < largo; i += 1) {
    diferencia |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diferencia === 0;
}

/** Si `pin` deriva a `hashEsperado` con esa sal e iteraciones. */
export async function verificarPin(
  pin: string,
  salHex: string,
  iteraciones: number,
  hashEsperado: string,
): Promise<boolean> {
  const derivado = await derivarPin(pin, salHex, iteraciones);
  return compararEnTiempoConstante(derivado, hashEsperado);
}
