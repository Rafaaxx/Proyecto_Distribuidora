import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import {
  ESTADOS_DE_JORNADA,
  PERMISOS_DE_LECTURA_DE_JORNADAS,
  etiquetaDeEstadoDeJornada,
  fusionarUsuarios,
  type UsuarioConocido,
} from '../../../domain/stock/jornadas'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { JornadaDelListado } from '../../../features/stock/api'
import type { FiltrosJornadas } from '../../../features/stock/claves'
import { useJornadas, useUbicaciones } from '../../../features/stock/hooks'
import { formatearFechaHora } from '../../../lib/fecha'
import { InsigniaDeEstadoDeJornada } from './piezasDeJornada'
import { CLASE_CONTROL, CLASE_ENLACE, PantallaSinPermiso } from './piezasDeOperacion'

const TITULO = 'Jornadas'

/**
 * Listado de jornadas (change 15, tarea 14.1; `design.md` D15, D16): filtros de ubicación, usuario,
 * estado y fechas, estado de cada una y acceso al detalle y a la apertura. Lo ve quien tiene
 * `ABRIR_JORNADA`, `RENDIR_JORNADA` o `LIBERAR_UBICACION`, decidido con `<SiTienePermiso>`.
 */
export function JornadasListScreen() {
  return (
    <SiTienePermiso
      permiso={PERMISOS_DE_LECTURA_DE_JORNADAS}
      fallback={<PantallaSinPermiso titulo={TITULO} mensaje="No tenés permiso para ver las jornadas." />}
    >
      <Listado />
    </SiTienePermiso>
  )
}

function Listado() {
  const [filtros, setFiltros] = useState<FiltrosJornadas>({})
  const [usuarios, setUsuarios] = useState<UsuarioConocido[]>([])
  const ubicaciones = useUbicaciones(undefined)
  const jornadas = useJornadas(filtros)
  const opcionesDeUbicacion = ubicaciones.data?.pages.flatMap((pagina) => pagina.items) ?? []
  const filas = jornadas.data?.pages.flatMap((pagina) => pagina.items) ?? []

  // El filtro de usuario recuerda a quienes ya aparecieron, aunque el filtro actual los oculte.
  const fusion = fusionarUsuarios(usuarios, filas)
  if (fusion.length !== usuarios.length) setUsuarios(fusion)

  const cambiar = (cambios: Partial<FiltrosJornadas>) => {
    const siguiente = { ...filtros, ...cambios }
    setFiltros({
      ...(siguiente.ubicacionId ? { ubicacionId: siguiente.ubicacionId } : {}),
      ...(siguiente.usuarioId ? { usuarioId: siguiente.usuarioId } : {}),
      ...(siguiente.estado ? { estado: siguiente.estado } : {}),
      ...(siguiente.desde ? { desde: siguiente.desde } : {}),
      ...(siguiente.hasta ? { hasta: siguiente.hasta } : {}),
    })
  }

  const columnas: ColumnaTabla<JornadaDelListado>[] = [
    { clave: 'ubicacion', encabezado: 'Ubicación', render: (j) => j.ubicacion_nombre },
    { clave: 'usuario', encabezado: 'Usuario', render: (j) => j.usuario_nombre ?? '' },
    { clave: 'abierta', encabezado: 'Abierta', render: (j) => formatearFechaHora(j.abierta_en) },
    { clave: 'estado', encabezado: 'Estado', render: (j) => <InsigniaDeEstadoDeJornada estado={j.estado} /> },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (j) => (
        <Link to={`/admin/stock/jornadas/${j.id}`} className={CLASE_ENLACE}>
          Ver detalle
        </Link>
      ),
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={TITULO}
        acciones={
          <>
            <SiTienePermiso permiso="ABRIR_JORNADA">
              <Link
                to="/admin/stock/jornadas/abrir"
                className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
              >
                Abrir jornada
              </Link>
            </SiTienePermiso>
            <Link to="/admin/stock" className={CLASE_ENLACE}>
              Volver a las ubicaciones
            </Link>
          </>
        }
      />

      <Card>
        <form onSubmit={(evento) => evento.preventDefault()} role="search" className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm text-primary">
            Ubicación
            <select
              className={CLASE_CONTROL}
              value={filtros.ubicacionId ?? ''}
              onChange={(evento) => cambiar({ ubicacionId: evento.target.value })}
            >
              <option value="">Todas</option>
              {opcionesDeUbicacion.map((ubicacion) => (
                <option key={ubicacion.id} value={ubicacion.id}>
                  {ubicacion.nombre}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm text-primary">
            Usuario
            <select
              className={CLASE_CONTROL}
              value={filtros.usuarioId ?? ''}
              onChange={(evento) => cambiar({ usuarioId: evento.target.value })}
            >
              <option value="">Todos</option>
              {usuarios.map((usuario) => (
                <option key={usuario.id} value={usuario.id}>
                  {usuario.nombre}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm text-primary">
            Estado
            <select
              className={CLASE_CONTROL}
              value={filtros.estado ?? ''}
              onChange={(evento) => cambiar({ estado: evento.target.value })}
            >
              <option value="">Todos</option>
              {ESTADOS_DE_JORNADA.map((estado) => (
                <option key={estado} value={estado}>
                  {etiquetaDeEstadoDeJornada(estado)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm text-primary">
            Desde
            <input
              type="date"
              className={CLASE_CONTROL}
              value={filtros.desde ?? ''}
              onChange={(evento) => cambiar({ desde: evento.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-primary">
            Hasta
            <input
              type="date"
              className={CLASE_CONTROL}
              value={filtros.hasta ?? ''}
              onChange={(evento) => cambiar({ hasta: evento.target.value })}
            />
          </label>
        </form>
      </Card>

      {jornadas.isPending && <p>Cargando…</p>}
      {jornadas.isError && <Alert>No se pudieron obtener las jornadas.</Alert>}
      {jornadas.isSuccess && filas.length === 0 && (
        <p className="text-sm text-primary/70">No hay jornadas para mostrar.</p>
      )}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(j) => j.id} />
        </Card>
      )}
      {jornadas.hasNextPage && (
        <div>
          <Boton
            type="button"
            variante="secundario"
            disabled={jornadas.isFetchingNextPage}
            onClick={() => void jornadas.fetchNextPage()}
          >
            Cargar más
          </Boton>
        </div>
      )}
    </main>
  )
}

export default JornadasListScreen
