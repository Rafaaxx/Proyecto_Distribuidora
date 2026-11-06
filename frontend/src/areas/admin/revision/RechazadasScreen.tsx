import { useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { formatearMonto } from '../../../domain/cuentas-corrientes/presentacion'
import {
  OPCIONES_DE_TIPO_DE_COMANDO,
  etiquetaDeTipoDeComando,
  motivoDeRechazo,
  tipoDeVinculoPermitido,
} from '../../../domain/revision/rechazos'
import { textoDeResolucion } from '../../../domain/revision/resolucion'
import { usePermisos } from '../../../features/identidad/usePermisos'
import type { Rechazo } from '../../../features/revision/api'
import type { FiltrosDeRechazos } from '../../../features/revision/claves'
import { mensajeDeErrorDeRevision } from '../../../features/revision/errores'
import { useRechazos, useResolverRechazo } from '../../../features/revision/hooks'
import { formatearFechaHora } from '../../../lib/fecha'
import { CLASE_CONTROL, DialogoDeResolucion } from './DialogoDeResolucion'
import { VinculoDeRechazo, type Vinculo } from './VinculoDeRechazo'

const ESTADOS: readonly { valor: NonNullable<FiltrosDeRechazos['estado']>; etiqueta: string }[] = [
  { valor: 'PENDIENTE', etiqueta: 'Pendientes' },
  { valor: 'RESUELTO', etiqueta: 'Resueltas' },
  { valor: 'TODOS', etiqueta: 'Todas' },
]

const ETIQUETA_DE_CUARENTENA = 'Teléfono dado de baja'
const ETIQUETA_DE_RECHAZO = 'Rechazada'
const TEXTO_DE_CONFIRMACION = '¿Resolver esta operación rechazada? No se puede deshacer.'

/** Permisos con los que se abre la pantalla de lo que se vincula (el listado de ventas y el de cobranzas). */
const PERMISOS_PARA_VINCULAR = {
  VENTA: ['VENDER', 'ANULAR_VENTA'],
  COBRANZA: ['REGISTRAR_COBRANZA', 'ANULAR_COBRANZA'],
} as const

/**
 * Pestaña «Rechazadas» de `/admin/revision` (change 25, tarea 14.1; D6, D7, D11; SYN-06, SYN-08, SYN-09): lo que el
 * teléfono envió y el sistema no aceptó, y lo que llegó de un teléfono dado de baja (cuarentena). Nada se reenvía:
 * si la operación ocurrió, se carga con conexión y se vincula al resolver; si no ocurrió, se resuelve sin vincular.
 * La jornada puede llegar por la URL (`?jornada=`), por ejemplo desde la pantalla de conteo.
 */
export function RechazadasScreen() {
  const [parametros, setParametros] = useSearchParams()
  const jornadaId = parametros.get('jornada') ?? undefined
  const [local, setLocal] = useState<FiltrosDeRechazos>({ estado: 'PENDIENTE' })
  const filtros: FiltrosDeRechazos = { ...local, jornadaId }
  const rechazos = useRechazos(filtros)
  const [resolviendo, setResolviendo] = useState<Rechazo | null>(null)

  const filas = rechazos.data?.pages.flatMap((pagina) => pagina.items) ?? []
  const usuarios = new Map(filas.map((fila) => [fila.usuario_id, fila.usuario_nombre ?? fila.usuario_id] as const))
  const vendedores = [...usuarios.entries()]
  if (local.usuarioId && !usuarios.has(local.usuarioId)) vendedores.push([local.usuarioId, local.usuarioId])

  const cambiar = (cambio: Partial<FiltrosDeRechazos>) => setLocal((actual) => ({ ...actual, ...cambio }))
  const quitarJornada = () => {
    const nuevos = new URLSearchParams(parametros)
    nuevos.delete('jornada')
    setParametros(nuevos)
  }

  if (rechazos.isError) {
    return <Alert>{mensajeDeErrorDeRevision(rechazos.error)}</Alert>
  }

  const columnas: ColumnaTabla<Rechazo>[] = [
    {
      clave: 'tipo',
      encabezado: 'Tipo de operación',
      render: (fila) => (
        <div className="flex flex-col gap-1">
          <span className="font-medium">{etiquetaDeTipoDeComando(fila.tipo)}</span>
          <span className="flex items-center gap-1">
            <Badge variante={fila.origen === 'CUARENTENA' ? 'negativo' : 'neutral'}>
              {fila.origen === 'CUARENTENA' ? ETIQUETA_DE_CUARENTENA : ETIQUETA_DE_RECHAZO}
            </Badge>
            {fila.origen === 'CUARENTENA' && <Ayuda clave="revision.cuarentena" />}
          </span>
        </div>
      ),
    },
    { clave: 'vendedor', encabezado: 'Vendedor', render: (fila) => fila.usuario_nombre ?? '' },
    {
      clave: 'jornada',
      encabezado: 'Jornada',
      render: (fila) => (fila.jornada_id === null ? '' : fila.jornada_id.slice(0, 8)),
    },
    { clave: 'llego', encabezado: 'Llegó', render: (fila) => formatearFechaHora(fila.recibido_en) },
    {
      clave: 'motivo',
      encabezado: 'Motivo del rechazo',
      render: (fila) => (
        <div className="flex flex-col gap-1">
          <span>{motivoDeRechazo(fila.tipo, fila.codigo)}</span>
          {fila.aceptada_despues && <Badge variante="positivo">Aceptada después</Badge>}
        </div>
      ),
    },
    { clave: 'envio', encabezado: 'Lo que envió el teléfono', render: (fila) => <LoQueEnvio fila={fila} /> },
    {
      clave: 'resolucion',
      encabezado: 'Resolución',
      render: (fila) =>
        fila.estado === 'RESUELTO' ? (
          <div className="flex flex-col gap-1">
            <span>{textoDeResolucion(fila)}</span>
            <VinculoResuelto fila={fila} />
          </div>
        ) : (
          <Boton variante="secundario" onClick={() => setResolviendo(fila)}>
            Resolver
          </Boton>
        ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3">
        <form onSubmit={(evento) => evento.preventDefault()} role="search" className="flex flex-wrap items-end gap-3">
          <Filtro id="rechazos-estado" etiqueta="Estado">
            <select
              id="rechazos-estado"
              className={CLASE_CONTROL}
              value={local.estado ?? 'PENDIENTE'}
              onChange={(e) => cambiar({ estado: e.target.value as FiltrosDeRechazos['estado'] })}
            >
              {ESTADOS.map((estado) => (
                <option key={estado.valor} value={estado.valor}>
                  {estado.etiqueta}
                </option>
              ))}
            </select>
          </Filtro>
          <Filtro id="rechazos-origen" etiqueta="Origen">
            <select
              id="rechazos-origen"
              className={CLASE_CONTROL}
              value={local.origen ?? ''}
              onChange={(e) => cambiar({ origen: (e.target.value || undefined) as FiltrosDeRechazos['origen'] })}
            >
              <option value="">Todos</option>
              <option value="RECHAZO">{ETIQUETA_DE_RECHAZO}</option>
              <option value="CUARENTENA">{ETIQUETA_DE_CUARENTENA}</option>
            </select>
          </Filtro>
          <Filtro id="rechazos-tipo" etiqueta="Tipo de operación">
            <select
              id="rechazos-tipo"
              className={CLASE_CONTROL}
              value={local.tipo ?? ''}
              onChange={(e) => cambiar({ tipo: e.target.value || undefined })}
            >
              <option value="">Todos</option>
              {OPCIONES_DE_TIPO_DE_COMANDO.map((tipo) => (
                <option key={tipo.valor} value={tipo.valor}>
                  {tipo.etiqueta}
                </option>
              ))}
            </select>
          </Filtro>
          <Filtro id="rechazos-vendedor" etiqueta="Vendedor">
            <select
              id="rechazos-vendedor"
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
        </form>
        {jornadaId && (
          <span className="flex items-center gap-2 text-sm text-primary">
            Jornada
            <Boton variante="secundario" onClick={quitarJornada}>
              Quitar filtro de jornada
            </Boton>
          </span>
        )}
      </Card>

      {rechazos.isPending && <p>Cargando…</p>}
      {rechazos.isSuccess && filas.length === 0 && (
        <p className="text-sm text-primary/70">Sin operaciones rechazadas.</p>
      )}
      {filas.length > 0 && (
        <Card>
          <Tabla filas={filas} columnas={columnas} obtenerClave={(fila) => `${fila.origen}:${fila.id}`} etiqueta="Rechazadas" />
        </Card>
      )}
      {rechazos.hasNextPage && (
        <div>
          <Boton variante="secundario" disabled={rechazos.isFetchingNextPage} onClick={() => void rechazos.fetchNextPage()}>
            Cargar más
          </Boton>
        </div>
      )}

      {resolviendo !== null && (
        <DialogoDeRechazo
          rechazo={resolviendo}
          onCerrar={() => setResolviendo(null)}
          onDesactualizado={() => void rechazos.refetch()}
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

/** El resumen de lo que envió el teléfono; los campos que no se pudieron leer no se muestran. */
function LoQueEnvio({ fila }: { fila: Rechazo }) {
  const resumen = fila.resumen
  if (resumen === null) return null
  return (
    <div className="flex flex-col gap-1">
      {resumen.cliente && <span>{resumen.cliente}</span>}
      {resumen.numero && <span className="text-primary/70">{resumen.numero}</span>}
      {resumen.total && <span className="text-primary/70">{formatearMonto(resumen.total)}</span>}
      {resumen.lineas.map((linea, indice) => (
        <span key={`l${String(indice)}`} className="text-primary/70">
          {[
            linea.producto,
            linea.cantidad === null ? null : `× ${String(linea.cantidad)}`,
            linea.importe === null ? null : formatearMonto(linea.importe),
          ]
            .filter((parte): parte is string => parte !== null)
            .join(' · ')}
        </span>
      ))}
      {resumen.medios.map((medio, indice) => (
        <span key={`m${String(indice)}`} className="text-primary/70">
          {[medio.medio, medio.importe === null ? null : formatearMonto(medio.importe)]
            .filter((parte): parte is string => parte !== null)
            .join(': ')}
        </span>
      ))}
    </div>
  )
}

function VinculoResuelto({ fila }: { fila: Rechazo }) {
  if (fila.vinculo_tipo === null || fila.vinculo_id === null) return null
  const esVenta = fila.vinculo_tipo === 'VENTA'
  return (
    <Link
      to={esVenta ? `/admin/ventas/${fila.vinculo_id}` : `/admin/cobranzas/${fila.vinculo_id}`}
      className="text-sm text-primary/70 hover:text-primary hover:underline"
    >
      {esVenta ? 'Ver venta vinculada' : 'Ver cobranza vinculada'}
    </Link>
  )
}

interface DialogoDeRechazoProps {
  rechazo: Rechazo
  onCerrar: () => void
  onDesactualizado: () => void
}

function DialogoDeRechazo({ rechazo, onCerrar, onDesactualizado }: DialogoDeRechazoProps) {
  const permisos = usePermisos()
  const resolver = useResolverRechazo()
  const [vinculo, setVinculo] = useState<Vinculo | null>(null)
  const tipoDeVinculo = tipoDeVinculoPermitido(rechazo.tipo)
  const puedeVincular = tipoDeVinculo !== null && PERMISOS_PARA_VINCULAR[tipoDeVinculo].some((p) => permisos.tiene(p))

  return (
    <DialogoDeResolucion
      titulo="Resolver"
      confirmacion={TEXTO_DE_CONFIRMACION}
      contenido={{ id: rechazo.id, origen: rechazo.origen, vinculo }}
      onCerrar={onCerrar}
      enviar={(comentario, operationId) =>
        resolver.mutateAsync({
          rechazoId: rechazo.id,
          origen: rechazo.origen,
          comentario,
          vinculo,
          operationId,
        })
      }
      onDesactualizado={onDesactualizado}
      codigosDeDesactualizado={['RECHAZO_YA_RESUELTO']}
    >
      {puedeVincular && tipoDeVinculo !== null && (
        <VinculoDeRechazo
          tipo={tipoDeVinculo}
          valor={vinculo}
          onChange={setVinculo}
        />
      )}
    </DialogoDeResolucion>
  )
}

export default RechazadasScreen
