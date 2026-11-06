import { useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import {
  CODIGOS_DE_OBSERVACION,
  detalleDeObservacion,
  etiquetaDeObservacion,
  nombresDeAviso,
} from '../../../domain/revision/detalleDeObservacion'
import {
  OPCIONES_DE_TIPO,
  puedeVerOperacion,
  rutaDeOperacion,
  tituloDeOperacion,
} from '../../../domain/revision/operaciones'
import {
  textoDeConfirmacionDeAvisos,
  textoDeResolucion,
  textoDeResolverAvisos,
} from '../../../domain/revision/resolucion'
import { formatearMonto } from '../../../domain/cuentas-corrientes/presentacion'
import { usePermisos } from '../../../features/identidad/usePermisos'
import type { ObservacionDeBandeja, OperacionObservada } from '../../../features/revision/api'
import type { FiltrosDeObservaciones } from '../../../features/revision/claves'
import { mensajeDeErrorDeRevision } from '../../../features/revision/errores'
import { useObservaciones, useResolverObservaciones } from '../../../features/revision/hooks'
import { formatearFechaHora } from '../../../lib/fecha'
import { CLASE_CONTROL, DialogoDeResolucion } from './DialogoDeResolucion'

const ESTADOS: readonly { valor: NonNullable<FiltrosDeObservaciones['estado']>; etiqueta: string }[] = [
  { valor: 'PENDIENTE', etiqueta: 'Pendientes' },
  { valor: 'RESUELTA', etiqueta: 'Resueltas' },
  { valor: 'TODAS', etiqueta: 'Todas' },
]

/**
 * Pestaña «Observaciones» de `/admin/revision` (change 25, tarea 13.2; D1, D3, D11; SYN-07, SYN-08, INV-01): una
 * fila por operación observada con su resumen y sus avisos (etiqueta y detalle legible), casilla por aviso
 * pendiente y por operación, «Resolver {N} avisos» con comentario y confirmación, y «Ver» a la pantalla de la
 * operación si el usuario la puede abrir. Resolver no modifica la operación (SYN-08). La jornada y el código
 * pueden llegar por la URL (`?jornada=`, `?codigo=`), por ejemplo desde el aviso del inicio.
 */
export function ObservacionesScreen() {
  const [parametros, setParametros] = useSearchParams()
  const permisos = usePermisos()
  const jornadaId = parametros.get('jornada') ?? undefined
  const [local, setLocal] = useState<FiltrosDeObservaciones>(() => ({
    estado: 'PENDIENTE',
    codigo: parametros.get('codigo') ?? undefined,
  }))
  const filtros: FiltrosDeObservaciones = { ...local, jornadaId }
  const observaciones = useObservaciones(filtros)
  const resolver = useResolverObservaciones()
  const [elegidas, setElegidas] = useState<ReadonlySet<string>>(new Set())
  const [enDialogo, setEnDialogo] = useState<string[] | null>(null)

  const operaciones = observaciones.data?.pages.flatMap((pagina) => pagina.items) ?? []
  const pendientesActuales = new Set(
    operaciones.flatMap((o) => o.observaciones.filter((a) => a.estado === 'PENDIENTE').map((a) => a.id)),
  )
  // Lo que ya no está pendiente (porque otra persona lo resolvió y la lista se recargó) deja de estar elegido.
  const ids = [...elegidas].filter((id) => pendientesActuales.has(id)).sort()
  const usuarios = new Map(operaciones.map((o) => [o.usuario_id, o.usuario_nombre ?? o.usuario_id] as const))
  const vendedores = [...usuarios.entries()]
  if (local.usuarioId && !usuarios.has(local.usuarioId)) vendedores.push([local.usuarioId, local.usuarioId])

  const cambiar = (cambio: Partial<FiltrosDeObservaciones>) => setLocal((actual) => ({ ...actual, ...cambio }))
  const quitarJornada = () => {
    const nuevos = new URLSearchParams(parametros)
    nuevos.delete('jornada')
    setParametros(nuevos)
  }
  const alternar = (idsAAlternar: readonly string[]) =>
    setElegidas((actual) => {
      const nuevo = new Set(actual)
      const todasElegidas = idsAAlternar.every((id) => nuevo.has(id))
      for (const id of idsAAlternar) {
        if (todasElegidas) nuevo.delete(id)
        else nuevo.add(id)
      }
      return nuevo
    })

  if (observaciones.isError) {
    return <Alert>{mensajeDeErrorDeRevision(observaciones.error)}</Alert>
  }

  const columnas: ColumnaTabla<OperacionObservada>[] = [
    {
      clave: 'operacion',
      encabezado: 'Operación',
      render: (operacion) => {
        const titulo = tituloDeOperacion(operacion.operacion_tipo, operacion.resumen)
        const pendientes = operacion.observaciones.filter((a) => a.estado === 'PENDIENTE').map((a) => a.id)
        return (
          <div className="flex items-start gap-2">
            {pendientes.length > 0 && (
              <input
                type="checkbox"
                aria-label={`Elegir todos los avisos de ${titulo}`}
                checked={pendientes.every((id) => elegidas.has(id))}
                onChange={() => alternar(pendientes)}
              />
            )}
            <div className="flex flex-col">
              <span className="font-medium">{titulo}</span>
              {operacion.resumen?.tercero && <span className="text-primary/70">{operacion.resumen.tercero}</span>}
              {operacion.resumen?.total && <span className="text-primary/70">{formatearMonto(operacion.resumen.total)}</span>}
            </div>
          </div>
        )
      },
    },
    { clave: 'vendedor', encabezado: 'Vendedor', render: (operacion) => operacion.usuario_nombre ?? '' },
    { clave: 'llego', encabezado: 'Llegó', render: (operacion) => formatearFechaHora(operacion.registered_at) },
    {
      clave: 'avisos',
      encabezado: 'Avisos',
      render: (operacion) => (
        <ul className="flex flex-col gap-2">
          {operacion.observaciones.map((aviso) => (
            <Aviso
              key={aviso.id}
              aviso={aviso}
              elegido={elegidas.has(aviso.id)}
              alAlternar={() => alternar([aviso.id])}
              nombres={{ usuarios }}
            />
          ))}
        </ul>
      ),
    },
    {
      clave: 'acciones',
      encabezado: 'Acciones',
      render: (operacion) => {
        const ruta = rutaDeOperacion(operacion.operacion_tipo, operacion.operacion_id)
        if (ruta === null || !puedeVerOperacion(operacion.operacion_tipo, permisos.tiene)) return null
        return (
          <Link to={ruta} className="text-sm text-primary/70 hover:text-primary hover:underline">
            Ver
          </Link>
        )
      },
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3">
        <form onSubmit={(evento) => evento.preventDefault()} role="search" className="flex flex-wrap items-end gap-3">
          <Filtro id="filtro-estado" etiqueta="Estado">
            <select
              id="filtro-estado"
              className={CLASE_CONTROL}
              value={local.estado ?? 'PENDIENTE'}
              onChange={(e) => cambiar({ estado: e.target.value as FiltrosDeObservaciones['estado'] })}
            >
              {ESTADOS.map((estado) => (
                <option key={estado.valor} value={estado.valor}>
                  {estado.etiqueta}
                </option>
              ))}
            </select>
          </Filtro>
          <Filtro id="filtro-codigo" etiqueta="Código">
            <select
              id="filtro-codigo"
              className={CLASE_CONTROL}
              value={local.codigo ?? ''}
              onChange={(e) => cambiar({ codigo: e.target.value || undefined })}
            >
              <option value="">Todos</option>
              {CODIGOS_DE_OBSERVACION.map((codigo) => (
                <option key={codigo} value={codigo}>
                  {etiquetaDeObservacion(codigo)}
                </option>
              ))}
            </select>
          </Filtro>
          <Filtro id="filtro-tipo" etiqueta="Tipo de operación">
            <select
              id="filtro-tipo"
              className={CLASE_CONTROL}
              value={local.tipo ?? ''}
              onChange={(e) => cambiar({ tipo: e.target.value || undefined })}
            >
              <option value="">Todos</option>
              {OPCIONES_DE_TIPO.map((tipo) => (
                <option key={tipo.valor} value={tipo.valor}>
                  {tipo.etiqueta}
                </option>
              ))}
            </select>
          </Filtro>
          <Filtro id="filtro-vendedor" etiqueta="Vendedor">
            <select
              id="filtro-vendedor"
              className={CLASE_CONTROL}
              value={local.usuarioId ?? ''}
              onChange={(e) => cambiar({ usuarioId: e.target.value || undefined })}
            >
              <option value="">Todos</option>
              {vendedores.map(([id, nombre]) => (
                <option key={id} value={id}>
                  {nombre}
                </option>
              ))}
            </select>
          </Filtro>
          <Filtro id="filtro-desde" etiqueta="Desde">
            <input
              id="filtro-desde"
              type="date"
              className={CLASE_CONTROL}
              value={local.desde ?? ''}
              onChange={(e) => cambiar({ desde: e.target.value || undefined })}
            />
          </Filtro>
          <Filtro id="filtro-hasta" etiqueta="Hasta">
            <input
              id="filtro-hasta"
              type="date"
              className={CLASE_CONTROL}
              value={local.hasta ?? ''}
              onChange={(e) => cambiar({ hasta: e.target.value || undefined })}
            />
          </Filtro>
        </form>
        {jornadaId && (
          <span className="flex items-center gap-2 text-sm text-primary">
            Jornada
            <Boton variante="secundario" onClick={quitarJornada}>
              Quitar filtro de jornada
            </Boton>
          </span>
        )}
        <div>
          <Boton disabled={ids.length === 0} onClick={() => setEnDialogo(ids)}>
            {ids.length === 0 ? 'Resolver' : textoDeResolverAvisos(ids.length)}
          </Boton>
        </div>
      </Card>

      {observaciones.isPending && <p>Cargando…</p>}
      {observaciones.isSuccess && operaciones.length === 0 && (
        <p className="text-sm text-primary/70">Sin avisos pendientes.</p>
      )}
      {operaciones.length > 0 && (
        <Card>
          <Tabla
            filas={operaciones}
            columnas={columnas}
            obtenerClave={(operacion) => `${operacion.operacion_tipo}:${operacion.operacion_id}`}
            etiqueta="Observaciones"
          />
        </Card>
      )}
      {observaciones.hasNextPage && (
        <div>
          <Boton
            variante="secundario"
            disabled={observaciones.isFetchingNextPage}
            onClick={() => void observaciones.fetchNextPage()}
          >
            Cargar más
          </Boton>
        </div>
      )}

      {enDialogo !== null && (
        <DialogoDeResolucion
          titulo={textoDeResolverAvisos(enDialogo.length)}
          confirmacion={textoDeConfirmacionDeAvisos(enDialogo.length)}
          contenido={enDialogo}
          onCerrar={() => {
            setEnDialogo(null)
            setElegidas(new Set())
          }}
          enviar={(comentario, operationId) =>
            resolver.mutateAsync({ observaciones: enDialogo, comentario, operationId })
          }
          onDesactualizado={() => void observaciones.refetch()}
          codigosDeDesactualizado={['OBSERVACION_YA_RESUELTA']}
        />
      )}
    </div>
  )
}

function Filtro({ id, etiqueta, children }: { id: string; etiqueta: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm text-primary">
        {etiqueta}
      </label>
      {children}
    </div>
  )
}

interface AvisoProps {
  aviso: ObservacionDeBandeja
  elegido: boolean
  alAlternar: () => void
  nombres: { usuarios: ReadonlyMap<string, string> }
}

function Aviso({ aviso, elegido, alAlternar, nombres }: AvisoProps) {
  const etiqueta = etiquetaDeObservacion(aviso.codigo)
  const lineas = detalleDeObservacion(aviso.codigo, aviso.detalle, nombresDeAviso(aviso.detalle, aviso.nombres, nombres))
  return (
    <li className="flex items-start gap-2">
      {aviso.estado === 'PENDIENTE' && (
        <input type="checkbox" aria-label={`Elegir aviso ${etiqueta}`} checked={elegido} onChange={alAlternar} />
      )}
      <div className="flex flex-col">
        <span className="font-medium">{etiqueta}</span>
        {lineas.map((linea) => (
          <span key={linea} className="text-primary/70">
            {linea}
          </span>
        ))}
        {aviso.estado === 'RESUELTA' && <span className="text-primary/70">{textoDeResolucion(aviso)}</span>}
      </div>
    </li>
  )
}

export default ObservacionesScreen
