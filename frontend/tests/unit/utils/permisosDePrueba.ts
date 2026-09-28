import { QueryClient } from '@tanstack/react-query'

import type { Yo } from '../../../src/features/identidad/api'
import { clavesIdentidad } from '../../../src/features/identidad/claves'
import type { CodigoPermiso } from '../../../src/domain/identidad/permisos'

/**
 * Auxiliar de prueba compartido (tarea 6.7): arma un `QueryClient` con
 * `['yo']` ya sembrado para un rol de `01-dominio.md` §19, así los grupos
 * 7 (menú, encabezado, aterrizaje) y 8 (pantallas con `<SiTienePermiso>`)
 * no repiten el cuerpo de `/yo` a mano ni mockean `apiFetch` solo para
 * fijar el permiso de la prueba.
 *
 * `PERMISOS_POR_ROL` es una copia de la tabla de `01` §19 para armar
 * datos de prueba; no es una fuente de autorización -- el servidor sigue
 * siendo quien decide (SEG-06). Si `01` §19 cambia, esta tabla se
 * actualiza junto con `domain/identidad/permisos.ts` (mismo criterio que
 * "todo cambio en una regla de cálculo actualiza los fixtures
 * compartidos antes de tocar el código", `CLAUDE.md` §4).
 */
export type RolDePrueba = 'ADM' | 'GES' | 'SUP' | 'VEN' | 'CON'

export const PERMISOS_POR_ROL: Record<RolDePrueba, CodigoPermiso[]> = {
  ADM: [
    'ADMIN_USUARIOS',
    'ADMIN_CONFIGURACION',
    'GESTIONAR_DISPOSITIVOS',
    'IMPORTAR_DATOS',
    'GESTIONAR_CATALOGO',
    'GESTIONAR_CLIENTES',
    'GESTIONAR_CREDITO',
    'GESTIONAR_PROVEEDORES',
    'VER_COSTOS',
    'EDITAR_COSTOS',
    'VER_UTILIDAD',
    'GESTIONAR_LISTAS',
    'PUBLICAR_LISTAS',
    'USAR_LISTA_ANTERIOR',
    'GESTIONAR_DESCUENTOS',
    'REGISTRAR_COMPRA',
    'ANULAR_COMPRA',
    'REGISTRAR_PAGO_PROVEEDOR',
    'ANULAR_PAGO_PROVEEDOR',
    'TRANSFERIR_STOCK',
    'AJUSTAR_STOCK',
    'PERMITIR_STOCK_NEGATIVO',
    'ABRIR_JORNADA',
    'RENDIR_JORNADA',
    'LIBERAR_UBICACION',
    'VENDER',
    'ANULAR_VENTA',
    'DESCUENTO_MANUAL',
    'AUTORIZAR_DESCUENTO',
    'SUPERAR_CREDITO',
    'VENDER_CLIENTE_SUSPENDIDO',
    'REGISTRAR_COBRANZA',
    'ANULAR_COBRANZA',
    'REVISAR_OBSERVACIONES',
    'VER_REPORTES',
    'VER_AUDITORIA',
    'FACTURAR',
    'FACTURAR_ABSORBIENDO_IVA',
    'ANULAR_FACTURA',
  ],
  GES: [
    'GESTIONAR_CATALOGO',
    'GESTIONAR_CLIENTES',
    'GESTIONAR_CREDITO',
    'GESTIONAR_PROVEEDORES',
    'VER_COSTOS',
    'EDITAR_COSTOS',
    'VER_UTILIDAD',
    'GESTIONAR_LISTAS',
    'REGISTRAR_COMPRA',
    'ANULAR_COMPRA',
    'REGISTRAR_PAGO_PROVEEDOR',
    'ANULAR_PAGO_PROVEEDOR',
    'TRANSFERIR_STOCK',
    'AJUSTAR_STOCK',
    'RENDIR_JORNADA',
    'ANULAR_VENTA',
    'REGISTRAR_COBRANZA',
    'ANULAR_COBRANZA',
    'REVISAR_OBSERVACIONES',
    'VER_REPORTES',
    'FACTURAR',
    'ANULAR_FACTURA',
  ],
  SUP: [
    'GESTIONAR_DISPOSITIVOS',
    'GESTIONAR_CLIENTES',
    'USAR_LISTA_ANTERIOR',
    'TRANSFERIR_STOCK',
    'ABRIR_JORNADA',
    'RENDIR_JORNADA',
    'LIBERAR_UBICACION',
    'VENDER',
    'ANULAR_VENTA',
    'DESCUENTO_MANUAL',
    'AUTORIZAR_DESCUENTO',
    'SUPERAR_CREDITO',
    'VENDER_CLIENTE_SUSPENDIDO',
    'REGISTRAR_COBRANZA',
    'ANULAR_COBRANZA',
    'REVISAR_OBSERVACIONES',
    'VER_REPORTES',
  ],
  VEN: ['TRANSFERIR_STOCK', 'ABRIR_JORNADA', 'VENDER', 'DESCUENTO_MANUAL', 'REGISTRAR_COBRANZA'],
  CON: ['VER_UTILIDAD', 'VER_REPORTES', 'VER_AUDITORIA'],
}

const NOMBRE_DE_ROL: Record<RolDePrueba, string> = {
  ADM: 'Administrador',
  GES: 'Administración',
  SUP: 'Supervisor comercial',
  VEN: 'Vendedor/Repartidor',
  CON: 'Consulta/Dirección',
}

/** Construye el cuerpo de `/yo` (`YoResponse`) para `rol`, con `overrides`
 * parciales por campo cuando una prueba necesita un nombre o id
 * específico. Los permisos siempre vienen de `PERMISOS_POR_ROL`, salvo
 * que `overrides.permisos` los pise explícitamente. */
export function yoDePrueba(rol: RolDePrueba, overrides: Partial<Yo> = {}): Yo {
  return {
    usuario: { id: 'usuario-de-prueba', nombre: `Usuario ${NOMBRE_DE_ROL[rol]}` },
    organizacion: { id: 'organizacion-de-prueba', nombre: 'Organización de prueba' },
    rol: { id: `rol-${rol.toLowerCase()}`, nombre: NOMBRE_DE_ROL[rol] },
    permisos: [...PERMISOS_POR_ROL[rol]],
    ...overrides,
  }
}

/** `QueryClient` de prueba con `['yo']` ya resuelto para `rol`: ninguna
 * prueba que lo use necesita mockear `apiFetch` para `/yo`, ni esperar a
 * que la consulta salga de `cargando`. */
export function queryClientConYo(rol: RolDePrueba, overrides: Partial<Yo> = {}): QueryClient {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  queryClient.setQueryData(clavesIdentidad.yo(), yoDePrueba(rol, overrides))
  return queryClient
}
