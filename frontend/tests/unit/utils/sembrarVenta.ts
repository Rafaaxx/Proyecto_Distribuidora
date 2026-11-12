import { leerDatosParaVender } from '../../../src/areas/ruta/datos/paraVender'
import { armarConfirmacionDeRuta, armarVentaDeRuta } from '../../../src/domain/ruta/armadoDeVentaLocal'
import { baseLocal } from '../../../src/lib/dispositivo/db'
import { anularVentaLocal } from '../../../src/sync/anularVentaLocal'
import { confirmarVentaLocal } from '../../../src/sync/confirmarVentaLocal'
import { registrarCobranzaLocal } from '../../../src/sync/registrarCobranzaLocal'
import { carritoDePrueba, IDS_DE_PRUEBA } from './datosParaVender'

/**
 * Confirma una venta de verdad (armado puro + transacción de Dexie) sobre la base ya sembrada con
 * un bootstrap: 2 cajas + 3 unidades de Gaseosa ($120.000,00) salvo que se indique otra cosa.
 */
export async function sembrarVenta(
  sufijo: string,
  opciones: {
    clienteId?: string
    usuarioId?: string
    cajas?: number
    unidades?: number
    ahora?: Date
    /** Importe cobrado en el acto, en efectivo (sin cobro si se omite). */
    cobro?: string
  } = {},
) {
  const datos = await leerDatosParaVender()
  if (datos === null) throw new Error('Primero se aplica el bootstrap de prueba.')
  const carrito = carritoDePrueba({
    ventaId: `venta-${sufijo}`,
    cobranzaId: `cobranza-${sufijo}`,
    operationId: `op-${sufijo}`,
    clienteId: opciones.clienteId ?? IDS_DE_PRUEBA.cliente,
    medios:
      opciones.cobro === undefined
        ? []
        : [{ medioPagoId: IDS_DE_PRUEBA.efectivo, importe: opciones.cobro, referencia: '' }],
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

/**
 * Anula de verdad (transacción de Dexie) la venta sembrada con el mismo sufijo, con el motivo
 * «Error de carga». El `operation_id` de la anulación es `op-anul-<sufijo>`.
 */
export async function sembrarAnulacion(
  sufijo: string,
  opciones: { devuelveDinero?: boolean | null; observacion?: string | null; ahora?: Date } = {},
) {
  const sesion = await baseLocal.sesion.get('actual')
  if (sesion === undefined) throw new Error('Primero se aplica el bootstrap de prueba.')
  return anularVentaLocal({
    ventaId: `venta-${sufijo}`,
    motivo: { id: IDS_DE_PRUEBA.motivo, nombre: 'Error de carga' },
    observacion: opciones.observacion ?? null,
    devuelveDinero: opciones.devuelveDinero ?? null,
    operationId: `op-anul-${sufijo}`,
    usuarioId: sesion.usuario.id,
    dispositivoId: 'disp-1',
    ahora: opciones.ahora ?? new Date('2026-10-30T16:00:00.000Z'),
    appVersion: '1.0.0',
  })
}

/**
 * Registra de verdad (transacción de Dexie) una cobranza independiente en efectivo (change 23).
 * Ids: `cobranza-s-<sufijo>` y `op-cob-<sufijo>`; $100,00 salvo que se indique otro importe.
 */
export async function sembrarCobranza(
  sufijo: string,
  opciones: { clienteId?: string; importe?: string; ahora?: Date; observacion?: string | null } = {},
) {
  const sesion = await baseLocal.sesion.get('actual')
  if (sesion === undefined) throw new Error('Primero se aplica el bootstrap de prueba.')
  const importe = opciones.importe ?? '100.00'
  return registrarCobranzaLocal({
    cobranzaId: `cobranza-s-${sufijo}`,
    operationId: `op-cob-${sufijo}`,
    clienteId: opciones.clienteId ?? IDS_DE_PRUEBA.cliente,
    importe,
    medios: [{ medio_pago_id: IDS_DE_PRUEBA.efectivo, importe, referencia: null }],
    observacion: opciones.observacion ?? null,
    usuarioId: sesion.usuario.id,
    dispositivoId: 'disp-1',
    ahora: opciones.ahora ?? new Date('2026-10-30T16:30:00.000Z'),
    appVersion: '1.0.0',
  })
}
