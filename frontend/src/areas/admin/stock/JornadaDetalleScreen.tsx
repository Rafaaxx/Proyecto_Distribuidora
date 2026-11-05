import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { accionesDeJornada, PERMISOS_DE_LECTURA_DE_JORNADAS } from '../../../domain/stock/jornadas'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { RecursoNoEncontradoStockError } from '../../../features/stock/errores'
import { useCerrarJornada, useJornada, useLiberarJornada } from '../../../features/stock/hooks'
import { formatearFechaHora, formatearHora } from '../../../lib/fecha'
import { CierreDeJornadaDialogo, type DevolucionRealizada } from './CierreDeJornadaDialogo'
import { InsigniaDeEstadoDeJornada, LiberarJornadaDialogo } from './piezasDeJornada'
import { ResumenDeJornada } from './ResumenDeJornada'
import { CLASE_ENLACE, PantallaSinPermiso } from './piezasDeOperacion'

const TITULO = 'Jornada'

type DialogoAbierto = 'cerrar' | 'liberar' | null

/**
 * Detalle de una jornada y sus acciones (change 15, tareas 14.1 y 14.2; RUT-09, `design.md` D13,
 * D15, D16). "Rendir", "Cerrar" y "Liberar" aparecen solo con su permiso y en el estado que las
 * admite (`accionesDeJornada`, del dominio); una jornada `CERRADA` o `LIBERADA` no ofrece ninguna.
 * "Cargar vehículo" lleva al alta de transferencia con la ubicación como destino (RUT-02).
 *
 * Change 24 (tarea 13.1; D4, D6, D8, D9): muestra la entrega del vendedor o su falta; "Rendir"
 * lleva a la pantalla de conteo y queda deshabilitado sin la entrega (RUT-05); "Cerrar" abre el
 * diálogo con la devolución del remanente; y el resumen de la jornada (RUT-07) va debajo.
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
  const navigate = useNavigate()
  const cerrar = useCerrarJornada()
  const liberar = useLiberarJornada()
  const permisos = usePermisos()
  const [dialogo, setDialogo] = useState<DialogoAbierto>(null)
  const [devuelto, setDevuelto] = useState<DevolucionRealizada | null>(null)

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
  const entregada = Boolean(datos.entregada_en)

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
            {acciones.rendir && (
              <Boton disabled={!entregada} onClick={() => navigate(`/admin/stock/jornadas/${datos.id}/rendicion`)}>
                Rendir
              </Boton>
            )}
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
        {datos.entregada_en ? (
          <p className="flex items-center gap-1">
            Entregada por el vendedor a las {formatearHora(datos.entregada_en)}.
            <Ayuda clave="stock.entregaDelDia" />
          </p>
        ) : (
          datos.estado === 'ABIERTA' && (
            <p className="flex items-center gap-1">
              El vendedor todavía no terminó el día en el teléfono.
              <Ayuda clave="stock.entregaDelDia" />
            </p>
          )
        )}
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

      {devuelto && (
        <Card className="flex flex-col gap-1 text-sm text-primary" data-testid="devolucion-del-remanente">
          <p>{devuelto.texto}</p>
          <Link to={`/admin/stock/transferencias/${devuelto.transferenciaId}`} className={CLASE_ENLACE}>
            Ver transferencia
          </Link>
        </Card>
      )}

      <ResumenDeJornada jornadaId={datos.id} ubicacionId={datos.ubicacion_id} />

      <CierreDeJornadaDialogo
        abierto={dialogo === 'cerrar'}
        jornadaId={datos.id}
        ubicacionId={datos.ubicacion_id}
        ubicacionNombre={datos.ubicacion_nombre}
        puedeDevolver={permisos.tiene('TRANSFERIR_STOCK')}
        onCerrar={cerrarDialogo}
        onConfirmar={(devolucion, operationId) =>
          cerrar.mutateAsync({ id: datos.id, ...(devolucion === null ? {} : { devolucion }), operationId })
        }
        onCerrada={setDevuelto}
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
