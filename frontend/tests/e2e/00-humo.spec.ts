/**
 * Prueba de humo del entorno de aceptación (change 28, tarea 6.2): inicia sesión como `admin` y
 * comprueba que el accesorio común falla ante una violación de CSP. Spec `sistema/aceptacion-etapa-1`:
 * «La suite no tolera errores de seguridad del navegador», escenario «Violación de CSP».
 */
import type { Page } from '@playwright/test'

import { expect, test } from './apoyo/fixtures'
import { iniciarSesionEnAdmin } from './apoyo/sesion'

/** Con la política real de Caddy (`script-src 'self'`), un script de otro origen se bloquea. */
async function cargarUnScriptDeOtroOrigen(page: Page): Promise<void> {
  await page.goto('/admin/login')
  await page.evaluate(() => {
    const script = document.createElement('script')
    script.src = 'https://origen-no-permitido.invalid/script.js'
    document.head.appendChild(script)
  })
}

test('el administrador inicia sesión y ve el inicio de /admin', async ({ page }) => {
  await iniciarSesionEnAdmin(page, 'admin')

  await expect(page.getByRole('heading', { name: 'Para revisar' })).toBeVisible()
})

test('una violación de CSP se registra nombrando la directiva violada', async ({ page, vigilante }) => {
  await cargarUnScriptDeOtroOrigen(page)

  await expect.poll(() => vigilante.violacionesDeCsp.length).toBeGreaterThan(0)
  expect(vigilante.violacionesDeCsp[0]).toContain("script-src 'self'")
  vigilante.descartarViolaciones() // esperada: que no falle este test por ella
})

// Sin descartarla, la violación hace fallar la prueba: `test.fail` exige que falle.
test.fail('una violación de CSP hace fallar la prueba que la provoca', async ({ page, vigilante }) => {
  await cargarUnScriptDeOtroOrigen(page)
  await expect.poll(() => vigilante.violacionesDeCsp.length).toBeGreaterThan(0)
})

test('un error no manejado de la página hace fallar la prueba que lo provoca', async ({ page, vigilante }) => {
  await page.setContent('<p>x</p>')
  await page.evaluate(() => {
    setTimeout(() => {
      throw new Error('error de prueba no manejado')
    }, 0)
  })

  await expect.poll(() => vigilante.erroresDePagina.length).toBeGreaterThan(0)
  expect(vigilante.erroresDePagina[0]).toContain('error de prueba no manejado')
  vigilante.descartarErrores()
})
