/**
 * Mapea el `codigo` de un `ErrorDeClientes` (change 07, grupo 5, tareas
 * 5.3/5.4) al campo del formulario donde se muestra, mismo criterio que
 * `features/proveedores/mapaErrorACampo.ts`. `null` cuando el error no
 * corresponde a un campo puntual (se muestra como mensaje general).
 */

/** Campos de la ficha de cliente (`ClienteFormScreen.tsx`, tarea 5.3). */
export type CampoCliente = 'nombre' | 'direccion' | 'contacto' | 'codigo' | 'documento_numero' | 'estado'

const MAPA_CODIGO_A_CAMPO_CLIENTE: Record<string, CampoCliente> = {
  NOMBRE_INVALIDO: 'nombre',
  FICHA_INCOMPLETA: 'direccion',
  CODIGO_INVALIDO: 'codigo',
  CODIGO_DUPLICADO: 'codigo',
  DOCUMENTO_INCOMPLETO: 'documento_numero',
  DOCUMENTO_INVALIDO: 'documento_numero',
  DOCUMENTO_DUPLICADO: 'documento_numero',
  ESTADO_INVALIDO: 'estado',
  TRANSICION_ESTADO_INVALIDA: 'estado',
  CLIENTE_CON_OPERACIONES: 'estado',
  CONSUMIDOR_FINAL_NO_INACTIVABLE: 'estado',
}

export function campoDeClienteParaCodigo(codigo: string): CampoCliente | null {
  return MAPA_CODIGO_A_CAMPO_CLIENTE[codigo] ?? null
}

/** Campos del formulario de crédito (`ClienteCreditoScreen.tsx`, tarea 5.4). */
export type CampoCredito = 'limite_credito' | 'politica_credito' | 'tolerancia_offline_valor'

const MAPA_CODIGO_A_CAMPO_CREDITO: Record<string, CampoCredito> = {
  LIMITE_CREDITO_INVALIDO: 'limite_credito',
  CONSUMIDOR_FINAL_SIN_CREDITO: 'limite_credito',
  POLITICA_CREDITO_INVALIDA: 'politica_credito',
  TOLERANCIA_OFFLINE_INVALIDA: 'tolerancia_offline_valor',
}

export function campoDeCreditoParaCodigo(codigo: string): CampoCredito | null {
  return MAPA_CODIGO_A_CAMPO_CREDITO[codigo] ?? null
}
