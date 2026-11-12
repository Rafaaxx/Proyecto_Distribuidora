import { useState } from 'react'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import {
  useDefinirListaPredeterminada,
  useListaPredeterminada,
  useOpcionesDeListas,
} from '../../../features/precios/hooks'
import { useOperationIdDeEnvio } from '../../../features/precios/useOperationIdDeEnvio'
import { AVISO_SIN_CONEXION, describirError, estaSinConexion } from '../precios/errores'

const TITULO = 'Lista de precios predeterminada'
const SIN_PERMISO = 'No tenés permiso para administrar la lista predeterminada.'

/**
 * Elección de la lista de precios predeterminada de la organización (change 13, tarea 13.5; `01`
 * §4, PRC-20, D11). Solo con `ADMIN_CONFIGURACION` (ADR-027): sin él no se monta nada y no se
 * pide nada. Mientras no haya una lista predeterminada, advierte que los clientes sin lista
 * asignada no tienen precio. Solo admite una lista activa; el servidor valida igual (SEG-06).
 */
export function ListaPredeterminadaScreen() {
  return (
    <SiTienePermiso
      permiso="ADMIN_CONFIGURACION"
      fallback={
        <main className="flex flex-col gap-4">
          <PageHeader titulo={TITULO} />
          <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
        </main>
      }
    >
      <ListaPredeterminada />
    </SiTienePermiso>
  )
}

function ListaPredeterminada() {
  const actual = useListaPredeterminada()

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={TITULO} />
      {actual.isPending && <p className="text-sm text-primary/70">Cargando…</p>}
      {actual.isError && <Alert>No se pudo obtener la lista predeterminada.</Alert>}
      {actual.isSuccess && (
        <>
          {actual.data.lista_id === null ? (
            <Alert>
              La organización no tiene una lista de precios predeterminada: los clientes sin lista asignada no tienen
              precio.
            </Alert>
          ) : (
            <Card className="text-sm text-primary">
              <p>
                Lista predeterminada actual: <strong>{actual.data.lista_nombre}</strong>
                {actual.data.activa === false ? ' (inactiva)' : ''}
              </p>
            </Card>
          )}
          <EleccionDeLista listaActualId={actual.data.lista_id} />
        </>
      )}
    </main>
  )
}

function EleccionDeLista({ listaActualId }: { listaActualId: string | null }) {
  const opciones = useOpcionesDeListas()
  const definir = useDefinirListaPredeterminada()
  const [elegida, setElegida] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const seleccion = elegida ?? listaActualId ?? ''
  const operationId = useOperationIdDeEnvio({ accion: 'LISTA_PRECIO_PREDETERMINADA_DEFINIR', listaId: seleccion })

  const guardar = async () => {
    setError(null)
    if (seleccion === '') {
      setError('Elegí una lista.')
      return
    }
    if (estaSinConexion()) {
      setError(AVISO_SIN_CONEXION)
      return
    }
    try {
      await definir.mutateAsync({ lista_id: seleccion, operationId: operationId.obtener() })
      operationId.completar()
      setElegida(null)
    } catch (e) {
      setError(describirError(e).mensaje)
    }
  }

  return (
    <Card className="flex flex-wrap items-end gap-3">
      <Campo id="lista-predeterminada" etiqueta="Lista predeterminada" error={error ?? undefined}>
        <select
          key={opciones.isPending ? 'cargando' : 'listo'}
          id="lista-predeterminada"
          className="rounded-md border border-border px-2 py-1 text-sm"
          value={seleccion}
          onChange={(evento) => setElegida(evento.target.value)}
        >
          <option value="">Sin elegir</option>
          {(opciones.data?.items ?? []).map((lista) => (
            <option key={lista.id} value={lista.id}>
              {lista.nombre}
            </option>
          ))}
        </select>
      </Campo>
      <Boton disabled={definir.isPending} onClick={() => void guardar()}>
        Guardar lista predeterminada
      </Boton>
    </Card>
  )
}

export default ListaPredeterminadaScreen
