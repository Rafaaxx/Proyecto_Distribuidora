import type { components } from '../../../src/api/schema.gen'
import type { CarritoDeRuta } from '../../../src/domain/ruta/armadoDeVentaLocal'
import type { DatosParaVender } from '../../../src/domain/ruta/armadoDeVentaLocal'
import { bootstrapDePrueba, ID } from './bootstrapDePrueba'

type Bootstrap = components['schemas']['BootstrapResponse']

/**
 * Instantánea de la base local para las pruebas del armado de la venta de ruta (change 22a): los
 * mismos datos que `aplicarBootstrap` guardaría, sin pasar por Dexie.
 */
export function datosParaVenderDesde(b: Bootstrap, movimientos: DatosParaVender['movimientos'] = []): DatosParaVender {
  return {
    sesion: { clave: 'actual', ...b.sesion, contexto_venta: b.contexto_venta },
    configuracion: { clave: 'organizacion', ...b.configuracion },
    clientes: b.clientes,
    productos: b.productos.map((p) => {
      const { presentaciones, ...producto } = p
      void presentaciones
      return producto
    }),
    presentaciones: b.productos.flatMap((p) => p.presentaciones.map((pr) => ({ ...pr, producto_id: p.id }))),
    listas: b.listas.map((l) => ({ id: l.id, nombre: l.nombre, es_predeterminada: l.es_predeterminada })),
    versiones: b.listas.flatMap((l) =>
      l.versiones.map((v) => ({
        id: v.id,
        lista_id: l.id,
        numero: v.numero,
        estado: v.estado,
        vigencia_desde: v.vigencia_desde,
        vigencia_hasta: v.vigencia_hasta,
      })),
    ),
    precios: b.listas.flatMap((l) => l.versiones.flatMap((v) => v.precios.map((pr) => ({ ...pr, version_id: v.id })))),
    reglas: b.reglas_descuento,
    stock: b.stock,
    mediosPago: b.catalogos.medios_pago,
    motivos: b.catalogos.motivos,
    autorizadores: b.autorizadores,
    movimientos,
  }
}

/** Bootstrap de la venta de ruta: Gaseosa x6 a $48.000 la caja (stock 20), cliente sin límite. */
export function bootstrapParaVender(cambios: (b: Bootstrap) => void = () => undefined): Bootstrap {
  const b = bootstrapDePrueba()
  b.sesion.permisos = ['VENDER']
  const primero = b.clientes[0]
  if (primero) primero.credito = { limite: null, politica: 'BLOQUEAR', tolerancia_tipo: null, tolerancia_valor: null }
  cambios(b)
  return b
}

export const IDS_DE_PRUEBA = {
  cliente: ID(101),
  producto: ID(30),
  caja: ID(31),
  unidad: ID(32),
  efectivo: ID(20),
  motivo: ID(21),
}

export function carritoDePrueba(sobre: Partial<CarritoDeRuta> = {}): CarritoDeRuta {
  return {
    ventaId: 'venta-1',
    cobranzaId: 'cobranza-1',
    operationId: 'op-1',
    clienteId: IDS_DE_PRUEBA.cliente,
    listaId: '',
    versionId: '',
    motivoListaId: '',
    items: [
      {
        productoId: IDS_DE_PRUEBA.producto,
        cajas: 2,
        unidades: 3,
        idsDeLinea: { [IDS_DE_PRUEBA.caja]: 'linea-caja', [IDS_DE_PRUEBA.unidad]: 'linea-unidad' },
      },
    ],
    generalTexto: '',
    propios: {},
    motivoDescuentoId: '',
    medios: [],
    observacionCobranza: '',
    aceptaExceso: false,
    seleccion: {},
    venderIgual: false,
    ...sobre,
  }
}
