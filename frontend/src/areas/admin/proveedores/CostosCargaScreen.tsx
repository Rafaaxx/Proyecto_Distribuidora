import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo } from 'react'
import { useFieldArray, useForm, type FieldPath } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Boton } from '../../../components/ui/Button'
import { Campo } from '../../../components/ui/Field'
import { Card } from '../../../components/ui/Card'
import type { Producto } from '../../../features/catalogo/api'
import { useProducto, useProductos } from '../../../features/catalogo/useListados'
import { useAlicuotas } from '../../../features/configuracion/useAlicuotas'
import {
  esquemaCargaDeCostos,
  FILA_VACIA,
  type DatosCargaDeCostos,
  type DatosFilaCosto,
} from '../../../domain/proveedores/costosCargaSchema'
import { calcularCostoBase } from '../../../domain/proveedores/costoBase'
import { formatearCosto, parsearImporteDesdeApi } from '../../../lib/money'
import type { CostoDelLote } from '../../../features/proveedores/api'
import { ErrorDeProveedores } from '../../../features/proveedores/errores'
import { campoDeCostoParaCodigo } from '../../../features/proveedores/mapaErrorACampo'
import { useProveedor } from '../../../features/proveedores/useListados'
import { useInformarCostos } from '../../../features/proveedores/useMutaciones'

/**
 * Carga de uno o varios costos informados de un proveedor, con vista
 * previa del costo base calculada en el cliente (tarea 11.4, CST-02, spec
 * `administracion-de-proveedores`). Un único envío (`COSTO_INFORMAR`)
 * para todas las filas (CST-05, INV-01: todo o nada).
 */

function fechaDeHoy(): string {
  const ahora = new Date()
  const anio = ahora.getFullYear()
  const mes = String(ahora.getMonth() + 1).padStart(2, '0')
  const dia = String(ahora.getDate()).padStart(2, '0')
  return `${anio}-${mes}-${dia}`
}

export function CostosCargaScreen() {
  const { proveedorId } = useParams<{ proveedorId: string }>()
  const proveedor = useProveedor(proveedorId)

  if (proveedor.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }

  if (proveedor.isError || !proveedorId) {
    return (
      <main>
        <p role="alert">No se pudo obtener el proveedor.</p>
      </main>
    )
  }

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-primary">Cargar costos — {proveedor.data.nombre}</h1>
      <CargaDeCostosFormulario proveedorId={proveedorId} />
    </main>
  )
}

function CargaDeCostosFormulario({ proveedorId }: { proveedorId: string }) {
  const navigate = useNavigate()
  const informar = useInformarCostos()
  const productos = useProductos({ activo: true })

  const productosDelProveedor = useMemo(
    () =>
      (productos.data?.pages.flatMap((pagina) => pagina.items) ?? []).filter(
        (producto) => producto.proveedor_id === proveedorId,
      ),
    [productos.data, proveedorId],
  )

  const {
    control,
    register,
    handleSubmit,
    setError,
    watch,
    formState: { errors },
  } = useForm<DatosCargaDeCostos>({
    resolver: zodResolver(esquemaCargaDeCostos),
    defaultValues: { filas: [{ ...FILA_VACIA, vigenciaDesde: fechaDeHoy() }] },
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'filas' })
  const filasActuales = watch('filas')

  const alEnviar = handleSubmit(async (datos) => {
    try {
      const costos: CostoDelLote[] = datos.filas.map((fila) => ({
        producto_id: fila.productoId,
        presentacion_id: fila.presentacionId,
        valor: fila.valor,
        incluye_iva: fila.incluyeIva,
        bonificacion: parsearImporteDesdeApi(fila.bonificacionPorcentaje).div(100).toFixed(6),
        vigencia_desde: fila.vigenciaDesde,
        observacion: fila.observacion.trim() === '' ? null : fila.observacion.trim(),
      }))
      await informar.mutateAsync({ proveedor_id: proveedorId, costos })
      // Bug 13.5: sin esta navegación el formulario quedaba en la misma
      // pantalla sin ningún indicio de éxito -- el usuario reenviaba el
      // mismo lote varias veces creyendo que no había funcionado, cada
      // click generando un COSTO_INFORMAR nuevo (Operation-Id distinto).
      navigate(`/admin/proveedores/${proveedorId}`)
    } catch (error) {
      atribuirErrorAFila(error, datos.filas, setError)
    }
  })

  return (
    <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
      {errors.filas?.root?.message && (
        <p role="alert" className="text-sm text-danger">
          {errors.filas.root.message}
        </p>
      )}
      {typeof errors.filas?.message === 'string' && (
        <p role="alert" className="text-sm text-danger">
          {errors.filas.message}
        </p>
      )}
      {errors.root?.message && (
        <p role="alert" className="text-sm text-danger">
          {errors.root.message}
        </p>
      )}

      {fields.map((campo, indice) => (
        <FilaCostoInput
          key={campo.id}
          indice={indice}
          register={register}
          errors={errors}
          fila={filasActuales[indice] ?? FILA_VACIA}
          productosDelProveedor={productosDelProveedor}
          onQuitar={fields.length > 1 ? () => remove(indice) : undefined}
        />
      ))}

      <Boton
        variante="secundario"
        className="self-start"
        onClick={() => append({ ...FILA_VACIA, vigenciaDesde: fechaDeHoy() })}
      >
        Agregar costo
      </Boton>

      <div className="flex gap-2">
        <Boton type="submit" disabled={informar.isPending}>
          Cargar costos
        </Boton>
        <Link to={`/admin/proveedores/${proveedorId}`} className="text-sm text-primary/70 hover:text-primary">
          Cancelar
        </Link>
      </div>
    </form>
  )
}

function atribuirErrorAFila(
  error: unknown,
  filas: DatosFilaCosto[],
  setError: ReturnType<typeof useForm<DatosCargaDeCostos>>['setError'],
) {
  if (!(error instanceof ErrorDeProveedores)) {
    setError('root', { message: 'No se pudo completar la operación.' })
    return
  }

  // contrato-api.md P9 (aprobado 2026-09-24): `fila` es el índice 0-based
  // que la API ya resuelve; reemplaza la heurística previa de buscar un
  // UUID en el mensaje del error (frágil frente a redacciones distintas).
  const indiceAfectado = error.fila
  const campo = campoDeCostoParaCodigo(error.codigo)
  if (indiceAfectado !== null && indiceAfectado >= 0 && indiceAfectado < filas.length && campo) {
    setError(`filas.${indiceAfectado}.${campo}` as FieldPath<DatosCargaDeCostos>, { message: error.message })
    return
  }

  setError('root', { message: error.message })
}

interface FilaCostoInputProps {
  indice: number
  register: ReturnType<typeof useForm<DatosCargaDeCostos>>['register']
  errors: ReturnType<typeof useForm<DatosCargaDeCostos>>['formState']['errors']
  fila: DatosFilaCosto
  productosDelProveedor: Producto[]
  onQuitar?: () => void
}

function FilaCostoInput({ indice, register, errors, fila, productosDelProveedor, onQuitar }: FilaCostoInputProps) {
  const producto = useProducto(fila.productoId || undefined)
  const alicuotas = useAlicuotas()

  const presentacionesDeCompra = (producto.data?.presentaciones ?? []).filter(
    (presentacion) => presentacion.activo && presentacion.usar_en_compra,
  )
  const presentacionElegida = presentacionesDeCompra.find(
    (presentacion) => presentacion.id === fila.presentacionId,
  )
  const alicuotaDelProducto = (alicuotas.data?.pages.flatMap((pagina) => pagina.items) ?? []).find(
    (alicuota) => alicuota.id === producto.data?.alicuota_id,
  )

  const erroresFila = errors.filas?.[indice]

  let vistaPrevia: string | null = null
  let errorDeVistaPrevia: string | null = null
  if (presentacionElegida && alicuotaDelProducto && fila.valor.trim() !== '') {
    try {
      const bonificacionFraccion = parsearImporteDesdeApi(fila.bonificacionPorcentaje || '0').div(100).toFixed(6)
      const costoBase = calcularCostoBase(
        fila.valor,
        fila.incluyeIva,
        alicuotaDelProducto.valor,
        bonificacionFraccion,
        presentacionElegida.unidades_base,
      )
      vistaPrevia = formatearCosto(costoBase)
    } catch (error) {
      errorDeVistaPrevia = error instanceof Error ? error.message : 'Datos inválidos.'
    }
  }

  return (
    <Card className="flex flex-wrap items-end gap-3">
      <Campo
        id={`filas.${indice}.productoId`}
        etiqueta="Producto"
        error={erroresFila?.productoId?.message}
      >
        <select
          id={`filas.${indice}.productoId`}
          className="rounded-md border border-border px-2 py-1 text-sm"
          {...register(`filas.${indice}.productoId` as const)}
        >
          <option value="">Elegí un producto</option>
          {productosDelProveedor.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nombre}
            </option>
          ))}
        </select>
      </Campo>

      <Campo
        id={`filas.${indice}.presentacionId`}
        etiqueta="Presentación"
        error={erroresFila?.presentacionId?.message}
      >
        <select
          id={`filas.${indice}.presentacionId`}
          className="rounded-md border border-border px-2 py-1 text-sm"
          {...register(`filas.${indice}.presentacionId` as const)}
          disabled={!fila.productoId}
        >
          <option value="">Elegí una presentación</option>
          {presentacionesDeCompra.map((presentacion) => (
            <option key={presentacion.id} value={presentacion.id}>
              {presentacion.nombre}
            </option>
          ))}
        </select>
      </Campo>

      <Campo id={`filas.${indice}.valor`} etiqueta="Valor" error={erroresFila?.valor?.message}>
        <input
          id={`filas.${indice}.valor`}
          className="w-28 rounded-md border border-border px-2 py-1 text-sm"
          {...register(`filas.${indice}.valor` as const)}
        />
      </Campo>

      <label className="flex items-center gap-1 text-sm text-primary">
        <input type="checkbox" {...register(`filas.${indice}.incluyeIva` as const)} />
        Incluye IVA
      </label>

      <Campo
        id={`filas.${indice}.bonificacionPorcentaje`}
        etiqueta="Bonificación %"
        error={erroresFila?.bonificacionPorcentaje?.message}
      >
        <input
          id={`filas.${indice}.bonificacionPorcentaje`}
          className="w-20 rounded-md border border-border px-2 py-1 text-sm"
          {...register(`filas.${indice}.bonificacionPorcentaje` as const)}
        />
      </Campo>

      <Campo
        id={`filas.${indice}.vigenciaDesde`}
        etiqueta="Vigencia desde"
        error={erroresFila?.vigenciaDesde?.message}
      >
        <input
          id={`filas.${indice}.vigenciaDesde`}
          type="date"
          className="rounded-md border border-border px-2 py-1 text-sm"
          {...register(`filas.${indice}.vigenciaDesde` as const)}
        />
      </Campo>

      <Campo id={`filas.${indice}.observacion`} etiqueta="Observación (opcional)">
        <input
          id={`filas.${indice}.observacion`}
          className="rounded-md border border-border px-2 py-1 text-sm"
          {...register(`filas.${indice}.observacion` as const)}
        />
      </Campo>

      <div className="text-sm text-primary/70" data-testid={`vista-previa-${indice}`}>
        {vistaPrevia && <>Costo base: {vistaPrevia}</>}
        {errorDeVistaPrevia && <span className="text-danger">{errorDeVistaPrevia}</span>}
      </div>

      {onQuitar && (
        <Boton variante="peligro" onClick={onQuitar}>
          Quitar
        </Boton>
      )}
    </Card>
  )
}

export default CostosCargaScreen
