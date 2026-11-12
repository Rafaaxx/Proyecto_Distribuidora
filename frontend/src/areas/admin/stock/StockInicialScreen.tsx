import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useFieldArray, useForm, useWatch, type Control, type UseFormRegister } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { PageHeader } from '../../../components/ui/PageHeader'
import { referenciaDePresentaciones } from '../../../domain/stock/cantidades'
import { formatearCostoDeApi } from '../../../domain/stock/costos'
import {
  armarEnvio,
  previsualizarPromedio,
  resolverOperationId,
  validarLinea,
  type EnvioPendiente,
  type LineaDeFormulario,
} from '../../../domain/stock/stockInicial'
import { obtenerProducto } from '../../../features/catalogo/api'
import { clavesCatalogo } from '../../../features/catalogo/claves'
import { useProducto, useProductos } from '../../../features/catalogo/useListados'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { usePermisos } from '../../../features/identidad/usePermisos'
import { ErrorDeStock } from '../../../features/stock/errores'
import { esErrorDeRed, useCostoPromedio, useRegistrarStockInicial } from '../../../features/stock/hooks'
import { generarOperationId } from '../../../lib/api/operationId'

const SIN_PERMISO = 'No tenés permiso para registrar stock inicial.'
const AVISO_SIN_CONEXION = 'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.'
const AVISO_REQUIERE_CONEXION =
  'Este dato requiere conexión con el servidor y no se guarda para enviar después: si se corta la conexión, volvé a intentarlo.'
const MENSAJE_GENERICO = 'No se pudo completar la operación.'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'

interface DatosDelFormulario {
  lineas: LineaDeFormulario[]
}

const LINEA_VACIA: LineaDeFormulario = { productoId: '', sentido: 'INGRESO', cajas: '', unidades: '', costo: '' }

function mensajeDeError(error: unknown): string {
  if (esErrorDeRed(error)) return AVISO_SIN_CONEXION
  return error instanceof ErrorDeStock ? error.message : MENSAJE_GENERICO
}

function SinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Cargar stock inicial" />
      <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
    </main>
  )
}

/**
 * Formulario de stock inicial de una ubicación (change 09, tarea 8.4; `design.md`
 * D1, D4, D5, D6, D14, D15; spec `administracion-de-stock`). Ruta
 * `/admin/stock/ubicaciones/:ubicacionId/stock-inicial`. El permiso es
 * `IMPORTAR_DATOS` (D1), de `['yo']` vía `<SiTienePermiso>`: sin él, el formulario
 * no se monta.
 *
 * Varias líneas (1 a 200): producto, tipo (ingreso o corrección, D4), cantidad en
 * cajas + unidades convertida a unidad base entera con la presentación de
 * referencia (CAT-08, INV-04) y costo por unidad base como string (solo en un
 * ingreso). A quien tiene `VER_COSTOS` se le previsualiza el promedio resultante
 * con la misma función que los fixtures de CST-11 (`domain/costeo`, D14); el
 * servidor recalcula siempre (TR-10). El `operation_id` es nuevo por envío y se
 * conserva para reenviarlo si el envío se cortó por la red (INV-06, TR-07). Es
 * `ONLINE` puro: no se encola nada.
 */
export function StockInicialScreen() {
  const { ubicacionId } = useParams<{ ubicacionId: string }>()
  return (
    <SiTienePermiso permiso="IMPORTAR_DATOS" fallback={<SinPermiso />}>
      {ubicacionId ? <Formulario ubicacionId={ubicacionId} /> : null}
    </SiTienePermiso>
  )
}

function Formulario({ ubicacionId }: { ubicacionId: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const registrar = useRegistrarStockInicial()
  const permisos = usePermisos()
  const verCostos = permisos.tiene('VER_COSTOS')
  // Envío cortado por la red antes de recibir respuesta: su `operation_id` se
  // conserva para reenviarlo si el usuario reintenta lo mismo.
  const pendienteRef = useRef<EnvioPendiente | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const { register, handleSubmit, control } = useForm<DatosDelFormulario>({
    defaultValues: { lineas: [{ ...LINEA_VACIA }] },
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'lineas' })

  async function enviar(datos: DatosDelFormulario) {
    setError(null)
    setEnviando(true)
    try {
      const lineas: { linea: LineaDeFormulario; unidadesPorCaja: number | null; nombrePresentacion: string | null }[] = []
      for (const cruda of datos.lineas) {
        // Un campo deshabilitado (cajas sin presentación de referencia) no entra
        // en los valores del formulario: se toma como vacío.
        const linea: LineaDeFormulario = {
          productoId: cruda.productoId ?? '',
          sentido: cruda.sentido ?? 'INGRESO',
          cajas: cruda.cajas ?? '',
          unidades: cruda.unidades ?? '',
          costo: cruda.costo ?? '',
        }
        let unidadesPorCaja: number | null = null
        let nombrePresentacion: string | null = null
        if (linea.productoId !== '') {
          const detalle = await queryClient.fetchQuery({
            queryKey: clavesCatalogo.producto(linea.productoId),
            queryFn: () => obtenerProducto(linea.productoId),
          })
          const referenciaDelProducto = referenciaDePresentaciones(detalle.presentaciones)
          unidadesPorCaja = referenciaDelProducto?.unidades ?? null
          nombrePresentacion = referenciaDelProducto?.nombre ?? null
        }
        lineas.push({ linea, unidadesPorCaja, nombrePresentacion })
      }

      const envio = armarEnvio(ubicacionId, lineas)
      if (!envio.ok) {
        setError(envio.indice === undefined ? envio.mensaje : `Línea ${String(envio.indice + 1)}: ${envio.mensaje}`)
        return
      }

      const operationId = resolverOperationId(pendienteRef.current, envio.cuerpo, generarOperationId)
      try {
        await registrar.mutateAsync({ ...envio.cuerpo, operationId })
        pendienteRef.current = null
        navigate(`/admin/stock/ubicaciones/${ubicacionId}/stock`)
      } catch (errorDeEnvio) {
        // Corte de red: puede que el servidor sí lo haya procesado, así que se
        // reenvía con el mismo `operation_id`. Un rechazo con respuesta HTTP ya
        // está resuelto: reenviar es una operación nueva.
        pendienteRef.current = esErrorDeRed(errorDeEnvio) ? { cuerpo: envio.cuerpo, operationId } : null
        setError(mensajeDeError(errorDeEnvio))
      }
    } catch (errorInesperado) {
      setError(mensajeDeError(errorInesperado))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo="Cargar stock inicial"
        acciones={
          <Link
            to={`/admin/stock/ubicaciones/${ubicacionId}/stock`}
            className="text-sm text-primary/70 hover:text-primary hover:underline"
          >
            Volver al stock
          </Link>
        }
      />
      <Card>
        <form onSubmit={(evento) => void handleSubmit(enviar)(evento)} noValidate className="flex flex-col gap-4">
          <p className="text-sm text-primary/70">{AVISO_REQUIERE_CONEXION}</p>

          {fields.map((campo, indice) => (
            <LineaEditor
              key={campo.id}
              indice={indice}
              register={register}
              control={control}
              verCostos={verCostos}
              puedeQuitar={fields.length > 1}
              onQuitar={() => remove(indice)}
            />
          ))}

          <div>
            <Boton type="button" variante="secundario" onClick={() => append({ ...LINEA_VACIA })}>
              Agregar línea
            </Boton>
          </div>

          {error && <Alert>{error}</Alert>}

          <div className="flex items-center gap-3">
            <Boton type="submit" disabled={enviando || registrar.isPending}>
              Registrar stock inicial
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
  verCostos: boolean
  puedeQuitar: boolean
  onQuitar: () => void
}

function LineaEditor({ indice, register, control, verCostos, puedeQuitar, onQuitar }: LineaEditorProps) {
  const linea = useWatch({ control, name: `lineas.${String(indice)}` as `lineas.${number}` })
  const [texto, setTexto] = useState('')
  const productos = useProductos({ texto: texto.trim() || undefined, activo: true })
  const opciones = productos.data?.pages.flatMap((pagina) => pagina.items) ?? []

  const productoId = linea.productoId === '' ? undefined : linea.productoId
  const detalle = useProducto(productoId)
  const presentacionDeReferencia = referenciaDePresentaciones(detalle.data?.presentaciones)
  const referencia = presentacionDeReferencia?.unidades ?? null
  const nombreReferencia = presentacionDeReferencia?.nombre ?? null
  const sinReferencia = productoId !== undefined && detalle.isSuccess && referencia === null
  const costo = useCostoPromedio(productoId, verCostos && productoId !== undefined)
  const esIngreso = linea.sentido !== 'CORRECCION'

  let promedio: string | null = null
  if (verCostos && costo.data && productoId !== undefined) {
    const validada = validarLinea(
      {
        productoId,
        sentido: linea.sentido,
        cajas: linea.cajas ?? '',
        unidades: linea.unidades ?? '',
        costo: linea.costo ?? '',
      },
      referencia,
      nombreReferencia,
    )
    if (validada.ok) {
      promedio = previsualizarPromedio({
        stockTotal: costo.data.stock_total,
        promedio: costo.data.costo_promedio,
        cantidadBase: validada.payload.cantidad_base,
        costo: validada.payload.costo_unitario === undefined ? null : String(validada.payload.costo_unitario),
      })
    }
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
            {opciones.map((producto) => (
              <option key={producto.id} value={producto.id}>
                {producto.codigo} · {producto.nombre}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-primary">
          Tipo de línea
          <select className={CLASE_CONTROL} {...register(nombre('sentido'))}>
            <option value="INGRESO">Ingreso</option>
            <option value="CORRECCION">Corrección (egreso)</option>
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm text-primary">
          {nombreReferencia ?? 'Cajas'}
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
        {esIngreso && (
          <label className="flex flex-col gap-1 text-sm text-primary">
            Costo por unidad base
            <input inputMode="decimal" autoComplete="off" className={CLASE_CONTROL} {...register(nombre('costo'))} />
          </label>
        )}
        {puedeQuitar && (
          <Boton type="button" variante="secundario" onClick={onQuitar}>
            Quitar línea
          </Boton>
        )}
      </div>

      {referencia !== null && (
        <p className="text-xs text-primary/70">Una {nombreReferencia ?? 'caja'} tiene {referencia} unidades.</p>
      )}
      {promedio !== null && (
        <p className="text-sm text-primary">Promedio resultante: {formatearCostoDeApi(promedio)}</p>
      )}
    </fieldset>
  )
}

export default StockInicialScreen
