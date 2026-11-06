import { textoDeResolucion, type ResolucionDeAviso as DatosDeResolucion } from '../../../domain/revision/resolucion'

/**
 * La resolución de una observación en el detalle de su operación (change 25, tarea 15.2; D11; SYN-08): «Resuelta
 * por {usuario} el {fecha}: {comentario}». Solo lectura; una observación pendiente no muestra nada.
 */
export function ResolucionDeAviso({ observacion }: { observacion: DatosDeResolucion & { estado: string } }) {
  if (observacion.estado !== 'RESUELTA') return null
  return <span className="text-primary/70">{textoDeResolucion(observacion)}</span>
}
