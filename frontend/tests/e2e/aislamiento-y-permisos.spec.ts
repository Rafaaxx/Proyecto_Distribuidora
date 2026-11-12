/**
 * Aislamiento entre organizaciones y permisos durante la demostración (change 28, D14). Spec
 * `sistema/aceptacion-etapa-1`, requisito «Aislamiento y permisos durante la demostración»,
 * escenarios «Usuario de otra organización» y «Acción no permitida». Cita INV-21, SEG-06, SEG-07,
 * ADR-056.
 *
 * Corre al final de la historia: la organización inicial ya tiene clientes, compras y ventas.
 */
import { randomUUID } from 'node:crypto'

import { ApiDeAceptacion, Consultas } from './apoyo/api'
import { abrirVista } from './apoyo/contextos'
import { expect, test } from './apoyo/fixtures'
import { SEGUNDA_ORGANIZACION } from './datos/escenario'
import { iniciarSesionEnAdmin } from './apoyo/sesion'

test.describe('Usuario de otra organización', () => {
  test('el administrador de la segunda organización no ve los clientes de la primera', async ({ browser, baseURL, vigilante }) => {
    const { page } = await abrirVista(browser, vigilante, 'PC', baseURL ?? '')
    await iniciarSesionEnAdmin(page, 'admin', SEGUNDA_ORGANIZACION)
    await page.goto('/admin/clientes')

    await expect(page.getByRole('heading', { name: 'Clientes' })).toBeVisible()
    await expect(page.getByText('Almacén Don Pedro')).toHaveCount(0)
    await expect(page.getByText('Kiosco La Esquina')).toHaveCount(0)
    await expect(page.getByRole('alert')).toHaveCount(0)
  })

  test('pedir por la API un cliente de la primera organización responde 404, no 403 (INV-21)', async ({
    browser,
    baseURL,
  }) => {
    const primera = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin')
    const clienteId = await new Consultas(primera).idDeCliente('C001')

    const segunda = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin', SEGUNDA_ORGANIZACION)
    expect(await segunda.estado(`/api/v1/clientes/${clienteId}`)).toBe(404)
    expect(await segunda.estado(`/api/v1/clientes/${clienteId}/saldo`)).toBe(404)
    // El propio cliente sigue existiendo para su organización.
    expect(await primera.estado(`/api/v1/clientes/${clienteId}`)).toBe(200)
  })
})

test.describe('Acción no permitida', () => {
  test('un vendedor no puede anular una compra por la API y nada cambia (SEG-06)', async ({ browser, baseURL }) => {
    const admin = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin')
    const compras = await admin.leer<{ items: { id: string; estado: string }[] }>('/api/v1/compras?limite=100')
    expect(compras.items.length).toBeGreaterThanOrEqual(2)
    const antes = compras.items.map((c) => `${c.id}:${c.estado}`).sort()

    const vendedor = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'vendedor')
    const compra = compras.items[0]
    expect(compra).toBeDefined()
    const respuesta = await vendedor.estado(`/api/v1/compras/${compra?.id ?? ''}/anulacion`, 'POST', {
      motivo_id: randomUUID(),
    })
    expect(respuesta).toBe(403)

    const despues = await admin.leer<{ items: { id: string; estado: string }[] }>('/api/v1/compras?limite=100')
    expect(despues.items.map((c) => `${c.id}:${c.estado}`).sort()).toEqual(antes)
  })
})
