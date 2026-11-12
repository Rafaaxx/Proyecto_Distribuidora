/**
 * Un envío cortado por la red antes de recibir respuesta: el archivo, el tipo y el
 * `Operation-Id` con el que se mandó. Si el usuario reintenta lo mismo, se reenvía con ese
 * mismo valor para que el servidor lo trate como la misma operación (INV-06, SYN-02).
 */
export interface EnvioPendiente {
  tipo: string
  archivo: File
  operationId: string
}

/**
 * `Operation-Id` del próximo envío: el del pendiente si es el mismo tipo y el mismo archivo
 * seleccionado (misma instancia de `File`), y uno nuevo si cambió cualquiera de los dos o si
 * no hay pendiente (otro archivo, o el mismo corregido y vuelto a elegir).
 */
export function resolverOperationId(
  pendiente: EnvioPendiente | null,
  tipo: string,
  archivo: File,
  generar: () => string,
): string {
  if (pendiente !== null && pendiente.tipo === tipo && pendiente.archivo === archivo) {
    return pendiente.operationId
  }
  return generar()
}
