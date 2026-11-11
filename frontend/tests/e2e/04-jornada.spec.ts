/**
 * Criterio 4 de `00` §9 (change 28, D14): se transfiere mercadería al vehículo y el vendedor toma
 * la ubicación y abre la jornada. Spec `sistema/aceptacion-etapa-1`, escenario «Criterio 4 —
 * transferencia al vehículo y apertura de jornada». Cita INV-15, INV-16, CAT-08.
 *
 * `ges01` (PC) transfiere del Depósito central a la Camioneta 1; `vendedor` (teléfono) abre la
 * jornada en la Camioneta 1.
 *   Vino A:    13 cajas + 2 unidades = 80 botellas (en el depósito quedan 91 - 6 de la venta del
 *              criterio 3 - 80 = 5)
 *   Cerveza B: 10 cajas de 12 = 120 latas (queda 131 - 120 = 11 en el depósito)
 * Es todo lo que hace falta para el criterio 5: la regla de volumen es «20 cajas equivalentes» y,
 * con la jornada abierta, la administración ya no puede mover stock de la camioneta (INV-15:
 * solo quien la tiene o quien puede liberarla), así que la carga tiene que estar hecha antes.
 */
import { ApiDeAceptacion, Consultas } from './apoyo/api'
import { abrirVista } from './apoyo/contextos'
import { expect, test } from './apoyo/fixtures'
import { iniciarSesionEnAdmin } from './apoyo/sesion'
import { abrirTelefono, cerrarTelefono, guardarTelefono, olvidarTelefono, problemasDelTelefono } from './apoyo/telefono'

test.describe.configure({ mode: 'serial' })

test.describe('Criterio 4 — transferencia al vehículo y apertura de jornada', () => {
  test('la administración transfiere mercadería del depósito a la camioneta (vista de PC)', async ({
    browser,
    baseURL,
    vigilante,
  }) => {
    const { page } = await abrirVista(browser, vigilante, 'PC', baseURL ?? '')
    await iniciarSesionEnAdmin(page, 'ges01')
    await page.goto('/admin/stock/transferencias/nueva')

    await page.getByLabel('Origen').selectOption({ label: 'Depósito central' })
    await page.getByLabel('Destino').selectOption({ label: 'Camioneta 1' })
    const linea1 = page.getByRole('group', { name: 'Línea 1' })
    await linea1.getByLabel('Producto').selectOption({ label: 'VINO-A · Vino A' })
    await linea1.getByLabel('Caja x6').fill('13')
    await linea1.getByLabel('Unidades').fill('2')
    await page.getByRole('button', { name: 'Agregar línea' }).click()
    const linea2 = page.getByRole('group', { name: 'Línea 2' })
    await linea2.getByLabel('Producto').selectOption({ label: 'CERV-B · Cerveza B' })
    await linea2.getByLabel('Caja x12').fill('10')
    await page.getByRole('button', { name: 'Registrar transferencia' }).click()

    await expect(page).toHaveURL(/\/admin\/stock\/transferencias\/[0-9a-f-]{36}$/)
  })

  test('el stock quedó repartido entre el depósito y el vehículo', async ({ browser, baseURL }) => {
    const consultas = new Consultas(await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'ges01'))

    expect(await consultas.stockBase('Camioneta 1', 'VINO-A')).toBe(80)
    expect(await consultas.stockBase('Camioneta 1', 'CERV-B')).toBe(120)
    expect(await consultas.stockBase('Depósito central', 'VINO-A')).toBe(5)
    expect(await consultas.stockBase('Depósito central', 'CERV-B')).toBe(11)
  })

  test('el vendedor toma la camioneta, abre la jornada y ve su stock en el teléfono', async ({
    browser,
    baseURL,
  }) => {
    // Este teléfono queda guardado: la jornada es del dispositivo que la abre (ADR-005) y los
    // criterios 5 a 10 siguen con él.
    olvidarTelefono()
    const telefono = await abrirTelefono(browser, baseURL ?? '')
    const { page } = telefono
    await page.getByRole('link', { name: 'Abrir jornada' }).click()

    await page.getByLabel('Ubicación').selectOption({ label: 'Camioneta 1' })
    await page.getByRole('button', { name: 'Abrir jornada' }).click()

    await expect(page.getByText('Jornada abierta en Camioneta 1')).toBeVisible()

    // Con la jornada abierta, el teléfono descargó los datos y muestra el stock del vehículo.
    await page.getByRole('link', { name: 'Stock', exact: true }).first().click()
    await expect(page.getByText('Vino A')).toBeVisible()
    await expect(page.getByText('Cerveza B')).toBeVisible()

    await guardarTelefono(telefono)
    expect(problemasDelTelefono(telefono), 'el teléfono informó errores de seguridad o no manejados').toEqual([])
    await cerrarTelefono(telefono)
  })

  test('nadie más puede tomar la camioneta mientras la jornada está abierta', async ({ browser, baseURL }) => {
    // INV-15: una ubicación con la jornada tomada no se ofrece a otro vendedor.
    const api = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'vendedor2')
    const ubicaciones = await api.leer<{ items: { nombre: string; jornada: { estado: string } | null }[] }>(
      '/api/v1/stock/ubicaciones',
    )
    expect(ubicaciones.items.find((u) => u.nombre === 'Camioneta 1')?.jornada?.estado).toBe('ABIERTA')
    // Y si intenta abrir otra jornada sobre ella, el servidor la rechaza (INV-15).
    const ubicacionId = await new Consultas(api).idDeUbicacion('Camioneta 1')
    expect(await api.estado('/api/v1/stock/jornadas', 'POST', { ubicacion_id: ubicacionId })).toBe(409)
  })
})
