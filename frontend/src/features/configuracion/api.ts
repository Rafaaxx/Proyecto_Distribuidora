import { apiFetch } from '../../lib/api/httpClient'
import type { components } from '../../api/schema.gen'
import { errorDesdeRespuesta } from './errores'

/**
 * Funciones de acceso a `/api/v1/configuracion/*` (tarea 10.7, `design.md`
 * D12). Tipadas contra `schema.gen.ts` (generado del OpenAPI real, tarea
 * 9.8) -- nunca `any`. Mismo patrón que `features/catalogo/api.ts` (tarea
 * 10.2).
 */

export type Alicuota = components['schemas']['AlicuotaResponse']
export type PaginaAlicuotas = components['schemas']['PaginaAlicuotas']

async function leerJsonOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw new Error('No se pudo obtener el listado de alícuotas.')
  }
  return (await respuesta.json()) as T
}

function paramsPagina(cursor: string | undefined, limite: number): string {
  const params = new URLSearchParams()
  params.set('limite', String(limite))
  if (cursor) {
    params.set('cursor', cursor)
  }
  return params.toString()
}

export async function listarAlicuotas(cursor?: string, limite = 30): Promise<PaginaAlicuotas> {
  const respuesta = await apiFetch(`/configuracion/alicuotas?${paramsPagina(cursor, limite)}`)
  return leerJsonOLanzar(respuesta)
}

export type ConfiguracionFiscal = components['schemas']['ConfiguracionFiscalResponse']
export type CondicionIva = components['schemas']['CondicionIvaCambiarRequest']['condicion_iva']
export type CondicionIvaCambiarDatos = components['schemas']['CondicionIvaCambiarRequest']
export type ResumenReglaIva = components['schemas']['ResumenReglaIvaResponse']

async function leerFiscalOLanzar<T>(respuesta: Response): Promise<T> {
  if (!respuesta.ok) {
    throw await errorDesdeRespuesta(respuesta)
  }
  return (await respuesta.json()) as T
}

/** `GET /configuracion/fiscal` (11b, D8): la condición de la organización del token. */
export async function obtenerConfiguracionFiscal(): Promise<ConfiguracionFiscal> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/fiscal'))
}

/** `GET /costos/resumen-regla-iva` (11b, D10): costos vigentes por regla de IVA. */
export async function obtenerResumenReglaIva(): Promise<ResumenReglaIva> {
  return leerFiscalOLanzar(await apiFetch('/costos/resumen-regla-iva'))
}

/** `POST /configuracion/fiscal/condicion-iva` (11b, D7). El `Operation-Id` lo conserva quien llama. */
export async function cambiarCondicionIva(
  datos: CondicionIvaCambiarDatos,
  operationId: string,
): Promise<ConfiguracionFiscal> {
  const respuesta = await apiFetch('/configuracion/fiscal/condicion-iva', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(datos),
  })
  return leerFiscalOLanzar(respuesta)
}

// --- medios de pago administrables (change 17b, D2, D6) -------------------------------------

export type MedioPagoAdmin = components['schemas']['MedioPagoAdminResponse']
export type MedioPagoCrearDatos = components['schemas']['MedioPagoCrearRequest']
export type MedioPagoModificarDatos = components['schemas']['MedioPagoModificarRequest']

function escrituraDeMedio(metodo: 'POST' | 'PUT', operationId: string, cuerpo: unknown): RequestInit {
  return {
    method: metodo,
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(cuerpo),
  }
}

/** `GET /configuracion/medios-pago/todos` (`ADMIN_CONFIGURACION`): activos e inactivos. */
export async function listarMediosPagoAdmin(): Promise<MedioPagoAdmin[]> {
  const lista = await leerFiscalOLanzar<{ items: MedioPagoAdmin[] }>(await apiFetch('/configuracion/medios-pago/todos'))
  return lista.items
}

/** `POST /configuracion/medios-pago` (`MEDIO_PAGO_CREAR`). El `Operation-Id` lo conserva quien llama. */
export async function crearMedioPago(datos: MedioPagoCrearDatos, operationId: string): Promise<MedioPagoAdmin> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/medios-pago', escrituraDeMedio('POST', operationId, datos)))
}

/** `PUT /configuracion/medios-pago/{id}` (`MEDIO_PAGO_MODIFICAR`): reemplazo completo; la baja es `activo=false`. */
export async function modificarMedioPago(
  medioPagoId: string,
  datos: MedioPagoModificarDatos,
  operationId: string,
): Promise<MedioPagoAdmin> {
  return leerFiscalOLanzar(
    await apiFetch(`/configuracion/medios-pago/${medioPagoId}`, escrituraDeMedio('PUT', operationId, datos)),
  )
}

// --- descuento manual y crédito por defecto (change 18b, D13, D14) --------------------------

export type DescuentoManualConfig = components['schemas']['DescuentoManualResponse']
export type DescuentoManualConfigurarDatos = components['schemas']['DescuentoManualConfigurarRequest']
export type CreditoOrganizacion = components['schemas']['CreditoOrganizacionResponse']
export type CreditoOrganizacionConfigurarDatos = components['schemas']['CreditoOrganizacionConfigurarRequest']

function escritura(operationId: string, cuerpo: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Operation-Id': operationId },
    body: JSON.stringify(cuerpo),
  }
}

/** `GET /configuracion/descuento-manual`: si está habilitado y si exige motivo. */
export async function obtenerDescuentoManual(): Promise<DescuentoManualConfig> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/descuento-manual'))
}

/** `POST /configuracion/descuento-manual` (`DESCUENTO_MANUAL_CONFIGURAR`, `ADMIN_CONFIGURACION`). */
export async function configurarDescuentoManual(
  datos: DescuentoManualConfigurarDatos,
  operationId: string,
): Promise<DescuentoManualConfig> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/descuento-manual', escritura(operationId, datos)))
}

/** `GET /configuracion/credito`: política por defecto y tolerancia sin conexión. */
export async function obtenerCreditoOrganizacion(): Promise<CreditoOrganizacion> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/credito'))
}

/** `POST /configuracion/credito` (`CREDITO_ORGANIZACION_CONFIGURAR`, `ADMIN_CONFIGURACION`). */
export async function configurarCreditoOrganizacion(
  datos: CreditoOrganizacionConfigurarDatos,
  operationId: string,
): Promise<CreditoOrganizacion> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/credito', escritura(operationId, datos)))
}

// --- nota de venta (change 20, D10) ----------------------------------------------------------

export type NotaVentaConfig = components['schemas']['NotaVentaConfiguracionResponse']
export type NotaVentaConfigurarDatos = components['schemas']['NotaVentaConfigurarRequest']

/** `GET /configuracion/nota-de-venta`: si la nota muestra el saldo, domicilio y teléfono. */
export async function obtenerNotaVentaConfig(): Promise<NotaVentaConfig> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/nota-de-venta'))
}

/** `POST /configuracion/nota-de-venta` (`NOTA_VENTA_CONFIGURAR`, `ADMIN_CONFIGURACION`). */
export async function configurarNotaVenta(datos: NotaVentaConfigurarDatos, operationId: string): Promise<NotaVentaConfig> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/nota-de-venta', escritura(operationId, datos)))
}

// --- datos de la organización (change 20, D15) ------------------------------------------------

export type OrganizacionDatos = components['schemas']['OrganizacionDatosResponse']
export type OrganizacionDatosConfigurar = components['schemas']['OrganizacionDatosConfigurarRequest']

/** `GET /configuracion/organizacion`: nombre y CUIT de la organización. */
export async function obtenerOrganizacionDatos(): Promise<OrganizacionDatos> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/organizacion'))
}

/** `POST /configuracion/organizacion` (`ORGANIZACION_DATOS_CONFIGURAR`, `ADMIN_CONFIGURACION`). */
export async function configurarOrganizacionDatos(
  datos: OrganizacionDatosConfigurar,
  operationId: string,
): Promise<OrganizacionDatos> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/organizacion', escritura(operationId, datos)))
}

// --- motivos, alícuotas y redondeo por defecto administrables (change 20c, D12) ----------------

export type MotivoAdmin = components['schemas']['MotivoAdminResponse']
export type MotivoCrearDatos = components['schemas']['MotivoCrearRequest']
export type MotivoModificarDatos = components['schemas']['MotivoModificarRequest']

/** `GET /configuracion/motivos/todos?ambito=` (`ADMIN_CONFIGURACION`): activos e inactivos del ámbito. */
export async function listarMotivosAdmin(ambito: string): Promise<MotivoAdmin[]> {
  const lista = await leerFiscalOLanzar<{ items: MotivoAdmin[] }>(
    await apiFetch(`/configuracion/motivos/todos?${new URLSearchParams({ ambito }).toString()}`),
  )
  return lista.items
}

/** `POST /configuracion/motivos` (`MOTIVO_CREAR`). El `Operation-Id` lo conserva quien llama. */
export async function crearMotivo(datos: MotivoCrearDatos, operationId: string): Promise<MotivoAdmin> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/motivos', escrituraDeMedio('POST', operationId, datos)))
}

/** `PUT /configuracion/motivos/{id}` (`MOTIVO_MODIFICAR`): reemplazo de nombre y estado. */
export async function modificarMotivo(
  motivoId: string,
  datos: MotivoModificarDatos,
  operationId: string,
): Promise<MotivoAdmin> {
  return leerFiscalOLanzar(
    await apiFetch(`/configuracion/motivos/${motivoId}`, escrituraDeMedio('PUT', operationId, datos)),
  )
}

export type AlicuotaCrearDatos = components['schemas']['AlicuotaCrearRequest']
export type AlicuotaModificarDatos = components['schemas']['AlicuotaModificarRequest']

/** `POST /configuracion/alicuotas` (`ALICUOTA_CREAR`): el valor viaja como string (INV-03). */
export async function crearAlicuota(datos: AlicuotaCrearDatos, operationId: string): Promise<Alicuota> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/alicuotas', escrituraDeMedio('POST', operationId, datos)))
}

/** `PUT /configuracion/alicuotas/{id}` (`ALICUOTA_MODIFICAR`): reemplazo completo; el valor no cambia. */
export async function modificarAlicuota(
  alicuotaId: string,
  datos: AlicuotaModificarDatos,
  operationId: string,
): Promise<Alicuota> {
  return leerFiscalOLanzar(
    await apiFetch(`/configuracion/alicuotas/${alicuotaId}`, escrituraDeMedio('PUT', operationId, datos)),
  )
}

export type RedondeoPorDefecto = components['schemas']['RedondeoPorDefectoResponse']
export type RedondeoPorDefectoDatos = components['schemas']['RedondeoPorDefectoDefinirRequest']

/** `GET /configuracion/redondeo-por-defecto` (`ADMIN_CONFIGURACION` o `GESTIONAR_LISTAS`). */
export async function obtenerRedondeoPorDefecto(): Promise<RedondeoPorDefecto> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/redondeo-por-defecto'))
}

/** `POST /configuracion/redondeo-por-defecto` (`REDONDEO_POR_DEFECTO_DEFINIR`); los dos nulos lo quitan. */
export async function definirRedondeoPorDefecto(
  datos: RedondeoPorDefectoDatos,
  operationId: string,
): Promise<RedondeoPorDefecto> {
  return leerFiscalOLanzar(await apiFetch('/configuracion/redondeo-por-defecto', escritura(operationId, datos)))
}
