/**
 * Criterio 3 de `00` §9 (change 28, D14): se carga un nuevo costo, se genera una nueva versión de
 * lista con margen y redondeo, y las ventas anteriores conservan su precio. Spec
 * `sistema/aceptacion-etapa-1`, escenario «Criterio 3 — nueva versión de lista sin alterar ventas
 * anteriores». Cita INV-10, INV-11, PRC-14, PRC-17, PRC-22, PRC-23.
 *
 * Quién hace qué (`01` §19): `ges01` (Administración) crea la lista y carga los costos; publicar
 * (`PUBLICAR_LISTAS`) y vender (`VENDER`) los hace `admin`, porque `Administración` no tiene esos
 * permisos.
 *
 * Cuentas (markup 30% sobre el costo de la presentación de referencia, redondeo hacia arriba a
 * múltiplos de $100; costos informados por el criterio 2):
 *   Versión 1: Vino A caja x6 a $6.600 -> 8.580 -> $8.600; Cerveza B caja x12 (lata $1.600 x 12 =
 *              $19.200) -> 24.960 -> $25.000.
 *   Versión 2: Vino A caja x6 a $7.200 -> 9.360 -> $9.400; Cerveza B no cambia.
 */
import { ApiDeAceptacion, Consultas } from './apoyo/api'
import { expect, test } from './apoyo/fixtures'
import { iniciarSesionEnAdmin } from './apoyo/sesion'

const LISTA = 'Lista general'

test.describe.configure({ mode: 'serial' })

test.describe('Criterio 3 — nueva versión de lista sin alterar ventas anteriores', () => {
  test('se crea la lista con su regla de margen y su redondeo', async ({ page }) => {
    await iniciarSesionEnAdmin(page, 'ges01')
    await page.goto('/admin/precios/nueva')

    await page.getByLabel('Nombre').fill(LISTA)
    await page.getByLabel('Múltiplo de redondeo').fill('100')
    await page.getByLabel('Dirección del redondeo').selectOption({ value: 'ARRIBA' })
    await page.getByRole('button', { name: 'Crear lista' }).click()

    // Al crearla, la pantalla lleva al detalle de la lista.
    await expect(page.getByRole('heading', { name: LISTA })).toBeVisible()
    await page.getByRole('button', { name: 'Nueva regla' }).click()
    await page.getByLabel('Porcentaje').fill('30')
    await page.getByRole('button', { name: 'Guardar regla' }).click()

    await expect(page.getByRole('table', { name: 'Reglas de margen' })).toContainText('30')
  })

  test('el administrador la deja como lista predeterminada', async ({ page }) => {
    await iniciarSesionEnAdmin(page, 'admin')
    await page.goto('/admin/configuracion/lista-predeterminada')

    await page.getByLabel('Lista predeterminada').selectOption({ label: LISTA })
    await page.getByRole('button', { name: 'Guardar lista predeterminada' }).click()

    await expect(page.getByLabel('Lista predeterminada')).toHaveValue(/.+/)
  })

  test('se genera y se publica la versión 1 con los precios esperados', async ({ page }) => {
    await iniciarSesionEnAdmin(page, 'admin')
    await page.goto('/admin/precios')
    await page.getByRole('link', { name: LISTA }).click()
    await page.getByRole('link', { name: 'Borrador' }).click()

    await page.getByRole('button', { name: 'Generar borrador' }).click()
    const precios = page.getByRole('table', { name: 'Precios del borrador' })
    await expect(precios).toContainText('8.600,00')
    await expect(precios).toContainText('25.000,00')

    await page.getByRole('button', { name: 'Publicar' }).click()
    await page.getByRole('button', { name: 'Confirmar publicación' }).click()
    await expect(page.locator('dd', { hasText: /^Versión 1$/ })).toBeVisible()
  })

  test('se confirma una venta con la versión 1', async ({ page }) => {
    await iniciarSesionEnAdmin(page, 'admin')
    await page.goto('/admin/ventas/nueva')

    await page.getByLabel('Cliente', { exact: true }).selectOption({ label: 'Almacén Don Pedro' })
    await page.getByLabel('Ubicación', { exact: true }).selectOption({ label: 'Depósito central' })
    await page.getByLabel('Buscar producto').fill('Vino A')
    await page.getByRole('button', { name: 'Agregar Vino A' }).click()
    await page.getByLabel('Cajas de Vino A').fill('1')

    await expect(page.getByTestId('total-de-la-venta')).toContainText('8.600,00')
    await page.getByRole('button', { name: 'Confirmar venta' }).click()
    await expect(page.getByRole('heading', { name: 'Venta registrada' })).toBeVisible()
  })

  test('se carga un costo nuevo para el Vino A', async ({ page, browser, baseURL }) => {
    await iniciarSesionEnAdmin(page, 'ges01')
    await page.goto('/admin/proveedores')
    await page.getByRole('row', { name: /Bodega del Valle/ }).getByRole('link').first().click()
    await page.getByRole('link', { name: /Cargar costos/ }).click()

    await page.getByLabel('Producto').selectOption({ label: 'Vino A' })
    await page.getByLabel('Presentación').selectOption({ label: 'Caja x6' })
    await page.getByRole('textbox', { name: 'Valor pagado' }).fill('7200')
    await page.getByRole('button', { name: 'Cargar costos' }).click()

    // El costo informado vigente del Vino A pasó a $7.200 la caja (CST-02: $1.200 por botella).
    const api = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'ges01')
    const productoId = await new Consultas(api).idDeProducto('VINO-A')
    await expect
      .poll(async () => JSON.stringify(await api.leer(`/api/v1/costos/productos/${productoId}/vigente`)))
      .toContain('1200.000000')
  })

  test('se genera y se publica la versión 2 con el costo nuevo', async ({ page }) => {
    await iniciarSesionEnAdmin(page, 'admin')
    await page.goto('/admin/precios')
    await page.getByRole('link', { name: LISTA }).click()
    await page.getByRole('link', { name: 'Borrador' }).click()
    await page.getByRole('button', { name: 'Generar borrador' }).click()
    const precios = page.getByRole('table', { name: 'Precios del borrador' })
    await expect(precios).toContainText('9.400,00')
    await expect(precios).toContainText('25.000,00') // la Cerveza B no cambió

    await page.getByRole('button', { name: 'Publicar' }).click()
    await page.getByRole('button', { name: 'Confirmar publicación' }).click()
    await expect(page.locator('dd', { hasText: /^Versión 2$/ })).toBeVisible()
  })

  test('la venta anterior conserva el precio de la versión 1', async ({ page, browser, baseURL }) => {
    await iniciarSesionEnAdmin(page, 'admin')
    await page.goto('/admin/ventas')
    await page.getByRole('link', { name: /Almacén Don Pedro|Ver|Detalle/ }).first().click()

    await expect(page.getByText('8.600,00').first()).toBeVisible()
    await expect(page.getByText('9.400,00')).toHaveCount(0)

    // La lista vigente ya ofrece el precio nuevo: la versión 2 existe y rige.
    const api = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin')
    const listas = await api.leer<{ items: { id: string; nombre: string }[] }>('/api/v1/precios/listas')
    const lista = listas.items.find((l) => l.nombre === LISTA)
    expect(lista).toBeDefined()
    const vigente = await api.leer<{ numero: number }>(`/api/v1/precios/listas/${lista?.id ?? ''}/vigente`)
    expect(vigente.numero).toBe(2)
  })
})
