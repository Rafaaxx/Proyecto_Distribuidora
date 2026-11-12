/**
 * Criterio 5 de `00` §9 (change 28, D14, D15): venta sin conexión con descuentos y cobro parcial.
 * Spec `sistema/aceptacion-etapa-1`, escenario «Criterio 5 — venta sin conexión con descuentos y
 * cobro parcial». Cita INV-08, INV-17, DSC-03, DSC-06, VTA-06.
 *
 * La camioneta ya tiene lo necesario desde el criterio 4 (la regla de volumen es «20 cajas
 * equivalentes» y, con la jornada abierta, la administración no puede cargarla más):
 *   Vino A 80 botellas (13 cajas x6 + 2), Cerveza B 120 latas (10 cajas x12).
 * La venta a Almacén Don Pedro, con el teléfono sin señal:
 *   Vino A 12 cajas + 3 botellas (12,5 cajas equivalentes) + Cerveza B 8 cajas + 6 latas (8,5)
 *   = 21 cajas equivalentes >= 20: la regla de volumen da 5%; encima, 5% de descuento manual
 *   general (el tope del vendedor es 10%: no pide autorización).
 *   Cobro en el acto: $10.000 en efectivo + $5.000 por transferencia; el resto queda en cuenta.
 */
import { ApiDeAceptacion, Consultas } from './apoyo/api'
import { abrirVista } from './apoyo/contextos'
import { expect, test } from './apoyo/fixtures'
import { importeDeTexto, olvidarMemoria, recordar } from './apoyo/memoria'
import { iniciarSesionEnAdmin } from './apoyo/sesion'
import {
  abrirTelefono,
  guardarTelefono,
  problemasDelTelefono,
  recargarSinSenal,
  type Telefono,
} from './apoyo/telefono'
import { abrirVender, cargarProducto, cobrarCon } from './apoyo/ventaEnRuta'

test.describe.configure({ mode: 'serial' })

test.describe('Criterio 5 — venta sin conexión con descuentos y cobro parcial', () => {
  let telefono: Telefono

  test.beforeAll(async ({ browser }, testInfo) => {
    olvidarMemoria()
    telefono = await abrirTelefono(browser, testInfo.project.use.baseURL ?? '')
  })

  test.afterAll(async () => {
    await guardarTelefono(telefono)
    expect(problemasDelTelefono(telefono), 'el teléfono informó errores de seguridad o no manejados').toEqual([])
  })

  test('antes de salir: el cliente tiene su límite de crédito, la camioneta lo cargado y el teléfono está al día', async ({
    browser,
    baseURL,
    vigilante,
  }) => {
    // Antes de salir (criterio 6): `ges01` le pone a Kiosco La Esquina (C002) un límite de crédito
    // de $10.000. Tiene que bajarse con señal: con conexión, apenas arranca el teléfono envía
    // lo pendiente, así que desde la primera venta el teléfono queda sin señal hasta el criterio 8.
    const apiGestion = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'ges01')
    const clienteId = await new Consultas(apiGestion).idDeCliente('C002')
    const { page: paginaDeGestion } = await abrirVista(browser, vigilante, 'PC', baseURL ?? '')
    await iniciarSesionEnAdmin(paginaDeGestion, 'ges01')
    await paginaDeGestion.goto(`/admin/clientes/${clienteId}/credito`)
    await paginaDeGestion.getByLabel('Límite de crédito (vacío = hereda)').fill('10000')
    await paginaDeGestion.getByRole('button', { name: 'Guardar crédito' }).click()
    await expect(paginaDeGestion).toHaveURL(new RegExp(`/admin/clientes/${clienteId}$`))

    // El teléfono, con señal, baja los datos al día.
    await telefono.page.getByRole('button', { name: 'Actualizar datos' }).click()
    await expect(telefono.page.getByText(/No se pudieron actualizar los datos/)).toHaveCount(0)

    const api = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin')
    const consultas = new Consultas(api)
    expect(await consultas.stockBase('Camioneta 1', 'VINO-A')).toBe(80)
    expect(await consultas.stockBase('Camioneta 1', 'CERV-B')).toBe(120)

    // Lo que tiene que seguir igual después de enviar las ventas (el criterio 8 lo compara).
    recordar({
      saldoC001Antes: await consultas.saldoDeCliente('C001'),
      saldoC002Antes: await consultas.saldoDeCliente('C002'),
      costoVinoAntes: (await consultas.costoPromedio('VINO-A')).costo ?? '',
      costoCervezaAntes: (await consultas.costoPromedio('CERV-B')).costo ?? '',
    })
  })

  test('sin señal, la aplicación se recarga y abre con lo que guardó', async () => {
    await recargarSinSenal(telefono)
    await expect(telefono.page.getByText('Jornada abierta en Camioneta 1')).toBeVisible()
  })

  test('el vendedor arma el pedido de cajas y unidades sueltas con la regla de volumen y un descuento manual', async () => {
    const { page } = telefono
    await abrirVender(page, 'Almacén Don Pedro')
    await cargarProducto(page, 'Vino A', { cajas: 12, unidades: 3 })
    await cargarProducto(page, 'Cerveza B', { cajas: 8, unidades: 6 })

    // DSC-03: 21 cajas equivalentes superan el umbral de 20: la regla de volumen se aplica sola.
    await expect(page.getByText('Incluye descuentos')).toBeVisible()
    const totalSinManual = importeDeTexto(await page.getByTestId('total-de-la-venta').innerText())

    // DSC-06: descuento manual general del 5%, dentro del tope del vendedor (10%).
    await page.getByLabel('Descuento general (%)').fill('5')
    const motivo = page.getByLabel('Motivo del descuento')
    if (await motivo.isVisible()) await motivo.selectOption({ index: 1 })
    await expect
      .poll(async () => importeDeTexto(await page.getByTestId('total-de-la-venta').innerText()))
      .not.toBe(totalSinManual)
    expect(Number(importeDeTexto(await page.getByTestId('total-de-la-venta').innerText()))).toBeLessThan(
      Number(totalSinManual),
    )
  })

  test('cobra una parte con efectivo y transferencia y confirma: el resto queda en cuenta corriente', async () => {
    const { page } = telefono
    await page.getByRole('button', { name: 'Siguiente' }).click()
    await expect(page.getByText('Paso 3 de 3: cobro y confirmación')).toBeVisible()
    const total = importeDeTexto(await page.getByTestId('total-a-cobrar').innerText())

    await cobrarCon(page, 1, 'Efectivo', '10000')
    await cobrarCon(page, 2, 'Transferencia', '5000', 'TRF-0001')
    await expect(page.getByTestId('cobrado')).toContainText('15.000,00')
    // INV-08: lo no cobrado en el acto queda como saldo del cliente (saldo previo + total - cobrado).
    await expect(page.getByTestId('saldo-resultante')).toBeVisible()

    await page.getByRole('button', { name: 'Confirmar venta' }).click()
    await expect(page).toHaveURL(/\/ruta\/ventas\/[0-9a-f-]{36}$/)
    await expect(page.getByRole('heading', { name: /^Venta / })).toBeVisible()
    // Sin señal la venta queda guardada en el teléfono, sin enviar (INV-17).
    await expect(page.getByText('Sin enviar', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Almacén Don Pedro')).toBeVisible()

    const numero = (await page.getByRole('heading', { name: /^Venta / }).innerText()).replace('Venta ', '').trim()
    recordar({ numeroVenta5: numero, totalVenta5: total, cobradoVenta5: '15000.00' })

    // La cabecera cuenta la venta como pendiente.
    await expect(page.getByRole('link', { name: '1 sin enviar' })).toBeVisible()
  })
})
