/**
 * Códigos de permiso de `01-dominio.md` §19 (D8-A, `design.md`): unión
 * literal, no `string` libre. Un error de tipeo en una pantalla es un
 * error de compilación (`npm run typecheck`), no una sección que se
 * oculta para siempre sin ningún aviso.
 *
 * La respuesta de `GET /api/v1/yo` sigue siendo `string[]` (el backend no
 * conoce esta unión): un código desconocido en la lista de la API
 * simplemente no coincide con ningún `CodigoPermiso` usado en la interfaz.
 * Si el backend agrega un permiso, esta unión se amplía cuando la
 * interfaz lo necesite.
 */
export type CodigoPermiso =
  | 'ADMIN_USUARIOS'
  | 'ADMIN_CONFIGURACION'
  | 'GESTIONAR_DISPOSITIVOS'
  | 'IMPORTAR_DATOS'
  | 'GESTIONAR_CATALOGO'
  | 'GESTIONAR_CLIENTES'
  | 'GESTIONAR_CREDITO'
  | 'GESTIONAR_PROVEEDORES'
  | 'VER_COSTOS'
  | 'EDITAR_COSTOS'
  | 'VER_UTILIDAD'
  | 'GESTIONAR_LISTAS'
  | 'PUBLICAR_LISTAS'
  | 'USAR_LISTA_ANTERIOR'
  | 'GESTIONAR_DESCUENTOS'
  | 'REGISTRAR_COMPRA'
  | 'ANULAR_COMPRA'
  | 'REGISTRAR_PAGO_PROVEEDOR'
  | 'ANULAR_PAGO_PROVEEDOR'
  | 'TRANSFERIR_STOCK'
  | 'AJUSTAR_STOCK'
  | 'PERMITIR_STOCK_NEGATIVO'
  | 'ABRIR_JORNADA'
  | 'RENDIR_JORNADA'
  | 'LIBERAR_UBICACION'
  | 'VENDER'
  | 'ANULAR_VENTA'
  | 'DESCUENTO_MANUAL'
  | 'AUTORIZAR_DESCUENTO'
  | 'SUPERAR_CREDITO'
  | 'VENDER_CLIENTE_SUSPENDIDO'
  | 'REGISTRAR_COBRANZA'
  | 'ANULAR_COBRANZA'
  | 'REVISAR_OBSERVACIONES'
  | 'VER_REPORTES'
  | 'VER_AUDITORIA'
  | 'FACTURAR'
  | 'FACTURAR_ABSORBIENDO_IVA'
  | 'ANULAR_FACTURA'
