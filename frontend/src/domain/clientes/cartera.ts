/**
 * Reglas puras de la cartera de clientes en las pantallas (change 20b, tarea 10.3; D13, D14, D15;
 * `01` §19, CLI-03). Solo UX: el servidor valida igual (`VENDEDOR_INVALIDO`, 409).
 */

export interface ClienteConVendedor {
  vendedor_id: string | null
  vendedor_nombre?: string | null
  vendedor_valido?: boolean | null
}

/** Texto del vendedor de un cliente; el de baja o sin permiso se marca para reasignarlo (D6, D15). */
export function etiquetaDeVendedor(cliente: ClienteConVendedor): { texto: string; paraReasignar: boolean } {
  if (cliente.vendedor_id === null) return { texto: 'Sin vendedor', paraReasignar: false }
  const nombre = cliente.vendedor_nombre ?? 'Vendedor'
  if (cliente.vendedor_valido === false) return { texto: `${nombre} (de baja o sin permiso)`, paraReasignar: true }
  return { texto: nombre, paraReasignar: false }
}

/** El consumidor final no se asigna a ningún vendedor: lo ven todos (CLI-03, D13). */
export function puedeAsignarse(cliente: { es_consumidor_final: boolean }): boolean {
  return !cliente.es_consumidor_final
}

const MENSAJES_POR_CODIGO: Record<string, string> = {
  VENDEDOR_INVALIDO:
    'Ese usuario no puede ser vendedor: tiene que estar activo, con un rol activo que permita vender o cobrar.',
  CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR: 'El consumidor final no se asigna a ningún vendedor: lo ven todos.',
  PERMISO_REQUERIDO: 'No tenés permiso para asignar vendedores.',
  RECURSO_NO_ENCONTRADO: 'Alguno de los clientes ya no existe. Actualizá la pantalla y volvé a intentar.',
}

/** Explicación en palabras simples de cada código de la asignación; con otro código, el mensaje del servidor. */
export function mensajeDeErrorDeClientes(codigo: string | null, mensajeDelServidor: string): string {
  return (codigo !== null ? MENSAJES_POR_CODIGO[codigo] : undefined) ?? mensajeDelServidor
}

function sinAcentosEnMinuscula(texto: string): string {
  return texto.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
}

/**
 * Buscador por nombre del selector de vendedor: contiene el texto, sin distinguir mayúsculas ni
 * acentos. Con texto vacío devuelve todos. `conservarId` mantiene al vendedor ya elegido aunque no
 * coincida, para que el selector no pierda su valor al escribir.
 */
export function filtrarVendedores<T extends { id: string; nombre: string }>(
  vendedores: readonly T[],
  consulta: string,
  conservarId?: string,
): T[] {
  const buscado = sinAcentosEnMinuscula(consulta.trim())
  if (buscado === '') return [...vendedores]
  return vendedores.filter(
    (vendedor) => vendedor.id === conservarId || sinAcentosEnMinuscula(vendedor.nombre).includes(buscado),
  )
}
