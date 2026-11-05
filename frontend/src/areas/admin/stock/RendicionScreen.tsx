import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { PageHeader } from '../../../components/ui/PageHeader'
import { formatearCantidad, referenciaDeRespuesta, type ReferenciaDePresentacion } from '../../../domain/stock/cantidades'
import { LIMITE_DE_OBSERVACION } from '../../../domain/stock/jornadas'
import {
  armarConteo,
  calcularDiferencia,
  contadoEnBase,
  textoDeConfirmacionDeRendicion,
  textoDeConteoIncompleto,
  type FilaDeConteo,
  type LineaDeConteo,
} from '../../../domain/stock/rendicion'
import { Tabla, type ColumnaTabla } from '../../../components/ui/Table'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { ErrorDeStock, mensajeDeErrorDeStock, RecursoNoEncontradoStockError } from '../../../features/stock/errores'
import {
  useJornada,
  useProductosParaRendicion,
  useRendirJornada,
  useResumenDeJornada,
  useSaldosCompletos,
} from '../../../features/stock/hooks'
import { AVISO_REQUIERE_CONEXION, CLASE_CONTROL, CLASE_ENLACE, PantallaSinPermiso } from './piezasDeOperacion'
import { CampoDeCantidad, type ValorDeCantidad } from './piezasDeRendicion'

const TITULO = 'Rendición'
const SIN_CONTAR: ValorDeCantidad = { cajas: '', unidades: '' }

/**
 * Pantalla de conteo de una jornada (change 24, tarea 12.1; `design.md` D2, D9, D11; RUT-05, RUT-06,
 * CAT-08, INV-04, INV-06). Por producto del conjunto a contar: el esperado (cajas y unidades), lo
 * contado y la diferencia al escribir; «Agregar producto» suma un sobrante; la confirmación dice
 * cuántas diferencias hay. Reintentar tras un corte reenvía el mismo `operation_id`. Las reglas
 * viven en `domain/stock/rendicion.ts`; el servidor valida y es la autoridad.
 */
export function RendicionScreen() {
  return (
    <SiTienePermiso
      permiso="RENDIR_JORNADA"
      fallback={<PantallaSinPermiso titulo={TITULO} mensaje="No tenés permiso para rendir jornadas." />}
    >
      <Conteo />
    </SiTienePermiso>
  )
}

interface FilaDePantalla {
  productoId: string
  esperado: number
}

function Conteo() {
  const { jornadaId } = useParams<{ jornadaId: string }>()
  const navigate = useNavigate()
  const jornada = useJornada(jornadaId)
  const resumen = useResumenDeJornada(jornadaId)
  const catalogo = useProductosParaRendicion()
  const permisos = usePermisos()
  const rendir = useRendirJornada()
  // Las presentaciones de referencia salen de los saldos del vehículo (`TRANSFERIR_STOCK`); sin ese
  // permiso, o para un producto sin saldo, la cantidad se escribe en unidades base.
  const saldos = useSaldosCompletos(permisos.tiene('TRANSFERIR_STOCK') ? jornada.data?.ubicacion_id : undefined)

  const [conteo, setConteo] = useState<Record<string, ValorDeCantidad>>({})
  const [agregados, setAgregados] = useState<string[]>([])
  const [agregando, setAgregando] = useState(false)
  const [observacion, setObservacion] = useState('')
  const [confirmando, setConfirmando] = useState<{ lineas: LineaDeConteo[]; conDiferencias: number } | null>(null)
  const [marcados, setMarcados] = useState<ReadonlySet<string>>(new Set())
  const [invalidas, setInvalidas] = useState<Record<string, string>>({})
  const [aviso, setAviso] = useState<string | null>(null)
  const [errorDelDialogo, setErrorDelDialogo] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const observacionLimpia = observacion.trim()
  const operationId = useOperationIdPorContenido({
    jornadaId,
    lineas: confirmando?.lineas,
    observacion: observacionLimpia,
  })

  if (jornada.isPending || resumen.isPending) return <p>Cargando…</p>
  if (jornada.isError || resumen.isError) {
    const noEncontrada = jornada.error instanceof RecursoNoEncontradoStockError
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} acciones={<Link to="/admin/stock/jornadas" className={CLASE_ENLACE}>Volver al listado</Link>} />
        <Alert>{noEncontrada ? 'No se encontró la jornada.' : 'No se pudo obtener la jornada.'}</Alert>
      </main>
    )
  }

  const datos = jornada.data
  const volver = (
    <Link to={`/admin/stock/jornadas/${datos.id}`} className={CLASE_ENLACE}>
      Volver a la jornada
    </Link>
  )
  if (datos.estado !== 'ABIERTA') {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={`${TITULO} de ${datos.ubicacion_nombre}`} acciones={volver} />
        <Alert>{mensajeDeErrorDeStock(new ErrorDeStock('JORNADA_ESTADO_INVALIDO', ''), 'jornada')}</Alert>
      </main>
    )
  }
  if (!datos.entregada_en) {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={`${TITULO} de ${datos.ubicacion_nombre}`} acciones={volver} />
        <Alert>{mensajeDeErrorDeStock(new ErrorDeStock('JORNADA_SIN_ENTREGA', ''), 'jornada')}</Alert>
      </main>
    )
  }

  const nombres = new Map(catalogo.productos.map((p) => [p.id, p.nombre]))
  const nombreDe = (productoId: string) => nombres.get(productoId) ?? `Producto ${productoId.slice(0, 8)}`
  const referencias = new Map<string, ReferenciaDePresentacion>()
  for (const saldo of saldos.lineas) {
    const referencia = referenciaDeRespuesta(saldo.unidades_referencia, saldo.nombre_referencia)
    if (referencia !== null) referencias.set(saldo.producto_id, referencia)
  }

  const delConjunto: FilaDePantalla[] = resumen.data.lineas.map((l) => ({ productoId: l.producto_id, esperado: l.esperado }))
  const enElConjunto = new Set(delConjunto.map((f) => f.productoId))
  const filas: FilaDePantalla[] = [
    ...delConjunto,
    ...agregados.filter((id) => !enElConjunto.has(id)).map((id) => ({ productoId: id, esperado: 0 })),
  ]
  const valorDe = (productoId: string) => conteo[productoId] ?? SIN_CONTAR
  const filaDeConteo = (fila: FilaDePantalla): FilaDeConteo => {
    const referencia = referencias.get(fila.productoId) ?? null
    return {
      productoId: fila.productoId,
      esperado: fila.esperado,
      ...valorDe(fila.productoId),
      unidadesPorCaja: referencia?.unidades ?? null,
      nombrePresentacion: referencia?.nombre ?? null,
    }
  }
  const productosParaAgregar = catalogo.productos.filter((p) => p.activo && !filas.some((f) => f.productoId === p.id))

  const cambiarCantidad = (productoId: string, valor: ValorDeCantidad) => {
    setConteo((actual) => ({ ...actual, [productoId]: valor }))
    setInvalidas((actual) => Object.fromEntries(Object.entries(actual).filter(([id]) => id !== productoId)))
  }

  const registrar = () => {
    setAviso(null)
    setMarcados(new Set())
    setInvalidas({})
    if (observacionLimpia.length > LIMITE_DE_OBSERVACION) {
      setAviso(`La observación admite hasta ${String(LIMITE_DE_OBSERVACION)} caracteres.`)
      return
    }
    const resultado = armarConteo(filas.map(filaDeConteo))
    if (!resultado.ok) {
      setInvalidas(Object.fromEntries(resultado.invalidas.map((i) => [i.productoId, i.mensaje])))
      if (resultado.sinContar.length > 0) setAviso(textoDeConteoIncompleto(resultado.sinContar.map(nombreDe)))
      return
    }
    setErrorDelDialogo(null)
    setConfirmando({ lineas: resultado.lineas, conDiferencias: resultado.conDiferencias })
  }

  const confirmar = async () => {
    if (confirmando === null) return
    setErrorDelDialogo(null)
    setEnviando(true)
    try {
      await rendir.mutateAsync({
        id: datos.id,
        lineas: confirmando.lineas,
        ...(observacionLimpia === '' ? {} : { observacion: observacionLimpia }),
        operationId,
      })
      navigate(`/admin/stock/jornadas/${datos.id}`)
    } catch (falla) {
      if (falla instanceof ErrorDeStock && falla.codigo === 'ESPERADO_DIFIERE') {
        // El stock cambió mientras se contaba: se recargan los esperados y se marcan los que cambiaron.
        setMarcados(new Set(falla.idsDe('distintos')))
        setConfirmando(null)
        setAviso(mensajeDeErrorDeStock(falla, 'jornada'))
        void resumen.refetch()
      } else if (falla instanceof ErrorDeStock && falla.codigo === 'CONTEO_INCOMPLETO') {
        setConfirmando(null)
        setAviso(textoDeConteoIncompleto(falla.idsDe('productos').map(nombreDe)))
        void resumen.refetch()
      } else {
        setErrorDelDialogo(mensajeDeErrorDeStock(falla, 'jornada'))
      }
    } finally {
      setEnviando(false)
    }
  }

  const columnas: ColumnaTabla<FilaDePantalla>[] = [
    {
      clave: 'producto',
      encabezado: 'Producto',
      render: (fila) => <span className="font-medium">{nombreDe(fila.productoId)}</span>,
    },
    {
      clave: 'esperado',
      encabezado: 'Esperado',
      ayuda: 'stock.esperado',
      render: (fila) => (
        <span className="flex flex-col gap-1">
          <span>{formatearCantidad(fila.esperado, referencias.get(fila.productoId) ?? null)}</span>
          {marcados.has(fila.productoId) && <span className="text-xs font-medium text-danger">Esperado actualizado</span>}
        </span>
      ),
    },
    {
      clave: 'contado',
      encabezado: 'Contado',
      render: (fila) => (
        <span className="flex flex-col gap-1">
          <CampoDeCantidad
            producto={nombreDe(fila.productoId)}
            valor={valorDe(fila.productoId)}
            referencia={referencias.get(fila.productoId) ?? null}
            onChange={(valor) => cambiarCantidad(fila.productoId, valor)}
          />
          {invalidas[fila.productoId] !== undefined && <span className="text-xs text-danger">{invalidas[fila.productoId]}</span>}
        </span>
      ),
    },
    {
      clave: 'diferencia',
      encabezado: 'Diferencia',
      ayuda: 'stock.diferenciaRendicion',
      render: (fila) => {
        const contado = contadoEnBase(filaDeConteo(fila))
        const diferencia = calcularDiferencia(contado, fila.esperado)
        if (diferencia === null) return <span className="text-primary/50">—</span>
        return (
          <span className={diferencia < 0 ? 'font-medium text-danger' : undefined}>
            {formatearCantidad(diferencia, referencias.get(fila.productoId) ?? null)}
          </span>
        )
      },
    },
  ]

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={`${TITULO} de ${datos.ubicacion_nombre}`}
        acciones={
          <>
            <Ayuda clave="stock.rendicion" />
            {volver}
          </>
        }
      />

      {aviso && <Alert>{aviso}</Alert>}

      <Card className="flex flex-col gap-3">
        <Tabla filas={filas} columnas={columnas} obtenerClave={(fila) => fila.productoId} etiqueta="Conteo de la jornada" />
        <div className="flex flex-wrap items-end gap-3">
          {agregando ? (
            <label className="flex flex-col gap-1 text-sm text-primary">
              Agregar producto
              <select
                className={CLASE_CONTROL}
                value=""
                onChange={(evento) => {
                  if (evento.target.value === '') return
                  setAgregados((actual) => [...actual, evento.target.value])
                  setAgregando(false)
                }}
              >
                <option value="">Elegí un producto</option>
                {productosParaAgregar.map((producto) => (
                  <option key={producto.id} value={producto.id}>
                    {producto.codigo} · {producto.nombre}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <Boton variante="secundario" onClick={() => setAgregando(true)}>
              Agregar producto
            </Boton>
          )}
        </div>
      </Card>

      <div className="flex flex-col gap-1">
        <label htmlFor="rendicion-observacion" className="text-sm font-medium text-primary">
          Observación
        </label>
        <textarea
          id="rendicion-observacion"
          rows={3}
          className={CLASE_CONTROL}
          value={observacion}
          onChange={(evento) => setObservacion(evento.target.value)}
        />
      </div>

      <div>
        <Boton onClick={registrar}>Registrar rendición</Boton>
      </div>

      <Dialogo
        abierto={confirmando !== null}
        titulo={textoDeConfirmacionDeRendicion(confirmando?.conDiferencias ?? 0)}
        onCerrar={() => setConfirmando(null)}
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm text-primary/70">{AVISO_REQUIERE_CONEXION}</p>
          {errorDelDialogo && <Alert>{errorDelDialogo}</Alert>}
          <div className="flex gap-2">
            <Boton disabled={enviando} onClick={() => void confirmar()}>
              Confirmar
            </Boton>
            <Boton variante="secundario" onClick={() => setConfirmando(null)}>
              Cancelar
            </Boton>
          </div>
        </div>
      </Dialogo>
    </main>
  )
}

export default RendicionScreen
