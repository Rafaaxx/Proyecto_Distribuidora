import { useQueries } from '@tanstack/react-query'
import { useState } from 'react'
import { useFieldArray, useForm, useWatch, type Control, type UseFormRegister } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { referenciaDePresentaciones, type ReferenciaDePresentacion } from '../../../domain/stock/cantidades'
import {
  AMBITO_DE_AJUSTE,
  armarAjuste,
  cantidadDeLinea,
  previsualizarAjuste,
  type LineaDeEntrada,
  type SaldoDeLinea,
} from '../../../domain/stock/operaciones'
import { obtenerProducto } from '../../../features/catalogo/api'
import { clavesCatalogo } from '../../../features/catalogo/claves'
import { useProducto, useProductos } from '../../../features/catalogo/useListados'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { LineaDeStock, Ubicacion } from '../../../features/stock/api'
import { ErrorDeStock, mensajeDeErrorDeStock } from '../../../features/stock/errores'
import {
  useMotivosDeStock,
  useRegistrarAjuste,
  useSaldosCompletos,
  useUbicaciones,
} from '../../../features/stock/hooks'
import {
  AVISO_REQUIERE_CONEXION,
  CLASE_CONTROL,
  CLASE_ENLACE,
  PantallaSinPermiso,
  SaldoResultante,
} from './piezasDeOperacion'

const TITULO = 'Nuevo ajuste'

type Signo = 'POSITIVO' | 'NEGATIVO'

interface LineaDeFormulario {
  productoId: string
  signo: Signo
  cajas: string
  unidades: string
}

interface DatosDelFormulario {
  ubicacionId: string
  motivoId: string
  observacion: string
  lineas: LineaDeFormulario[]
}

const LINEA_VACIA: LineaDeFormulario = { productoId: '', signo: 'POSITIVO', cajas: '', unidades: '' }

interface ErrorDeEnvio {
  mensaje: string
  indice?: number
}

/** Producto de una línea, con la presentación de referencia que viene de su detalle. */
interface ProductoDeLinea {
  id: string
  codigo: string
  nombre: string
  referencia: ReferenciaDePresentacion | null
}

/**
 * Alta de un ajuste de stock (change 14, tarea 13.2; spec `administracion-de-stock`; STK-08,
 * `design.md` D1, D2, D3, D7, D11). Ruta `/admin/stock/ajustes/nueva`, con `?ubicacion=&producto=
 * &cantidad=` desde "Ajustar" (la regularización de un saldo negativo, D2: la cantidad llega en
 * unidad base). Pide ubicación, motivo del ámbito `AJUSTE_STOCK`, observación opcional y líneas
 * con signo en cajas + unidades; cada línea muestra el saldo actual y el resultante y marca un
 * resultado negativo, que el servidor rechaza siempre (D1). Sin importes calculados acá.
 */
export function AjusteFormScreen() {
  return (
    <SiTienePermiso
      permiso="AJUSTAR_STOCK"
      fallback={<PantallaSinPermiso titulo={TITULO} mensaje="No tenés permiso para registrar ajustes." />}
    >
      <CargaInicial />
    </SiTienePermiso>
  )
}

/** Espera lo que el formulario precarga (ubicaciones y producto), para que sus opciones existan al montar. */
function CargaInicial() {
  const [parametros] = useSearchParams()
  const ubicaciones = useUbicaciones(true)
  const productoPrecargado = parametros.get('producto') ?? undefined
  const producto = useProducto(productoPrecargado)

  const cargando = ubicaciones.isPending || (productoPrecargado !== undefined && producto.isPending)
  if (cargando) return <p>Cargando…</p>
  if (ubicaciones.isError) {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo={TITULO} />
        <Alert>No se pudieron obtener las ubicaciones.</Alert>
      </main>
    )
  }
  return <Formulario ubicaciones={ubicaciones.data.pages.flatMap((pagina) => pagina.items)} />
}

function productosDeLineas(ids: string[], resultados: { data?: Awaited<ReturnType<typeof obtenerProducto>> }[]) {
  const mapa = new Map<string, ProductoDeLinea>()
  ids.forEach((id, indice) => {
    const detalle = resultados[indice]?.data
    if (detalle) {
      mapa.set(id, {
        id,
        codigo: detalle.codigo,
        nombre: detalle.nombre,
        referencia: referenciaDePresentaciones(detalle.presentaciones),
      })
    }
  })
  return mapa
}

function entradaDeLinea(cruda: Partial<LineaDeFormulario> | undefined, producto: ProductoDeLinea | undefined): LineaDeEntrada {
  return {
    productoId: cruda?.productoId ?? '',
    cajas: cruda?.cajas ?? '',
    unidades: cruda?.unidades ?? '',
    negativa: cruda?.signo === 'NEGATIVO',
    unidadesPorCaja: producto?.referencia?.unidades ?? null,
    nombrePresentacion: producto?.referencia?.nombre ?? null,
  }
}

function Formulario({ ubicaciones }: { ubicaciones: Ubicacion[] }) {
  const navigate = useNavigate()
  const [parametros] = useSearchParams()
  const registrar = useRegistrarAjuste()
  const motivos = useMotivosDeStock(AMBITO_DE_AJUSTE)
  const [error, setError] = useState<ErrorDeEnvio | null>(null)
  const [enviando, setEnviando] = useState(false)

  const ubicacionInicial = parametros.get('ubicacion') ?? ''
  const productoInicial = parametros.get('producto') ?? ''
  const cantidadInicial = parametros.get('cantidad') ?? ''
  const { register, handleSubmit, control } = useForm<DatosDelFormulario>({
    defaultValues: {
      ubicacionId: ubicaciones.some((u) => u.id === ubicacionInicial) ? ubicacionInicial : '',
      motivoId: '',
      observacion: '',
      // D2: la regularización llega como unidades base positivas, editables.
      lineas: [
        productoInicial === ''
          ? { ...LINEA_VACIA }
          : { productoId: productoInicial, signo: 'POSITIVO', cajas: '', unidades: /^\d+$/.test(cantidadInicial) ? cantidadInicial : '' },
      ],
    },
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'lineas' })
  const valores = useWatch({ control })
  const ubicacionId = valores.ubicacionId ?? ''
  const idsDeProductos = (valores.lineas ?? []).map((l) => l?.productoId ?? '')
  const detalles = useQueries({
    queries: idsDeProductos.map((id) => ({
      queryKey: clavesCatalogo.producto(id),
      queryFn: () => obtenerProducto(id),
      enabled: id !== '',
    })),
  })
  const productos = productosDeLineas(idsDeProductos, detalles)
  const saldos = useSaldosCompletos(ubicacionId === '' ? undefined : ubicacionId)

  const armado = armarAjuste({
    ubicacionId,
    motivoId: valores.motivoId ?? '',
    observacion: valores.observacion ?? '',
    lineas: (valores.lineas ?? []).map((l) => entradaDeLinea(l, productos.get(l?.productoId ?? ''))),
  })
  // El `operation_id` cambia cuando cambia el contenido y se conserva si se reintenta lo mismo.
  const operationId = useOperationIdPorContenido(armado.ok ? armado.cuerpo : null)

  async function enviar() {
    if (!armado.ok) {
      setError({ mensaje: armado.mensaje, indice: armado.indice })
      return
    }
    setError(null)
    setEnviando(true)
    try {
      const resultado = await registrar.mutateAsync({ ...armado.cuerpo, operationId })
      navigate(`/admin/stock/ajustes/${resultado.id}`)
    } catch (falla) {
      setError({
        mensaje: mensajeDeErrorDeStock(falla, 'ajuste'),
        indice: falla instanceof ErrorDeStock ? falla.linea : undefined,
      })
    } finally {
      setEnviando(false)
    }
  }

  const nombreDeLaUbicacion = ubicaciones.find((u) => u.id === ubicacionId)?.nombre ?? ''

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={TITULO}
        acciones={
          <Link to="/admin/stock/ajustes" className={CLASE_ENLACE}>
            Volver al listado
          </Link>
        }
      />
      <Card>
        <form onSubmit={(evento) => void handleSubmit(enviar)(evento)} noValidate className="flex flex-col gap-4">
          <p className="text-sm text-primary/70">{AVISO_REQUIERE_CONEXION}</p>

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm text-primary">
              Ubicación
              <select className={CLASE_CONTROL} {...register('ubicacionId')}>
                <option value="">Elegí la ubicación</option>
                {ubicaciones.map((ubicacion) => (
                  <option key={ubicacion.id} value={ubicacion.id}>
                    {ubicacion.nombre}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-primary">
              Motivo
              <select className={CLASE_CONTROL} {...register('motivoId')}>
                <option value="">Elegí un motivo</option>
                {(motivos.data?.items ?? []).map((motivo) => (
                  <option key={motivo.id} value={motivo.id}>
                    {motivo.nombre}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {fields.map((campo, indice) => (
            <LineaEditor
              key={campo.id}
              indice={indice}
              register={register}
              control={control}
              producto={productos.get(idsDeProductos[indice] ?? '')}
              saldos={saldos.completo ? saldos.lineas : null}
              ubicacion={nombreDeLaUbicacion}
              error={error?.indice === indice ? error.mensaje : null}
              puedeQuitar={fields.length > 1}
              onQuitar={() => remove(indice)}
            />
          ))}

          <div>
            <Boton type="button" variante="secundario" onClick={() => append({ ...LINEA_VACIA })}>
              Agregar línea
            </Boton>
          </div>

          <label className="flex flex-col gap-1 text-sm text-primary">
            Observación
            <textarea className={CLASE_CONTROL} rows={2} {...register('observacion')} />
          </label>

          {error && error.indice === undefined && <Alert>{error.mensaje}</Alert>}

          <div className="flex items-center gap-3">
            <Boton type="submit" disabled={enviando || registrar.isPending}>
              Registrar ajuste
            </Boton>
          </div>
        </form>
      </Card>
    </main>
  )
}

interface LineaEditorProps {
  indice: number
  register: UseFormRegister<DatosDelFormulario>
  control: Control<DatosDelFormulario>
  producto: ProductoDeLinea | undefined
  /** `null` mientras los saldos de la ubicación no terminaron de cargar o no hay ubicación. */
  saldos: readonly LineaDeStock[] | null
  ubicacion: string
  error: string | null
  puedeQuitar: boolean
  onQuitar: () => void
}

function LineaEditor({ indice, register, control, producto, saldos, ubicacion, error, puedeQuitar, onQuitar }: LineaEditorProps) {
  const linea = useWatch({ control, name: `lineas.${String(indice)}` as `lineas.${number}` })
  const [texto, setTexto] = useState('')
  const productos = useProductos({ texto: texto.trim() || undefined, activo: true })
  const listado = productos.data?.pages.flatMap((pagina) => pagina.items) ?? []
  // El producto elegido siempre figura entre las opciones, aunque la búsqueda ya no lo traiga.
  const opciones =
    producto && !listado.some((p) => p.id === producto.id)
      ? [{ id: producto.id, codigo: producto.codigo, nombre: producto.nombre }, ...listado]
      : listado

  const referencia = producto?.referencia ?? null
  const sinReferencia = producto !== undefined && referencia === null
  const cantidad = producto
    ? cantidadDeLinea(entradaDeLinea(linea, producto))
    : null
  let saldo: SaldoDeLinea | null = null
  if (saldos !== null && producto && cantidad?.ok && cantidad.cantidadBase !== 0) {
    const actual = saldos.find((s) => s.producto_id === producto.id)?.cantidad_base ?? 0
    saldo = previsualizarAjuste(actual, cantidad.cantidadBase)
  }

  const nombre = (campo: keyof LineaDeFormulario) => `lineas.${String(indice)}.${campo}` as `lineas.${number}.${typeof campo}`

  return (
    <fieldset className="flex flex-col gap-3 rounded-md border border-border p-3">
      <legend className="px-1 text-sm font-medium text-primary">Línea {indice + 1}</legend>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm text-primary">
          Buscar producto
          <input
            type="search"
            value={texto}
            onChange={(evento) => setTexto(evento.target.value)}
            placeholder="Nombre o código"
            className={CLASE_CONTROL}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-primary">
          Producto
          <select className={CLASE_CONTROL} {...register(nombre('productoId'))}>
            <option value="">Elegí un producto</option>
            {opciones.map((opcion) => (
              <option key={opcion.id} value={opcion.id}>
                {opcion.codigo} · {opcion.nombre}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-primary">
          Tipo de ajuste
          <select className={CLASE_CONTROL} {...register(nombre('signo'))}>
            <option value="POSITIVO">Sobrante (suma)</option>
            <option value="NEGATIVO">Faltante (resta)</option>
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm text-primary">
          {referencia?.nombre ?? 'Cajas'}
          <input
            inputMode="numeric"
            autoComplete="off"
            disabled={sinReferencia}
            className={CLASE_CONTROL}
            {...register(nombre('cajas'))}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-primary">
          Unidades
          <input inputMode="numeric" autoComplete="off" className={CLASE_CONTROL} {...register(nombre('unidades'))} />
        </label>
        {puedeQuitar && (
          <Boton type="button" variante="secundario" onClick={onQuitar}>
            Quitar línea
          </Boton>
        )}
      </div>

      {referencia !== null && (
        <p className="text-xs text-primary/70">
          Una {referencia.nombre ?? 'caja'} tiene {referencia.unidades} unidades.
        </p>
      )}
      {saldo !== null && <SaldoResultante ubicacion={ubicacion} saldo={saldo} referencia={referencia} />}
      {error && <Alert>{error}</Alert>}
    </fieldset>
  )
}

export default AjusteFormScreen
