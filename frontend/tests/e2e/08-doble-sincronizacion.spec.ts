/**
 * Criterio 8 de `00` §9 (change 28, D14, D15): doble sincronización deliberada. Spec
 * `sistema/aceptacion-etapa-1`, escenario «Criterio 8 — doble sincronización deliberada». Cita
 * INV-06, INV-08, INV-17, CST-11.
 *
 * Vuelve la señal y el teléfono envía su lote (las ventas de los criterios 5 y 6). La prueba
 * captura ese pedido tal como salió del teléfono y lo vuelve a mandar dos veces: es el reintento
 * de un corte a mitad de camino. Después comprueba POR LA API que existe una sola venta por
 * operación y que stock, saldos, costo y utilidad son los de una sola confirmación.
 */
import Decimal from 'decimal.js'

import { ApiDeAceptacion, Consultas } from './apoyo/api'
import { expect, test } from './apoyo/fixtures'
import { exigir } from './apoyo/memoria'
import { abrirTelefono, cerrarTelefono, guardarTelefono, problemasDelTelefono, volverLaSenal, type Telefono } from './apoyo/telefono'

interface PedidoCapturado {
  url: string
  cuerpo: string
  cabeceras: Record<string, string>
}

test.describe.configure({ mode: 'serial' })

test.describe('Criterio 8 — doble sincronización deliberada', () => {
  let telefono: Telefono
  const pedidos: PedidoCapturado[] = []

  test.beforeAll(async ({ browser }, testInfo) => {
    telefono = await abrirTelefono(browser, testInfo.project.use.baseURL ?? '')
    telefono.page.on('request', (pedido) => {
      if (pedido.method() === 'POST' && pedido.url().endsWith('/api/v1/sync/comandos')) {
        void pedido.allHeaders().then((cabeceras) => {
          pedidos.push({ url: pedido.url(), cuerpo: pedido.postData() ?? '', cabeceras })
        })
      }
    })
  })

  test.afterAll(async () => {
    await guardarTelefono(telefono)
    expect(problemasDelTelefono(telefono), 'el teléfono informó errores de seguridad o no manejados').toEqual([])
    await cerrarTelefono(telefono)
  })

  test('con señal, el teléfono envía el lote y todo queda enviado', async () => {
    const { page } = telefono
    await expect(page.getByRole('link', { name: /sin enviar/ })).toBeVisible()
    // Vuelve la señal: el teléfono envía solo (evento `online`); «Sincronizar» pide el envío ya.
    await volverLaSenal(telefono)
    await page.getByRole('button', { name: 'Sincronizar' }).first().click()

    await expect(page.getByRole('link', { name: 'Todo enviado' })).toBeVisible()
    expect(pedidos.length).toBeGreaterThanOrEqual(1)
    expect(pedidos.some((p) => p.cuerpo.includes(exigir('numeroVenta5')))).toBe(true)
  })

  test('el mismo lote, enviado dos veces más, no duplica nada', async ({ browser, baseURL }) => {
    const lote = pedidos.find((p) => p.cuerpo.includes(exigir('numeroVenta5')))
    expect(lote, 'no se capturó el lote del teléfono').toBeDefined()
    if (lote === undefined) return

    // INV-06: cada reenvío lleva las mismas operaciones; el servidor responde sin volver a aplicarlas.
    for (let vez = 1; vez <= 2; vez += 1) {
      const respuesta = await telefono.context.request.post(lote.url, {
        data: lote.cuerpo,
        headers: {
          'content-type': lote.cabeceras['content-type'] ?? 'application/json',
          authorization: lote.cabeceras['authorization'] ?? '',
        },
      })
      expect(respuesta.status(), `reenvío ${String(vez)}`).toBeLessThan(500)
    }

    const api = await ApiDeAceptacion.iniciarSesion(browser, baseURL ?? '', 'admin')
    const consultas = new Consultas(api)

    // Una sola venta por operación: cada número aparece una vez.
    const ventas = await consultas.ventas()
    const venta5 = ventas.filter((v) => v.numero === exigir('numeroVenta5'))
    const venta6 = ventas.filter((v) => v.numero === exigir('numeroVenta6'))
    expect(venta5).toHaveLength(1)
    expect(venta6).toHaveLength(1)
    expect(new Set(ventas.map((v) => v.numero)).size).toBe(ventas.length)
    // El total que mostró el teléfono es el que guardó el servidor (INV-17).
    expect(new Decimal(venta5[0]?.total ?? '0').toFixed(2)).toBe(exigir('totalVenta5'))
    expect(new Decimal(venta6[0]?.total ?? '0').toFixed(2)).toBe(exigir('totalVenta6'))

    // Stock (INV-04): 80 - (12x6 + 3) = 5 botellas; 120 - (8x12 + 6) - 12 = 6 latas.
    expect(await consultas.stockBase('Camioneta 1', 'VINO-A')).toBe(5)
    expect(await consultas.stockBase('Camioneta 1', 'CERV-B')).toBe(6)

    // Saldos (INV-08): saldo previo + total - cobrado, una sola vez.
    const saldo1 = new Decimal(exigir('saldoC001Antes')).plus(exigir('totalVenta5')).minus(exigir('cobradoVenta5'))
    const saldo2 = new Decimal(exigir('saldoC002Antes')).plus(exigir('totalVenta6'))
    expect(await consultas.saldoDeCliente('C001')).toBe(saldo1.toFixed(2))
    expect(await consultas.saldoDeCliente('C002')).toBe(saldo2.toFixed(2))

    // Costo (CST-11): una venta no mueve el promedio.
    expect((await consultas.costoPromedio('VINO-A')).costo).toBe(exigir('costoVinoAntes'))
    expect((await consultas.costoPromedio('CERV-B')).costo).toBe(exigir('costoCervezaAntes'))

    // Utilidad: neto - costo vendido de las líneas, sin duplicar ninguna.
    const detalle5 = await consultas.detalleDeVenta(venta5[0]?.venta_id ?? '')
    const detalle6 = await consultas.detalleDeVenta(venta6[0]?.venta_id ?? '')
    const lineas = [...detalle5.lineas, ...detalle6.lineas]
    // Una línea por presentación: cajas y unidades sueltas de Vino A y de Cerveza B (4); la caja de Cerveza B (1).
    expect(detalle5.lineas).toHaveLength(4)
    expect(detalle6.lineas).toHaveLength(1)
    const costoEsperado = lineas.reduce((suma, l) => suma.plus(l.costo_total ?? '0'), new Decimal(0))
    const netoEsperado = lineas.reduce((suma, l) => suma.plus(l.importe_neto), new Decimal(0))

    const reporte = await api.leer<{ resumen: { costo_vendido: string | null; utilidad: string | null } }>(
      '/api/v1/reportes/ventas',
    )
    expect(reporte.resumen.costo_vendido).not.toBeNull()
    expect(new Decimal(reporte.resumen.costo_vendido ?? '0').gte(costoEsperado)).toBe(true)
    expect(
      new Decimal(reporte.resumen.utilidad ?? '0').gte(netoEsperado.minus(costoEsperado)),
      'la utilidad del período incluye la de las dos ventas',
    ).toBe(true)
  })
})
