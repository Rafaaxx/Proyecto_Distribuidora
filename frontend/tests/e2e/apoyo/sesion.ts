import type { Page } from '@playwright/test'

import { CONTRASENA, ORGANIZACION, PIN_DE_PRUEBA, type NombreDeUsuario } from '../datos/escenario'

/** Inicia sesión en `/admin` con un usuario de la siembra y espera el inicio. */
export async function iniciarSesionEnAdmin(
  page: Page,
  usuario: NombreDeUsuario,
  organizacion: string = ORGANIZACION,
): Promise<void> {
  await page.goto('/admin/login')
  await page.getByLabel('Organización').fill(organizacion)
  await page.getByLabel('Usuario').fill(usuario)
  await page.getByLabel('Contraseña').fill(CONTRASENA)
  await page.getByRole('button', { name: 'Iniciar sesión' }).click()
  await page.waitForURL('**/admin/inicio')
}

/** Inicia sesión en `/ruta` (el teléfono del vendedor) y espera el inicio de la ruta. */
export async function iniciarSesionEnRuta(
  page: Page,
  usuario: NombreDeUsuario,
  organizacion: string = ORGANIZACION,
): Promise<void> {
  await page.goto('/ruta')
  await page.getByLabel('Organización').fill(organizacion)
  await page.getByLabel('Usuario').fill(usuario)
  await page.getByLabel('Contraseña').fill(CONTRASENA)
  await page.getByRole('button', { name: 'Iniciar sesión' }).click()

  // En un dispositivo nuevo, la primera vez la aplicación pide definir el PIN de 6 dígitos con el
  // que se abre también sin señal.
  // Sin jornada abierta todavía no hay datos descargados y el título es «Área de ruta».
  const inicio = page.getByRole('heading', { name: /^(Área de ruta|Hola, )/ })
  const definirPin = page.getByRole('heading', { name: 'Definí tu PIN' })
  await inicio.or(definirPin).waitFor()
  if (await definirPin.isVisible()) {
    await page.getByLabel('PIN', { exact: true }).fill(PIN_DE_PRUEBA)
    await page.getByLabel('Repetí el PIN').fill(PIN_DE_PRUEBA)
    await page.getByRole('button', { name: 'Guardar PIN' }).click()
    await inicio.waitFor()
  }
}
