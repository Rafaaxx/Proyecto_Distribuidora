import type { components } from '../../../src/api/schema.gen'

/** Bootstrap mínimo pero completo para las pruebas del change 21 (area `/ruta`). */
type Bootstrap = components['schemas']['BootstrapResponse']

export const ID = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`

export function clienteDePrueba(n: number, nombre: string): Bootstrap['clientes'][number] {
  return {
    id: ID(100 + n),
    codigo: `C${n}`,
    nombre,
    razon_social: null,
    documento_tipo: null,
    documento_numero: null,
    direccion: 'Calle 1',
    telefono: null,
    estado: 'ACTIVO',
    lista_precio_id: null,
    es_consumidor_final: false,
    en_cartera: true,
    saldo: '1500.50',
    credito: { limite: '10000.00', politica: 'BLOQUEAR', tolerancia_tipo: null, tolerancia_valor: null },
  }
}

export function bootstrapDePrueba(opciones: { clientes?: Bootstrap['clientes']; generado?: string } = {}): Bootstrap {
  return {
    generado_en: opciones.generado ?? '2026-10-30T10:00:00Z',
    sesion: {
      usuario: { id: ID(1), nombre: 'Vendedor Uno', usuario: 'vendedor' },
      permisos: ['VENDER'],
      jornada: {
        id: ID(2),
        ubicacion_id: ID(3),
        ubicacion_nombre: 'Camioneta 1',
        abierta_en: '2026-10-30T09:00:00Z',
      },
      numeracion: { prefijo: '0001', ultimo_correlativo: 7 },
    },
    configuracion: {
      organizacion_id: ID(9),
      nombre: 'Distribuidora',
      cuit: null,
      moneda: 'ARS',
      zona_horaria: 'America/Argentina/Buenos_Aires',
      condicion_iva: 'MONOTRIBUTO',
      modo_impositivo: 'A',
      politica_credito: 'BLOQUEAR',
      tolerancia_tipo: null,
      tolerancia_valor: null,
      permite_consumidor_final: true,
      consumidor_final_id: null,
      estado_facturacion_default: 'NO_FACTURADA',
      intentos_pin_max: 5,
      motivo_obligatorio_lista: false,
      nota: { domicilio: null, telefono: null, muestra_saldo: true },
    },
    contexto_venta: null,
    catalogos: {
      medios_pago: [{ id: ID(20), nombre: 'Efectivo', requiere_referencia: false }],
      motivos: [{ id: ID(21), ambito: 'DESCUENTO', nombre: 'Promo' }],
      alicuotas: [{ id: ID(22), nombre: 'IVA 21', valor: '0.210000' }],
    },
    productos: [
      {
        id: ID(30),
        codigo: 'P1',
        nombre: 'Gaseosa',
        categoria_id: ID(40),
        marca_id: null,
        alicuota_id: ID(22),
        alicuota_valor: '0.210000',
        presentacion_referencia_id: ID(31),
        presentaciones: [
          { id: ID(31), nombre: 'Caja x6', unidades_base: 6, es_referencia: true },
          { id: ID(32), nombre: 'Unidad', unidades_base: 1, es_referencia: false },
        ],
      },
    ],
    clientes: opciones.clientes ?? [clienteDePrueba(1, 'Almacén Uno'), clienteDePrueba(2, 'Kiosco Dos')],
    listas: [
      {
        id: ID(50),
        nombre: 'General',
        es_predeterminada: true,
        versiones: [
          {
            id: ID(51),
            numero: 1,
            estado: 'VIGENTE',
            vigencia_desde: '2026-10-01T00:00:00Z',
            vigencia_hasta: null,
            precios: [{ producto_id: ID(30), precio_referencia: '48000.00', unidades_referencia: 6 }],
          },
        ],
      },
    ],
    reglas_descuento: [],
    stock: [{ producto_id: ID(30), cantidad_base: 20 }],
    autorizadores: [],
  }
}

