import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useFieldArray, useForm, type FieldPath } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Badge } from '../../../components/ui/Badge'
import { Boton } from '../../../components/ui/Button'
import { Campo } from '../../../components/ui/Field'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { visualizarCantidad } from '../../../domain/catalogo/cantidades'
import {
  esquemaPresentacion,
  esquemaPresentacionModificar,
  esquemaProducto,
  esquemaProductoBase,
  type DatosPresentacion,
  type DatosPresentacionModificar,
  type DatosProducto,
  type DatosProductoBase,
} from '../../../domain/catalogo/productoSchema'
import type { Presentacion, ProductoDetalle } from '../../../features/catalogo/api'
import { ErrorDeCatalogo } from '../../../features/catalogo/errores'
import { campoDeProductoParaCodigo, type CampoProducto } from '../../../features/catalogo/mapaErrorACampo'
import { useCategorias, useMarcas, useProducto } from '../../../features/catalogo/useListados'
import {
  useAgregarPresentacion,
  useCambiarReferencia,
  useCrearProducto,
  useModificarPresentacion,
  useModificarProducto,
} from '../../../features/catalogo/useMutacionesCatalogo'
import { useAlicuotas } from '../../../features/configuracion/useAlicuotas'

/**
 * Detalle + alta/edición de producto y presentaciones (tarea 10.5).
 *
 * Sin un `productoId` en la ruta (`/admin/catalogo/productos/nuevo`) es el
 * formulario de alta (producto y sus presentaciones iniciales en un único
 * envío, `POST /catalogo/productos`, CAT-02/CAT-03). Con `productoId`
 * (`/admin/catalogo/productos/:productoId`) es edición: los datos base del
 * producto se modifican con `PUT /catalogo/productos/{id}`, pero las
 * presentaciones NO viajan ahí -- el backend las gestiona con sus propios
 * comandos (`PRESENTACION_AGREGAR`/`PRESENTACION_MODIFICAR`,
 * `design.md` D-comandos), así que la sección de presentaciones tiene sus
 * propios formularios y envíos.
 */
export function ProductoFormScreen() {
  const { productoId } = useParams<{ productoId?: string }>()
  if (productoId) {
    return <ProductoEdicion productoId={productoId} />
  }
  return <ProductoAlta />
}

const PRESENTACION_VACIA: DatosPresentacion = {
  nombre: '',
  unidadesBase: 1,
  usarEnVenta: true,
  usarEnCompra: false,
  esReferencia: true,
}

function mensajeDeError(error: unknown): { campo: CampoProducto | null; mensaje: string } {
  if (error instanceof ErrorDeCatalogo) {
    return { campo: campoDeProductoParaCodigo(error.codigo), mensaje: error.message }
  }
  return { campo: null, mensaje: 'No se pudo completar la operación.' }
}

/** Texto de equivalencia CAT-08 de una presentación contra la de
 * referencia vigente (`Pack x24` sobre `Caja x12` → "2 caja(s) + 0
 * unidad(es)"): cuántas veces entra la referencia en esta presentación. */
function textoEquivalencia(unidadesPresentacion: number, referencia: { nombre: string; unidadesBase: number }): string | null {
  if (!Number.isSafeInteger(unidadesPresentacion) || unidadesPresentacion < 1) {
    return null
  }
  try {
    const { cajas, unidades } = visualizarCantidad(unidadesPresentacion, referencia.unidadesBase)
    return `= ${cajas} ${referencia.nombre}(s) + ${unidades} unidad(es)`
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------
// Alta
// ---------------------------------------------------------------------

function ProductoAlta() {
  const navigate = useNavigate()
  const categorias = useCategorias()
  const marcas = useMarcas()
  const alicuotas = useAlicuotas()
  const crear = useCrearProducto()

  const {
    register,
    control,
    handleSubmit,
    setError,
    setValue,
    watch,
    formState: { errors },
  } = useForm<DatosProducto>({
    resolver: zodResolver(esquemaProducto),
    defaultValues: {
      codigo: '',
      nombre: '',
      categoriaId: '',
      marcaId: null,
      unidadBase: 'unidad',
      alicuotaId: '',
      presentaciones: [PRESENTACION_VACIA],
    },
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'presentaciones' })
  const presentacionesActuales = watch('presentaciones')
  const referencia = presentacionesActuales.find((presentacion) => presentacion.esReferencia)

  function marcarComoReferencia(indice: number) {
    presentacionesActuales.forEach((_presentacion, otroIndice) => {
      setValue(`presentaciones.${otroIndice}.esReferencia`, otroIndice === indice)
    })
  }

  // CAT-05: los selectores del formulario de producto ofrecen solo
  // categorías/marcas activas (tarea 10.6).
  const opcionesCategoria = (categorias.data?.pages.flatMap((pagina) => pagina.items) ?? []).filter(
    (categoria) => categoria.activo,
  )
  const opcionesMarca = (marcas.data?.pages.flatMap((pagina) => pagina.items) ?? []).filter((marca) => marca.activo)
  // D12: el selector de alícuota ofrece solo las activas (mismo criterio
  // que categorías/marcas, CAT-05); el filtro del cliente no reemplaza la
  // validación del servidor (`PRODUCTO_CREAR` ya rechaza una alícuota
  // inactiva o ajena).
  const opcionesAlicuota = (alicuotas.data?.pages.flatMap((pagina) => pagina.items) ?? []).filter(
    (alicuota) => alicuota.activo,
  )

  const alEnviar = handleSubmit(async (datos) => {
    try {
      const detalle = await crear.mutateAsync({
        codigo: datos.codigo,
        nombre: datos.nombre,
        categoria_id: datos.categoriaId,
        marca_id: datos.marcaId,
        unidad_base: datos.unidadBase,
        alicuota_id: datos.alicuotaId,
        presentaciones: datos.presentaciones.map((presentacion) => ({
          nombre: presentacion.nombre,
          unidades_base: presentacion.unidadesBase,
          usar_en_venta: presentacion.usarEnVenta,
          usar_en_compra: presentacion.usarEnCompra,
          es_referencia: presentacion.esReferencia,
        })),
      })
      navigate(`/admin/catalogo/productos/${detalle.id}`)
    } catch (error) {
      const { campo, mensaje } = mensajeDeError(error)
      setError(campo ?? 'root', { message: mensaje })
    }
  })

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-primary">Nuevo producto</h1>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="codigo" etiqueta="Código" error={errors.codigo?.message}>
          <input id="codigo" className="rounded-md border border-border px-2 py-1 text-sm" {...register('codigo')} />
        </Campo>
        <Campo id="nombre" etiqueta="Nombre" error={errors.nombre?.message}>
          <input id="nombre" className="rounded-md border border-border px-2 py-1 text-sm" {...register('nombre')} />
        </Campo>
        <Campo id="categoriaId" etiqueta="Categoría" error={errors.categoriaId?.message}>
          <select id="categoriaId" className="rounded-md border border-border px-2 py-1 text-sm" {...register('categoriaId')}>
            <option value="">Elegí una categoría</option>
            {opcionesCategoria.map((categoria) => (
              <option key={categoria.id} value={categoria.id}>
                {categoria.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <Campo id="marcaId" etiqueta="Marca (opcional)" error={errors.marcaId?.message}>
          <select
            id="marcaId"
            className="rounded-md border border-border px-2 py-1 text-sm"
            {...register('marcaId', {
              setValueAs: (valor: string) => (valor === '' ? null : valor),
            })}
          >
            <option value="">Sin marca</option>
            {opcionesMarca.map((marca) => (
              <option key={marca.id} value={marca.id}>
                {marca.nombre}
              </option>
            ))}
          </select>
        </Campo>
        <Campo id="unidadBase" etiqueta="Unidad base" error={errors.unidadBase?.message}>
          <input
            id="unidadBase"
            className="rounded-md border border-border px-2 py-1 text-sm"
            {...register('unidadBase')}
          />
        </Campo>
        <Campo id="alicuotaId" etiqueta="Alícuota" error={errors.alicuotaId?.message}>
          <select id="alicuotaId" className="rounded-md border border-border px-2 py-1 text-sm" {...register('alicuotaId')}>
            <option value="">Elegí una alícuota</option>
            {opcionesAlicuota.map((alicuota) => (
              <option key={alicuota.id} value={alicuota.id}>
                {alicuota.nombre}
              </option>
            ))}
          </select>
        </Campo>

        <fieldset className="flex flex-col gap-3 rounded-md border border-border p-3">
          <legend className="px-1 text-sm font-medium text-primary">Presentaciones</legend>
          {errors.presentaciones?.root?.message && (
            <p role="alert" className="text-sm text-danger">
              {errors.presentaciones.root.message}
            </p>
          )}
          {typeof errors.presentaciones?.message === 'string' && (
            <p role="alert" className="text-sm text-danger">
              {errors.presentaciones.message}
            </p>
          )}
          {fields.map((campo, indice) => {
            const presentacion = presentacionesActuales[indice]
            const equivalencia =
              referencia && presentacion && !presentacion.esReferencia && referencia !== presentacion
                ? textoEquivalencia(presentacion.unidadesBase, {
                    nombre: referencia.nombre || 'referencia',
                    unidadesBase: referencia.unidadesBase,
                  })
                : null
            return (
              <div key={campo.id} className="flex flex-wrap items-end gap-2 border-b border-border pb-2">
                <Campo
                  id={`presentaciones.${indice}.nombre`}
                  etiqueta="Nombre"
                  error={errors.presentaciones?.[indice]?.nombre?.message}
                >
                  <input
                    id={`presentaciones.${indice}.nombre`}
                    className="rounded-md border border-border px-2 py-1 text-sm"
                    {...register(`presentaciones.${indice}.nombre` as const)}
                  />
                </Campo>
                <Campo
                  id={`presentaciones.${indice}.unidadesBase`}
                  etiqueta="Unidades base"
                  error={errors.presentaciones?.[indice]?.unidadesBase?.message}
                >
                  <input
                    id={`presentaciones.${indice}.unidadesBase`}
                    type="number"
                    className="w-24 rounded-md border border-border px-2 py-1 text-sm"
                    {...register(`presentaciones.${indice}.unidadesBase` as const, { valueAsNumber: true })}
                  />
                </Campo>
                <label className="flex items-center gap-1 text-sm text-primary">
                  <input type="checkbox" {...register(`presentaciones.${indice}.usarEnVenta` as const)} />
                  Venta
                </label>
                <label className="flex items-center gap-1 text-sm text-primary">
                  <input type="checkbox" {...register(`presentaciones.${indice}.usarEnCompra` as const)} />
                  Compra
                </label>
                <label className="flex items-center gap-1 text-sm text-primary">
                  <input
                    type="radio"
                    name="presentacion-referencia"
                    checked={presentacion?.esReferencia ?? false}
                    onChange={() => marcarComoReferencia(indice)}
                  />
                  Referencia
                </label>
                {equivalencia && <span className="text-sm text-primary/70">{equivalencia}</span>}
                {fields.length > 1 && (
                  <Boton variante="peligro" onClick={() => remove(indice)}>
                    Quitar
                  </Boton>
                )}
              </div>
            )
          })}
          <Boton
            variante="secundario"
            onClick={() => append({ ...PRESENTACION_VACIA, esReferencia: false })}
          >
            Agregar presentación
          </Boton>
        </fieldset>

        {errors.root?.message && (
          <p role="alert" className="text-sm text-danger">
            {errors.root.message}
          </p>
        )}

        <div className="flex gap-2">
          <Boton type="submit" disabled={crear.isPending}>
            Crear producto
          </Boton>
          <Link to="/admin/catalogo/productos" className="text-sm text-primary/70 hover:text-primary">
            Cancelar
          </Link>
        </div>
      </form>
    </main>
  )
}

// ---------------------------------------------------------------------
// Edición
// ---------------------------------------------------------------------

function ProductoEdicion({ productoId }: { productoId: string }) {
  const producto = useProducto(productoId)

  if (producto.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }

  if (producto.isError) {
    return (
      <main>
        <p role="alert">No se pudo obtener el producto.</p>
      </main>
    )
  }

  return (
    <main className="flex flex-col gap-6">
      <ProductoBaseForm detalle={producto.data} />
      <PresentacionesSeccion detalle={producto.data} />
    </main>
  )
}

function ProductoBaseForm({ detalle }: { detalle: ProductoDetalle }) {
  const navigate = useNavigate()
  const categorias = useCategorias()
  const marcas = useMarcas()
  const alicuotas = useAlicuotas()
  const modificar = useModificarProducto()

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<DatosProductoBase>({
    resolver: zodResolver(esquemaProductoBase),
    values: {
      codigo: detalle.codigo,
      nombre: detalle.nombre,
      categoriaId: detalle.categoria_id,
      marcaId: detalle.marca_id,
      unidadBase: detalle.unidad_base,
      alicuotaId: detalle.alicuota_id,
      activo: detalle.activo,
    },
  })

  // CAT-05: los selectores del formulario de producto ofrecen solo
  // categorías/marcas activas (tarea 10.6).
  const opcionesCategoria = (categorias.data?.pages.flatMap((pagina) => pagina.items) ?? []).filter(
    (categoria) => categoria.activo,
  )
  const opcionesMarca = (marcas.data?.pages.flatMap((pagina) => pagina.items) ?? []).filter((marca) => marca.activo)
  const opcionesAlicuota = (alicuotas.data?.pages.flatMap((pagina) => pagina.items) ?? []).filter(
    (alicuota) => alicuota.activo,
  )

  const alEnviar = handleSubmit(async (datos) => {
    try {
      await modificar.mutateAsync({
        productoId: detalle.id,
        codigo: datos.codigo,
        nombre: datos.nombre,
        categoria_id: datos.categoriaId,
        marca_id: datos.marcaId,
        unidad_base: datos.unidadBase,
        alicuota_id: datos.alicuotaId,
        activo: datos.activo,
      })
      // Tarea 10.12 (bug 13.5): al guardar cambios exitosamente, volver al
      // listado del catálogo (ruta absoluta, ver tarea 10.8).
      navigate('/admin/catalogo')
    } catch (error) {
      const { campo, mensaje } = mensajeDeError(error)
      setError((campo as FieldPath<DatosProductoBase>) ?? 'root', { message: mensaje })
    }
  })

  return (
    <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-primary">{detalle.codigo} — {detalle.nombre}</h1>
      <Campo id="codigo" etiqueta="Código" error={errors.codigo?.message}>
        <input id="codigo" className="rounded-md border border-border px-2 py-1 text-sm" {...register('codigo')} />
      </Campo>
      <Campo id="nombre" etiqueta="Nombre" error={errors.nombre?.message}>
        <input id="nombre" className="rounded-md border border-border px-2 py-1 text-sm" {...register('nombre')} />
      </Campo>
      <Campo id="categoriaId" etiqueta="Categoría" error={errors.categoriaId?.message}>
        <select id="categoriaId" className="rounded-md border border-border px-2 py-1 text-sm" {...register('categoriaId')}>
          {opcionesCategoria.map((categoria) => (
            <option key={categoria.id} value={categoria.id}>
              {categoria.nombre}
            </option>
          ))}
        </select>
      </Campo>
      <Campo id="marcaId" etiqueta="Marca" error={errors.marcaId?.message}>
        <select
          id="marcaId"
          className="rounded-md border border-border px-2 py-1 text-sm"
          {...register('marcaId', { setValueAs: (valor: string) => (valor === '' ? null : valor) })}
        >
          <option value="">Sin marca</option>
          {opcionesMarca.map((marca) => (
            <option key={marca.id} value={marca.id}>
              {marca.nombre}
            </option>
          ))}
        </select>
      </Campo>
      <Campo id="unidadBase" etiqueta="Unidad base" error={errors.unidadBase?.message}>
        <input id="unidadBase" className="rounded-md border border-border px-2 py-1 text-sm" {...register('unidadBase')} />
      </Campo>
      <Campo id="alicuotaId" etiqueta="Alícuota" error={errors.alicuotaId?.message}>
        <select id="alicuotaId" className="rounded-md border border-border px-2 py-1 text-sm" {...register('alicuotaId')}>
          {opcionesAlicuota.map((alicuota) => (
            <option key={alicuota.id} value={alicuota.id}>
              {alicuota.nombre}
            </option>
          ))}
        </select>
      </Campo>
      <label className="flex items-center gap-2 text-sm text-primary">
        <input type="checkbox" {...register('activo')} />
        Activo
      </label>
      {errors.root?.message && (
        <p role="alert" className="text-sm text-danger">
          {errors.root.message}
        </p>
      )}
      <Boton type="submit" disabled={modificar.isPending} className="self-start">
        Guardar cambios
      </Boton>
    </form>
  )
}

function PresentacionesSeccion({ detalle }: { detalle: ProductoDetalle }) {
  const [presentacionEnEdicion, setPresentacionEnEdicion] = useState<Presentacion | null>(null)
  const [agregando, setAgregando] = useState(false)
  const cambiarReferencia = useCambiarReferencia()
  const referencia = detalle.presentaciones.find((presentacion) => presentacion.es_referencia) ?? null

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-primary">Presentaciones</h2>
        <Boton variante="secundario" onClick={() => setAgregando(true)}>
          Agregar presentación
        </Boton>
      </div>
      <Card className="overflow-x-auto p-0">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 font-medium text-primary">Nombre</th>
              <th className="px-3 py-2 font-medium text-primary">Unidades</th>
              <th className="px-3 py-2 font-medium text-primary">Equivalencia</th>
              <th className="px-3 py-2 font-medium text-primary">Referencia</th>
              <th className="px-3 py-2 font-medium text-primary">Estado</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {detalle.presentaciones.map((presentacion) => {
              const equivalencia =
                referencia && presentacion.id !== referencia.id
                  ? textoEquivalencia(presentacion.unidades_base, {
                      nombre: referencia.nombre,
                      unidadesBase: referencia.unidades_base,
                    })
                  : null
              return (
                <tr key={presentacion.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2">{presentacion.nombre}</td>
                  <td className="px-3 py-2">{presentacion.unidades_base}</td>
                  <td className="px-3 py-2">{equivalencia ?? '—'}</td>
                  <td className="px-3 py-2">
                    {presentacion.es_referencia ? <Badge variante="positivo">Referencia</Badge> : 'No'}
                  </td>
                  <td className="px-3 py-2">
                    <Badge variante={presentacion.activo ? 'positivo' : 'neutral'}>
                      {presentacion.activo ? 'Activa' : 'Inactiva'}
                    </Badge>
                  </td>
                  <td className="flex gap-2 px-3 py-2">
                    <Boton variante="secundario" onClick={() => setPresentacionEnEdicion(presentacion)}>
                      Editar
                    </Boton>
                    {!presentacion.es_referencia && presentacion.usar_en_venta && presentacion.activo && (
                      <Boton
                        variante="secundario"
                        disabled={cambiarReferencia.isPending}
                        onClick={() =>
                          cambiarReferencia.mutate({ productoId: detalle.id, presentacionId: presentacion.id })
                        }
                      >
                        Usar como referencia
                      </Boton>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </Card>
      {cambiarReferencia.isError && (
        <p role="alert" className="text-sm text-danger">
          {mensajeDeError(cambiarReferencia.error).mensaje}
        </p>
      )}

      <Dialogo abierto={agregando} titulo="Agregar presentación" onCerrar={() => setAgregando(false)}>
        <PresentacionAgregarForm productoId={detalle.id} onListo={() => setAgregando(false)} />
      </Dialogo>

      <Dialogo
        abierto={presentacionEnEdicion !== null}
        titulo="Editar presentación"
        onCerrar={() => setPresentacionEnEdicion(null)}
      >
        {presentacionEnEdicion && (
          <PresentacionEditarForm
            productoId={detalle.id}
            presentacion={presentacionEnEdicion}
            onListo={() => setPresentacionEnEdicion(null)}
          />
        )}
      </Dialogo>
    </section>
  )
}

function PresentacionAgregarForm({ productoId, onListo }: { productoId: string; onListo: () => void }) {
  const agregar = useAgregarPresentacion()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<DatosPresentacion>({
    resolver: zodResolver(esquemaPresentacion),
    defaultValues: { nombre: '', unidadesBase: 1, usarEnVenta: true, usarEnCompra: false, esReferencia: false },
  })

  const alEnviar = handleSubmit(async (datos) => {
    try {
      await agregar.mutateAsync({
        productoId,
        nombre: datos.nombre,
        unidades_base: datos.unidadesBase,
        usar_en_venta: datos.usarEnVenta,
        usar_en_compra: datos.usarEnCompra,
      })
      onListo()
    } catch (error) {
      const { campo, mensaje } = mensajeDeError(error)
      setError((campo as FieldPath<DatosPresentacion>) ?? 'root', { message: mensaje })
    }
  })

  return (
    <form onSubmit={alEnviar} noValidate className="flex flex-col gap-3">
      <Campo id="ap-nombre" etiqueta="Nombre" error={errors.nombre?.message}>
        <input id="ap-nombre" className="rounded-md border border-border px-2 py-1 text-sm" {...register('nombre')} />
      </Campo>
      <Campo id="ap-unidades" etiqueta="Unidades base" error={errors.unidadesBase?.message}>
        <input
          id="ap-unidades"
          type="number"
          className="rounded-md border border-border px-2 py-1 text-sm"
          {...register('unidadesBase', { valueAsNumber: true })}
        />
      </Campo>
      <label className="flex items-center gap-2 text-sm text-primary">
        <input type="checkbox" {...register('usarEnVenta')} />
        Usar en venta
      </label>
      <label className="flex items-center gap-2 text-sm text-primary">
        <input type="checkbox" {...register('usarEnCompra')} />
        Usar en compra
      </label>
      {errors.root?.message && (
        <p role="alert" className="text-sm text-danger">
          {errors.root.message}
        </p>
      )}
      <Boton type="submit" disabled={agregar.isPending} className="self-start">
        Agregar
      </Boton>
    </form>
  )
}

function PresentacionEditarForm({
  productoId,
  presentacion,
  onListo,
}: {
  productoId: string
  presentacion: Presentacion
  onListo: () => void
}) {
  const modificar = useModificarPresentacion()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<DatosPresentacionModificar>({
    resolver: zodResolver(esquemaPresentacionModificar),
    defaultValues: {
      nombre: presentacion.nombre,
      unidadesBase: presentacion.unidades_base,
      usarEnVenta: presentacion.usar_en_venta,
      usarEnCompra: presentacion.usar_en_compra,
      esReferencia: presentacion.es_referencia,
      activo: presentacion.activo,
    },
  })

  const alEnviar = handleSubmit(async (datos) => {
    try {
      await modificar.mutateAsync({
        presentacionId: presentacion.id,
        productoId,
        nombre: datos.nombre,
        unidades_base: datos.unidadesBase,
        usar_en_venta: datos.usarEnVenta,
        usar_en_compra: datos.usarEnCompra,
        activo: datos.activo,
      })
      onListo()
    } catch (error) {
      const { campo, mensaje } = mensajeDeError(error)
      setError((campo as FieldPath<DatosPresentacionModificar>) ?? 'root', { message: mensaje })
    }
  })

  return (
    <form onSubmit={alEnviar} noValidate className="flex flex-col gap-3">
      <Campo id="ep-nombre" etiqueta="Nombre" error={errors.nombre?.message}>
        <input id="ep-nombre" className="rounded-md border border-border px-2 py-1 text-sm" {...register('nombre')} />
      </Campo>
      <Campo id="ep-unidades" etiqueta="Unidades base" error={errors.unidadesBase?.message}>
        <input
          id="ep-unidades"
          type="number"
          className="rounded-md border border-border px-2 py-1 text-sm"
          {...register('unidadesBase', { valueAsNumber: true })}
        />
      </Campo>
      <label className="flex items-center gap-2 text-sm text-primary">
        <input type="checkbox" {...register('usarEnVenta')} />
        Usar en venta
      </label>
      <label className="flex items-center gap-2 text-sm text-primary">
        <input type="checkbox" {...register('usarEnCompra')} />
        Usar en compra
      </label>
      <label className="flex items-center gap-2 text-sm text-primary">
        <input type="checkbox" {...register('activo')} />
        Activa
      </label>
      {errors.root?.message && (
        <p role="alert" className="text-sm text-danger">
          {errors.root.message}
        </p>
      )}
      <Boton type="submit" disabled={modificar.isPending} className="self-start">
        Guardar
      </Boton>
    </form>
  )
}
