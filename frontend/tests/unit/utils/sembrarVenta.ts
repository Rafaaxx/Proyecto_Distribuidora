import { leerDatosParaVender } from '../../../src/areas/ruta/datos/paraVender'
import { armarConfirmacionDeRuta, armarVentaDeRuta } from '../../../src/domain/ruta/armadoDeVentaLocal'
import { confirmarVentaLocal } from '../../../src/sync/confirmarVentaLocal'
import { carritoDePrueba, IDS_DE_PRUEBA } from './datosParaVender'

/**
 * Confirma una venta de verdad (armado puro + transacción de Dexie) sobre la base ya sembrada con
 * un bootstrap: 2 cajas + 3 unidades de Gaseosa ($120.000,00) salvo que se indique otra cosa.
 */
export async function sembrarVenta(
  sufijo: string,
  opciones: { clienteId?: string; usuarioId?: string; cajas?: number; unidades?: number; ahora?: Date } = {},
) {
  const datos = await leerDatosParaVender()
  if (datos === null) throw new Error('Primero se aplica el bootstrap de prueba.')
  const carrito = carritoDePrueba({
    ventaId: `venta-${sufijo}`,
    cobranzaId: `cobranza-${sufijo}`,
    operationId: `op-${sufijo}`,
    clienteId: opciones.clienteId ?? IDS_DE_PRUEBA.cliente,
    items: [
      {
        productoId: IDS_DE_PRUEBA.producto,
        cajas: opciones.cajas ?? 2,
        unidades: opciones.unidades ?? 3,
        idsDeLinea: { [IDS_DE_PRUEBA.caja]: `l-caja-${sufijo}`, [IDS_DE_PRUEBA.unidad]: `l-unidad-${sufijo}` },
      },
    ],
  })
  const ahora = opciones.ahora ?? new Date('2026-10-30T15:00:00.000Z')
  const armada = armarVentaDeRuta(datos, carrito, ahora)
  const entrada = armarConfirmacionDeRuta(datos, carrito, armada, {
    usuarioId: opciones.usuarioId ?? datos.sesion.usuario.id,
    dispositivoId: 'disp-1',
    ahora,
    appVersion: '1.0.0',
    autorizadoresVerificados: [],
  })
  return confirmarVentaLocal(entrada)
}
