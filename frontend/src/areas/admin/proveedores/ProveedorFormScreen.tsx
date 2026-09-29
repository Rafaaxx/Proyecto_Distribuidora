import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Boton } from '../../../components/ui/Button'
import { Campo } from '../../../components/ui/Field'
import {
  esquemaProveedorCrear,
  esquemaProveedorModificar,
  type DatosProveedorCrear,
  type DatosProveedorModificar,
} from '../../../domain/proveedores/proveedorSchema'
import { ErrorDeProveedores } from '../../../features/proveedores/errores'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { campoDeProveedorParaCodigo, type CampoProveedor } from '../../../features/proveedores/mapaErrorACampo'
import { useProveedor } from '../../../features/proveedores/useListados'
import { useCrearProveedor, useModificarProveedor } from '../../../features/proveedores/useMutaciones'

const SIN_PERMISO_DE_PROVEEDORES = 'No tenés permiso para gestionar proveedores.'

/** Estado sin permiso: mismo texto que la red de seguridad del 403, para
 * que el mensaje no revele por qué el usuario no ve la pantalla. */
function ProveedoresSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-primary">Proveedor</h1>
      <p className="text-sm text-primary/70">{SIN_PERMISO_DE_PROVEEDORES}</p>
    </main>
  )
}

/**
 * Alta y edición de proveedor (tarea 11.3). Sin `proveedorId` en la ruta
 * (`/admin/proveedores/nuevo`) es el formulario de alta; con `proveedorId`
 * (`/admin/proveedores/:proveedorId`) es la ficha: edición y
 * activar/desactivar (D5, `ProveedorConProductosActivosError` si tiene
 * productos activos).
 *
 * Tarea 8.4 del change 06b: la pantalla se decide **solo** con
 * `GESTIONAR_PROVEEDORES` de la consulta de sesión `['yo']`, con el
 * mecanismo compartido `<SiTienePermiso>` (ADR-027, `design.md` D4-A /
 * **B2**). Los formularios viven en componentes internos, así que sin
 * permiso no se montan y la pantalla no pide la ficha del proveedor para
 * averiguar si el usuario puede verla. El enlace "Cargar costos" se decide
 * por separado, con `EDITAR_COSTOS` (`01` §19).
 */
export function ProveedorFormScreen() {
  const { proveedorId } = useParams<{ proveedorId?: string }>()
  return (
    <SiTienePermiso permiso="GESTIONAR_PROVEEDORES" fallback={<ProveedoresSinPermiso />}>
      {proveedorId ? <ProveedorEdicion proveedorId={proveedorId} /> : <ProveedorAlta />}
    </SiTienePermiso>
  )
}

function mensajeDeError(error: unknown): { campo: CampoProveedor | null; mensaje: string } {
  if (error instanceof ErrorDeProveedores) {
    return { campo: campoDeProveedorParaCodigo(error.codigo), mensaje: error.message }
  }
  return { campo: null, mensaje: 'No se pudo completar la operación.' }
}

const setValueAsTextoOpcional = (valor: string) => (valor === '' ? null : valor)

function ProveedorAlta() {
  const navigate = useNavigate()
  const crear = useCrearProveedor()

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<DatosProveedorCrear>({
    resolver: zodResolver(esquemaProveedorCrear),
    defaultValues: { nombre: '', cuit: null, contacto: null, telefono: null, email: null },
  })

  const alEnviar = handleSubmit(async (datos) => {
    try {
      // Grupo 8, tarea 8.2 (decisión del usuario 2026-09-29): vuelve al
      // listado, mismo criterio que clientes -- el listado ya muestra el
      // proveedor nuevo (la mutación invalida el listado).
      await crear.mutateAsync(datos)
      navigate('/admin/proveedores')
    } catch (error) {
      const { campo, mensaje } = mensajeDeError(error)
      setError(campo ?? 'root', { message: mensaje })
    }
  })

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-primary">Nuevo proveedor</h1>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="nombre" etiqueta="Nombre" error={errors.nombre?.message}>
          <input id="nombre" className="rounded-md border border-border px-2 py-1 text-sm" {...register('nombre')} />
        </Campo>
        <Campo id="cuit" etiqueta="CUIT (opcional)" error={errors.cuit?.message}>
          <input
            id="cuit"
            className="rounded-md border border-border px-2 py-1 text-sm"
            {...register('cuit', { setValueAs: setValueAsTextoOpcional })}
          />
        </Campo>
        <Campo id="contacto" etiqueta="Contacto (opcional)" error={errors.contacto?.message}>
          <input
            id="contacto"
            className="rounded-md border border-border px-2 py-1 text-sm"
            {...register('contacto', { setValueAs: setValueAsTextoOpcional })}
          />
        </Campo>
        <Campo id="telefono" etiqueta="Teléfono (opcional)" error={errors.telefono?.message}>
          <input
            id="telefono"
            className="rounded-md border border-border px-2 py-1 text-sm"
            {...register('telefono', { setValueAs: setValueAsTextoOpcional })}
          />
        </Campo>
        <Campo id="email" etiqueta="Email (opcional)" error={errors.email?.message}>
          <input
            id="email"
            className="rounded-md border border-border px-2 py-1 text-sm"
            {...register('email', { setValueAs: setValueAsTextoOpcional })}
          />
        </Campo>

        {errors.root?.message && (
          <p role="alert" className="text-sm text-danger">
            {errors.root.message}
          </p>
        )}

        <div className="flex gap-2">
          <Boton type="submit" disabled={crear.isPending}>
            Crear proveedor
          </Boton>
          <Link to="/admin/proveedores" className="text-sm text-primary/70 hover:text-primary">
            Cancelar
          </Link>
        </div>
      </form>
    </main>
  )
}

function ProveedorEdicion({ proveedorId }: { proveedorId: string }) {
  const proveedor = useProveedor(proveedorId)
  const modificar = useModificarProveedor()

  if (proveedor.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }

  if (proveedor.isError) {
    return (
      <main>
        <p role="alert">No se pudo obtener el proveedor.</p>
      </main>
    )
  }

  return <ProveedorEdicionFormulario proveedorId={proveedorId} detalle={proveedor.data} modificar={modificar} />
}

function ProveedorEdicionFormulario({
  proveedorId,
  detalle,
  modificar,
}: {
  proveedorId: string
  detalle: { nombre: string; cuit: string | null; contacto: string | null; telefono: string | null; email: string | null; activo: boolean }
  modificar: ReturnType<typeof useModificarProveedor>
}) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<DatosProveedorModificar>({
    resolver: zodResolver(esquemaProveedorModificar),
    values: {
      nombre: detalle.nombre,
      cuit: detalle.cuit,
      contacto: detalle.contacto,
      telefono: detalle.telefono,
      email: detalle.email,
      activo: detalle.activo,
    },
  })

  const navigate = useNavigate()

  const alEnviar = handleSubmit(async (datos) => {
    try {
      await modificar.mutateAsync({ proveedorId, ...datos })
      // Grupo 8, tarea 8.2 (decisión del usuario 2026-09-29): vuelve al
      // listado tras guardar la edición, mismo criterio que clientes.
      navigate('/admin/proveedores')
    } catch (error) {
      const { campo, mensaje } = mensajeDeError(error)
      setError(campo ?? 'root', { message: mensaje })
    }
  })

  // D5: desactivar un proveedor con productos activos se rechaza con
  // `PROVEEDOR_CON_PRODUCTOS_ACTIVOS` (409) -- sin campo puntual, se
  // muestra como mensaje general (tarea 11.3).
  const desactivar = handleSubmit(async (datos) => {
    try {
      await modificar.mutateAsync({ proveedorId, ...datos, activo: !datos.activo })
    } catch (error) {
      const { mensaje } = mensajeDeError(error)
      setError('root', { message: mensaje })
    }
  })

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-primary">{detalle.nombre}</h1>
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <Campo id="nombre" etiqueta="Nombre" error={errors.nombre?.message}>
          <input id="nombre" className="rounded-md border border-border px-2 py-1 text-sm" {...register('nombre')} />
        </Campo>
        <Campo id="cuit" etiqueta="CUIT (opcional)" error={errors.cuit?.message}>
          <input
            id="cuit"
            className="rounded-md border border-border px-2 py-1 text-sm"
            {...register('cuit', { setValueAs: setValueAsTextoOpcional })}
          />
        </Campo>
        <Campo id="contacto" etiqueta="Contacto (opcional)" error={errors.contacto?.message}>
          <input
            id="contacto"
            className="rounded-md border border-border px-2 py-1 text-sm"
            {...register('contacto', { setValueAs: setValueAsTextoOpcional })}
          />
        </Campo>
        <Campo id="telefono" etiqueta="Teléfono (opcional)" error={errors.telefono?.message}>
          <input
            id="telefono"
            className="rounded-md border border-border px-2 py-1 text-sm"
            {...register('telefono', { setValueAs: setValueAsTextoOpcional })}
          />
        </Campo>
        <Campo id="email" etiqueta="Email (opcional)" error={errors.email?.message}>
          <input
            id="email"
            className="rounded-md border border-border px-2 py-1 text-sm"
            {...register('email', { setValueAs: setValueAsTextoOpcional })}
          />
        </Campo>

        {errors.root?.message && (
          <p role="alert" className="text-sm text-danger">
            {errors.root.message}
          </p>
        )}

        <div className="flex gap-2">
          <Boton type="submit" disabled={modificar.isPending}>
            Guardar cambios
          </Boton>
          <Boton
            type="button"
            variante={detalle.activo ? 'peligro' : 'secundario'}
            disabled={modificar.isPending}
            onClick={() => void desactivar()}
          >
            {detalle.activo ? 'Desactivar' : 'Reactivar'}
          </Boton>
          <Link to="/admin/proveedores" className="text-sm text-primary/70 hover:text-primary">
            Volver
          </Link>
          {detalle.activo && (
            /* `EDITAR_COSTOS` de `['yo']`, no una consulta al servidor para
               averiguarlo (ADR-027; escenario "Enlace 'Cargar costos' desde
               la ficha del proveedor según el permiso"). */
            <SiTienePermiso permiso="EDITAR_COSTOS">
              <Link to={`/admin/proveedores/${proveedorId}/costos`} className="text-sm text-primary/70 hover:text-primary">
                Cargar costos
              </Link>
            </SiTienePermiso>
          )}
        </div>
      </form>
    </main>
  )
}

export default ProveedorFormScreen
