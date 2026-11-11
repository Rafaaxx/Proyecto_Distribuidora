/**
 * Criterio 10 de `00` §9 (change 28, D14): rendición con diferencia auditada. Spec
 * `sistema/aceptacion-etapa-1`, escenario «Criterio 10 — rendición con diferencia auditada».
 * Cita RUT-05, RUT-06, STK-03, AUD-01, INV-04.
 *
 * El vendedor termina el día en el teléfono (entrega la jornada) y `admin` rinde la jornada desde
 * `/admin` contando la camioneta. Esperado según el sistema: 5 botellas de Vino A y 18 latas de
 * Cerveza B. Conteo: 4 botellas (falta 1) y 1 caja + 6 latas (coincide) -> UNA diferencia.
 */
import { ApiDeAceptacion, Consultas } from './apoyo/api'
import { abrirVista } from './apoyo/contextos'
import { expect, test } from './apoyo/fixtures'
import { iniciarSesionEnAdmin } from './apoyo/sesion'
import { abrirTelefono, cerrarTelefono, guardarTelefono, problemasDelTelefono, type Telefono } from './apoyo/telefono'

test.describe.configure({ mode: 'serial' })

test.describe('Criterio 10 — rendición con diferencia auditada', () => {
  let telefono: Telefono

  test.beforeAll(async ({ browser }, testInfo) => {
    telefono = await abrirTelefono(browser, testInfo.project.use.baseURL ?? '')
  })

  test.afterAll(async () => {
    await guardarTelefono(telefono)
    expect(problemasDelTelefono(telefono), 'el teléfono informó errores de seguridad o no manejados').toEqual([])
    await cerrarTelefono(telefono)
  })

  test('el vendedor termina el día en el teléfono y la entrega llega al servidor', async ({ browser, baseURL }) => {
    const { page } = telefono
    await page.getByRole('button', { name: 'Terminar el día', exact: true }).click()
    await expect(page.getByRole('heading', { name: '¿Terminar el día?' })).toBeVisible()
    await page.getByRole('dialog').getByRole('button', { name: 'Terminar el día' }).click()
    await expect(page.getByRole('heading', { name: '¿Terminar el día?' })).toHaveCount(0)

    const api = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin')
    await expect
      .poll(async () => {
        const abiertas = await api.leer<{ items: { id: string; ubicacion_nombre: string }[] }>(
          '/api/v1/stock/jornadas?estado=ABIERTA',
        )
        const id = abiertas.items.find((j) => j.ubicacion_nombre === 'Camioneta 1')?.id
        if (id === undefined) return false
        const detalle = await api.leer<{ entregada_en: string | null }>(`/api/v1/stock/jornadas/${id}`)
        return detalle.entregada_en !== null
      })
      .toBe(true)
  })

  test('el administrador rinde la jornada con una diferencia de una botella', async ({ browser, baseURL, vigilante }) => {
    const api = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin')
    const consultas = new Consultas(api)
    expect(await consultas.stockBase('Camioneta 1', 'VINO-A')).toBe(5)
    expect(await consultas.stockBase('Camioneta 1', 'CERV-B')).toBe(18)

    const jornadas = await api.leer<{ items: { id: string; ubicacion_nombre: string }[] }>(
      '/api/v1/stock/jornadas?estado=ABIERTA',
    )
    const jornada = jornadas.items.find((j) => j.ubicacion_nombre === 'Camioneta 1')
    expect(jornada, 'no hay jornada abierta en la Camioneta 1').toBeDefined()

    const { page } = await abrirVista(browser, vigilante, 'PC', baseURL ?? '')
    await iniciarSesionEnAdmin(page, 'admin')
    await page.goto(`/admin/stock/jornadas/${jornada?.id ?? ''}/rendicion`)
    await expect(page.getByRole('heading', { name: 'Rendición de Camioneta 1' })).toBeVisible()

    await page.getByLabel('Cajas de Vino A').fill('0')
    await page.getByLabel('Unidades de Vino A').fill('4')
    await page.getByLabel('Cajas de Cerveza B').fill('1')
    await page.getByLabel('Unidades de Cerveza B').fill('6')
    await page.getByLabel('Observación').fill('Falta una botella de Vino A')
    await page.getByRole('button', { name: 'Registrar rendición' }).click()

    await expect(page.getByRole('heading', { name: '¿Registrar la rendición con 1 diferencia?' })).toBeVisible()
    await page.getByRole('button', { name: 'Confirmar', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`/admin/stock/jornadas/${jornada?.id ?? ''}$`))
  })

  test('la diferencia queda como movimiento auditado y el stock coincide con el conteo', async ({ browser, baseURL }) => {
    const api = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin')
    const consultas = new Consultas(api)

    // STK-03: el movimiento DIFERENCIA_RENDICION corrige el stock al conteo (no se edita ni se borra).
    expect(await consultas.stockBase('Camioneta 1', 'VINO-A')).toBe(4)
    expect(await consultas.stockBase('Camioneta 1', 'CERV-B')).toBe(18)

    // La jornada pasó a rendición y quedó una sola.
    const enRendicion = await api.leer<{ items: { ubicacion_nombre: string; estado: string }[] }>(
      '/api/v1/stock/jornadas?estado=EN_RENDICION',
    )
    expect(enRendicion.items.filter((j) => j.ubicacion_nombre === 'Camioneta 1')).toHaveLength(1)

    // AUD-01: el reporte de rendiciones muestra la jornada con su diferencia.
    const reporte = await api.leer<{ jornadas: { filas: unknown[] } }>('/api/v1/reportes/rendiciones')
    expect(JSON.stringify(reporte.jornadas.filas)).toContain('Camioneta 1')
  })
})
