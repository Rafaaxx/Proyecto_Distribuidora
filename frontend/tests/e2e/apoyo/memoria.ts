/**
 * Lo que un criterio le deja al siguiente (change 28, D14): importes y cantidades observados en
 * pantalla o por la API. Vive en un archivo del directorio temporal porque cada archivo de prueba
 * corre en su propio proceso. El criterio 5 lo reinicia.
 */
import { readFileSync, rmSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const ARCHIVO = path.join(os.tmpdir(), 'distribuidora-aceptacion-memoria.json')

export interface MemoriaDeLaSuite {
  saldoC001Antes?: string
  saldoC002Antes?: string
  costoVinoAntes?: string
  costoCervezaAntes?: string
  numeroVenta5?: string
  totalVenta5?: string
  cobradoVenta5?: string
  numeroVenta6?: string
  totalVenta6?: string
  stockVinoCamioneta?: number
  stockCervezaCamioneta?: number
}

export function leerMemoria(): MemoriaDeLaSuite {
  try {
    return JSON.parse(readFileSync(ARCHIVO, 'utf-8')) as MemoriaDeLaSuite
  } catch {
    return {}
  }
}

export function recordar(cambios: MemoriaDeLaSuite): void {
  writeFileSync(ARCHIVO, JSON.stringify({ ...leerMemoria(), ...cambios }))
}

export function olvidarMemoria(): void {
  rmSync(ARCHIVO, { force: true })
}

/** Un dato que un criterio anterior tenía que dejar: si falta, se dice cuál. */
export function exigir<K extends keyof MemoriaDeLaSuite>(clave: K): NonNullable<MemoriaDeLaSuite[K]> {
  const valor = leerMemoria()[clave]
  if (valor === undefined) throw new Error(`El criterio anterior no dejó «${clave}»`)
  return valor as NonNullable<MemoriaDeLaSuite[K]>
}

/** Texto de dinero mostrado por la aplicación («$ 125.400,00») a decimal de la API («125400.00»). */
export function importeDeTexto(texto: string): string {
  const m = /(\d[\d.]*,\d{2})/.exec(texto)
  if (m === null) throw new Error(`No hay un importe en «${texto}»`)
  return (m[1] ?? '').replace(/\./g, '').replace(',', '.')
}
