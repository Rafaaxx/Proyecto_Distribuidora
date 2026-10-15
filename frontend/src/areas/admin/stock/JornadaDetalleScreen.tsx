import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { accionesDeJornada, PERMISOS_DE_LECTURA_DE_JORNADAS } from '../../../domain/stock/jornadas'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { RecursoNoEncontradoStockError } from '../../../features/stock/errores'
import { useCerrarJornada, useJornada, useLiberarJornada, useRendirJornada } from '../../../features/stock/hooks'
import { formatearFechaHora } from '../../../lib/fecha'
import { ConfirmarTransicionDialogo, InsigniaDeEstadoDeJornada, LiberarJornadaDialogo } from './piezasDeJornada'
import { CLASE_ENLACE, PantallaSinPermiso } from './piezasDeOperacion'

const TITULO = 'Jornada'

type DialogoAbierto = 'rendir' | 'cerrar' | 'liberar' | null

/**
 * Detalle de una jornada y sus acciones (change 15, tareas 14.1 y 14.2; RUT-09, `design.md` D13,
 * D15, D16). "Rendir", "Cerrar" y "Liberar" aparecen solo con su permiso y en el estado que las
 * admite (`accionesDeJornada`, del dominio); una jornada `CERRADA` o `LIBERADA` no ofrece ninguna.
 * "Cargar vehículo" lleva al alta de transferencia con la ubicación como destino (RUT-02).
 */
export function JornadaDetalleScreen() {
  return (
    <SiTienePermiso
      permiso={PERMISOS_DE_LECTURA_DE_JORNADAS}
      fallback={<PantallaSinPermiso titulo={TITULO} mensaje="No tenés permiso para ver las jornadas." />}
    >
      <Detalle />
    </SiTienePermiso>
  )
}

function Detalle() {
  const { jornadaId } = useParams<{ jornadaId: string }>()
  const jornada = useJornada(jornadaId)
  const rendir = useRendirJornada()
  const cerrar = useCerrarJornada()
  const liberar = useLiberarJornada()
  const permisos = usePermisos()
  const [dialogo, setDialogo] = useState<DialogoAbierto>(null)

  if (jornada.isPending) return <p>Cargando…</p>
  if (jornada.isError) {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>
          {jornada.error instanceof RecursoNoEncontradoStockError
            ? 'No se encontró la jornada.'
            : 'No se pudo obtener la jornada.'}
        </Alert>
      </main>
    )
  }

  const datos = jornada.data
  const acciones = accionesDeJornada(datos.estado, permisos.tiene)
  const cerrarDialogo = () => setDialogo(null)
  const releer = () => void jornada.refetch()

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={TITULO}
        acciones={
          <>
            {datos.estado === 'ABIERTA' && (
              <SiTienePermiso permiso="TRANSFERIR_STOCK">
                <Link
                  to={`/admin/stock/transferencias/nueva?destino=${datos.ubicacion_id}`}
                  className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
                >
                  Cargar vehículo
                </Link>
              </SiTienePermiso>
            )}
            {acciones.rendir && <Boton onClick={() => setDialogo('rendir')}>Rendir</Boton>}
            {acciones.cerrar && <Boton onClick={() => setDialogo('cerrar')}>Cerrar</Boton>}
            {acciones.liberar && (
              <span className="inline-flex items-center gap-1">
                <Boton variante="peligro" onClick={() => setDialogo('liberar')}>
                  Liberar
                </Boton>
                <Ayuda clave="stock.liberacion" />
              </span>
            )}
            <Link to="/admin/stock/jornadas" className={CLASE_ENLACE}>
              Volver al listado
            </Link>
          </>
        }
      />

      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p className="flex items-center gap-2">
          Estado: <InsigniaDeEstadoDeJornada estado={datos.estado} />
        </p>
        <p>Ubicación: {datos.ubicacion_nombre}</p>
        <p>
          Abierta el {formatearFechaHora(datos.abierta_en)} por {datos.usuario_nombre ?? ''}
        </p>
        {datos.rendida_en && (
          <p>
            Rendida el {formatearFechaHora(datos.rendida_en)} por {datos.rendida_por_nombre ?? ''}
          </p>
        )}
        {datos.cerrada_en && (
          <p>
            Cerrada el {formatearFechaHora(datos.cerrada_en)} por {datos.cerrada_por_nombre ?? ''}
          </p>
        )}
      </Card>

      {datos.liberada_en && (
        <Card className="flex flex-col gap-1 text-sm text-primary" data-testid="liberacion">
          <h2 className="text-base font-semibold">Liberación</h2>
          <p>Motivo: {datos.motivo_liberacion_nombre ?? datos.motivo_liberacion_id}</p>
          <p>
            Liberada el {formatearFechaHora(datos.liberada_en)} por {datos.liberada_por_nombre ?? ''}
          </p>
          {datos.observacion_liberacion && <p>Observación: {datos.observacion_liberacion}</p>}
        </Card>
      )}

      <ConfirmarTransicionDialogo
        abierto={dialogo === 'rendir'}
        titulo="Rendir jornada"
        texto={`Vas a pasar la jornada de ${datos.ubicacion_nombre} a rendición.`}
        id={datos.id}
        accion="rendir"
        onCerrar={cerrarDialogo}
        onConfirmar={(operationId) => rendir.mutateAsync({ id: datos.id, operationId })}
        onEstadoInvalido={releer}
      />
      <ConfirmarTransicionDialogo
        abierto={dialogo === 'cerrar'}
        titulo="Cerrar jornada"
        texto={`Vas a cerrar la jornada de ${datos.ubicacion_nombre}: la ubicación queda libre para una nueva jornada.`}
        id={datos.id}
        accion="cerrar"
        onCerrar={cerrarDialogo}
        onConfirmar={(operationId) => cerrar.mutateAsync({ id: datos.id, operationId })}
        onEstadoInvalido={releer}
      />
      <LiberarJornadaDialogo
        abierto={dialogo === 'liberar'}
        id={datos.id}
        onCerrar={cerrarDialogo}
        onConfirmar={(motivoId, observacion, operationId) =>
          liberar.mutateAsync({
            id: datos.id,
            motivo_id: motivoId,
            ...(observacion === undefined ? {} : { observacion }),
            operationId,
          })
        }
        onEstadoInvalido={releer}
      />
    </main>
  )
}

export default JornadaDetalleScreen
