/**
 * Criterio 6 de `00` §9 (change 28, D14): exceso de crédito sin conexión. Spec
 * `sistema/aceptacion-etapa-1`, escenario «Criterio 6 — exceso de crédito sin conexión». Cita
 * INV-17, CRE-04, CRE-05, CRE-06.
 *
 * Kiosco La Esquina (C002) debe $8.000 desde la importación; `ges01` le puso un límite de $10.000
 * y el teléfono lo bajó con señal (en el criterio 5, antes de cortarla). Sin señal, una venta de 1 caja de Cerveza B ($25.000) lo deja
 * unos $23.000 sobre el límite: supera el límite pero entra en la tolerancia sin conexión de la
 * organización ($50.000, política AUTORIZAR). Se resuelve según esa política: se confirma por la
 * tolerancia, sin pedir autorizador y sin que ninguna regla de negocio la rechace.
 */
import { expect, test } from './apoyo/fixtures'
import { importeDeTexto, recordar } from './apoyo/memoria'
import {
  abrirTelefono,
  guardarTelefono,
  problemasDelTelefono,
  type Telefono,
} from './apoyo/telefono'
import { abrirVender, cargarProducto } from './apoyo/ventaEnRuta'

test.describe.configure({ mode: 'serial' })

test.describe('Criterio 6 — exceso de crédito sin conexión', () => {
  let telefono: Telefono

  test.beforeAll(async ({ browser }, testInfo) => {
    telefono = await abrirTelefono(browser, testInfo.project.use.baseURL ?? '')
  })

  test.afterAll(async () => {
    await guardarTelefono(telefono)
    expect(problemasDelTelefono(telefono), 'el teléfono informó errores de seguridad o no manejados').toEqual([])
  })

  test('el teléfono, sin señal, ya tiene el límite de crédito del cliente', async () => {
    // El límite lo puso la administración y el teléfono lo bajó ANTES de cortar la señal (criterio
    // 5): con conexión, apenas arranca el teléfono enviaría las ventas pendientes.
    const { page } = telefono
    await page.getByRole('link', { name: 'Clientes', exact: true }).first().click()
    await page.getByRole('link', { name: 'Kiosco La Esquina' }).click()
    await expect(page.getByText('Límite de crédito')).toBeVisible()
    await expect(page.getByText('$ 10.000,00', { exact: true })).toBeVisible()
    await page.getByRole('link', { name: 'Inicio', exact: true }).first().click()
  })

  test('sin señal, la segunda venta supera el límite y se resuelve por la política configurada', async () => {
    const { page } = telefono
    await abrirVender(page, 'Kiosco La Esquina')
    await cargarProducto(page, 'Cerveza B', { cajas: 1 })
    const total = importeDeTexto(await page.getByTestId('total-de-la-venta').innerText())
    await page.getByRole('button', { name: 'Siguiente' }).click()

    // CRE-04: el panel del teléfono evalúa el crédito con los datos locales y la tolerancia
    // sin conexión; no hay que aceptar nada ni elegir un supervisor.
    const panel = page.getByTestId('panel-de-credito')
    await expect(panel).toContainText('se confirma por la tolerancia sin conexión')
    await expect(page.getByTestId('bloqueos')).toHaveCount(0)
    await expect(page.getByLabel('Supervisor que autoriza el crédito')).toHaveCount(0)

    await page.getByRole('button', { name: 'Confirmar venta' }).click()
    await expect(page).toHaveURL(/\/ruta\/ventas\/[0-9a-f-]{36}$/)
    await expect(page.getByText('Sin enviar', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Kiosco La Esquina')).toBeVisible()

    const numero = (await page.getByRole('heading', { name: /^Venta / }).innerText()).replace('Venta ', '').trim()
    recordar({ numeroVenta6: numero, totalVenta6: total })
    await expect(page.getByRole('link', { name: '2 sin enviar' })).toBeVisible()
  })
})
