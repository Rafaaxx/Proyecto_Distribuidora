/**
 * El teléfono del vendedor a lo largo de los criterios 5 a 10 (change 28, D14, D15). Los criterios
 * son una historia en serie: las ventas hechas sin señal en el 5 y el 6 se envían recién en el 8,
 * así que la base local del teléfono (IndexedDB, sesión, PIN) tiene que sobrevivir de un archivo
 * de prueba al siguiente. Se guarda con `storageState({ indexedDB: true })` en un archivo del
 * directorio temporal y cada archivo abre un contexto nuevo a partir de él.
 *
 * Un contexto restaurado no trae el service worker: se vuelve a registrar con una visita CON
 * conexión (`registrarServiceWorker`) antes de cortar la red; recién ahí recargar sin señal sirve
 * la aplicación desde el caché (necesita el build de producción, no el servidor de desarrollo).
 */
import { existsSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { devices, expect, type Browser, type BrowserContext, type Page } from '@playwright/test'

import { PIN_DE_PRUEBA, type NombreDeUsuario } from '../datos/escenario'
import { Vigilante } from './fixtures'
import { iniciarSesionEnRuta } from './sesion'

const ARCHIVO_DE_ESTADO = path.join(os.tmpdir(), 'distribuidora-aceptacion-telefono.json')

export interface Telefono {
  context: BrowserContext
  page: Page
  vigilante: Vigilante
}

/**
 * El teléfono abierto en este proceso. Los criterios 5 a 8 son UN tramo sin señal: apenas el
 * teléfono arranca con conexión envía lo pendiente (SYN, `22b`: al empezar, al volver la señal),
 * así que no se puede cerrar y volver a abrir entre un archivo y otro sin enviar las ventas antes
 * de tiempo. Con un solo trabajador, los archivos corren en el mismo proceso y comparten esta
 * instancia; si no hay (la prueba se corre suelta, o el trabajador se reinició tras una falla),
 * se abre uno desde el estado guardado.
 */
let abierto: Telefono | null = null

/** Cierra el teléfono (y deja de compartirlo): el siguiente `abrirTelefono` parte del estado guardado. */
export async function cerrarTelefono(telefono: Telefono): Promise<void> {
  if (abierto === telefono) abierto = null
  await telefono.context.close()
}

/** Olvida el teléfono guardado: el criterio 4 (el vendedor abre la jornada) arranca con un dispositivo nuevo. */
export function olvidarTelefono(): void {
  rmSync(ARCHIVO_DE_ESTADO, { force: true })
}

export async function guardarTelefono(telefono: Telefono): Promise<void> {
  await telefono.context.storageState({ path: ARCHIVO_DE_ESTADO, indexedDB: true })
}

/**
 * Abre el teléfono: con el estado guardado (recarga y desbloquea con el PIN) o, si no hay,
 * como dispositivo nuevo (inicia sesión y define el PIN). Una jornada es del usuario Y del
 * dispositivo que la abrió (ADR-005; `GET /stock/jornadas/actual`): el criterio 4 abre la jornada
 * en este teléfono y lo guarda, y los criterios 5 a 10 siguen con el mismo aparato.
 */
export async function abrirTelefono(
  browser: Browser,
  baseURL: string,
  usuario: NombreDeUsuario = 'vendedor',
): Promise<Telefono> {
  if (abierto !== null && !abierto.page.isClosed()) return abierto
  const restaurar = existsSync(ARCHIVO_DE_ESTADO)
  const context = await browser.newContext({
    ...devices['Pixel 7'],
    baseURL,
    ignoreHTTPSErrors: true,
    locale: 'es-AR',
    timezoneId: 'America/Argentina/Mendoza',
    ...(restaurar ? { storageState: ARCHIVO_DE_ESTADO } : {}),
  })
  const page = await context.newPage()
  const vigilante = new Vigilante()
  vigilante.vigilar(page)
  const telefono = { context, page, vigilante }

  if (restaurar) {
    await page.goto('/ruta')
    await desbloquearConPin(page)
  } else {
    await iniciarSesionEnRuta(page, usuario)
  }
  await registrarServiceWorker(page)
  abierto = telefono
  return telefono
}

/** El teléfono pide el PIN al arrancar o recargar; se escribe y se espera a que desaparezca el pedido. */
export async function desbloquearConPin(page: Page): Promise<void> {
  const pedido = page.getByRole('heading', { name: 'Ingresá tu PIN' })
  const inicio = page.getByRole('heading', { name: /^(Área de ruta|Hola, )/ })
  await pedido.or(inicio).waitFor()
  if (await pedido.isVisible()) {
    await page.getByLabel('PIN', { exact: true }).fill(PIN_DE_PRUEBA)
    await page.getByRole('button', { name: 'Desbloquear' }).click()
    // Recargar deja al usuario en la pantalla en que estaba (no siempre el inicio).
    await expect(pedido).toHaveCount(0)
  }
}

/** Espera al service worker y recarga una vez, para que la página quede controlada por él. */
async function registrarServiceWorker(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
  })
  await page.reload()
  await desbloquearConPin(page)
}

/** Corta la red del teléfono y recarga la aplicación: tiene que abrir con lo que guardó. */
export async function recargarSinSenal(telefono: Telefono): Promise<void> {
  await telefono.context.setOffline(true)
  await telefono.page.reload()
  await desbloquearConPin(telefono.page)
  await expect(telefono.page.getByText('Sin conexión', { exact: true }).first()).toBeVisible()
}

export async function volverLaSenal(telefono: Telefono): Promise<void> {
  await telefono.context.setOffline(false)
  await expect(telefono.page.getByText('Con conexión', { exact: true }).first()).toBeVisible()
}

/** Al terminar el archivo: el accesorio común también vigila la página compartida. */
export function problemasDelTelefono(telefono: Telefono): string[] {
  return telefono.vigilante.problemas()
}
