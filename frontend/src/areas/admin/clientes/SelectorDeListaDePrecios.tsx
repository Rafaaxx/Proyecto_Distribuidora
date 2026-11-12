import type { UseFormRegisterReturn } from 'react-hook-form'

import { Campo } from '../../../components/ui/Field'
import { useOpcionesDeListas } from '../../../features/precios/hooks'

export const OPCION_PREDETERMINADA = 'Predeterminada de la organización'
export const OPCION_LISTA_NO_ACTIVA = 'Lista asignada (no activa)'

/**
 * Lista de precios asignada al cliente (change 13, tarea 13.4; CLI-01, D11). Ofrece las listas
 * activas (`GET /precios/listas/opciones`, abierto a `GESTIONAR_CLIENTES`: no hace falta
 * `GESTIONAR_LISTAS`) y la predeterminada de la organización, que se manda como `null`. Si la
 * lista que ya tiene el cliente no está entre las activas se muestra igual, para que guardar la
 * ficha no la cambie en silencio. Si las opciones no se pueden obtener, queda la predeterminada.
 */
export function SelectorDeListaDePrecios({
  registro,
  listaAsignadaId,
  error,
}: {
  registro: UseFormRegisterReturn
  /** La lista que el cliente ya tiene asignada (edición), o `null`. */
  listaAsignadaId: string | null
  error?: string
}) {
  const opciones = useOpcionesDeListas()
  const listas = opciones.data?.items ?? []
  const asignadaFueraDeLasActivas =
    listaAsignadaId !== null && opciones.isSuccess && !listas.some((lista) => lista.id === listaAsignadaId)

  return (
    <Campo id="lista_precio_id" etiqueta="Lista de precios" error={error}>
      {/* La clave hace que el selector se monte de nuevo cuando llegan las opciones: así toma el valor del formulario. */}
      <select
        key={opciones.isPending ? 'cargando' : 'listo'}
        id="lista_precio_id"
        className="rounded-md border border-border px-2 py-1 text-sm"
        {...registro}
      >
        <option value="">{OPCION_PREDETERMINADA}</option>
        {listas.map((lista) => (
          <option key={lista.id} value={lista.id}>
            {lista.nombre}
          </option>
        ))}
        {asignadaFueraDeLasActivas && <option value={listaAsignadaId}>{OPCION_LISTA_NO_ACTIVA}</option>}
      </select>
    </Campo>
  )
}
