import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  ESTADOS_CLIENTE,
  TIPOS_DOCUMENTO,
  esquemaClienteCrear,
  esquemaClienteModificar,
  type DatosClienteCrear,
  type DatosClienteModificar,
} from '../../../domain/clientes/clienteSchema'
import type { Cliente } from '../../../features/clientes/api'
import { ErrorDeClientes } from '../../../features/clientes/errores'
import { campoDeClienteParaCodigo, type CampoCliente } from '../../../features/clientes/mapaErrorACampo'
import { useCliente } from '../../../features/clientes/useListados'
import { esErrorDeRed, useCrearCliente, useModificarCliente } from '../../../features/clientes/useMutaciones'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'
import { SaldoDeCuenta } from '../cuentas-corrientes/SaldoDeCuenta'

const SIN_PERMISO_DE_CLIENTES = 'No tenés permiso para gestionar clientes.'
const AVISO_SIN_CONEXION = 'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.'
const HEREDA_DE_LA_ORGANIZACION = 'Hereda de la organización'

/** Formatea un importe de la API (`"150000.00"` o `null`) para mostrarlo en
 * solo lectura (`lib/money.ts`, INV-03: nunca pasa por `number`). `null`
 * significa HEREDA de la organización (CRE-03, D8), no cero. Mismo criterio
 * que `valorVigente` de `ClienteCreditoScreen.tsx`. */
function valorVigente(valorApi: string | null): string {
  return valorApi === null ? HEREDA_DE_LA_ORGANIZACION : formatearImporte(parsearImporteDesdeApi(valorApi))
}

/** Texto de la tolerancia offline en solo lectura: tipo y valor van juntos
 * (D6); si el tipo es `null` el par entero hereda de la organización. */
function textoTolerancia(tipo: string | null, valor: string | null): string {
  return tipo === null ? HEREDA_DE_LA_ORGANIZACION : `${tipo}: ${valorVigente(valor)}`
}

/** Estado sin permiso: mismo texto que la red de seguridad del 403, para
 * que el mensaje no revele por qué el usuario no ve la pantalla (mismo
 * criterio que `ProveedorFormScreen.tsx`). */
function ClientesSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Cliente" />
      <p className="text-sm text-primary/70">{SIN_PERMISO_DE_CLIENTES}</p>
    </main>
  )
}

/**
 * Alta y edición de cliente (change 07, grupo 5, tarea 5.3; `design.md`
 * D9 enmienda 2026-09-29). Sin `clienteId` en la ruta
 * (`/admin/clientes/nuevo`) es el alta; con `clienteId`
 * (`/admin/clientes/:clienteId`) es la ficha: edición y cambio de estado.
 *
 * La pantalla se decide **solo** con `GESTIONAR_CLIENTES` de la consulta de
 * sesión `['yo']` (ADR-027, `design.md` D3), mismo criterio que
 * `ProveedorFormScreen.tsx`: sin permiso los formularios no se montan.
 */
export function ClienteFormScreen() {
  const { clienteId } = useParams<{ clienteId?: string }>()
  return (
    <SiTienePermiso permiso="GESTIONAR_CLIENTES" fallback={<ClientesSinPermiso />}>
      {clienteId ? <ClienteEdicion clienteId={clienteId} /> : <ClienteAlta />}
    </SiTienePermiso>
  )
}

/**
 * Traduce el error de una mutación al campo/mensaje del formulario. Un
 * error de RED (`esErrorDeRed`, agotados los reintentos de
 * `debeReintentar`) se muestra como aviso general, sin campo puntual: los
 * cuatro comandos de este módulo son `ONLINE` puros y esta área no tiene
 * cola offline, así que la pantalla solo avisa que hace falta conexión, sin
 * encolar nada (tarea 5.3).
 */
function mensajeDeError(error: unknown): { campo: CampoCliente | null; mensaje: string } {
  if (esErrorDeRed(error)) {
    return { campo: null, mensaje: AVISO_SIN_CONEXION }
  }
  if (error instanceof ErrorDeClientes) {
    return { campo: campoDeClienteParaCodigo(error.codigo), mensaje: error.message }
  }
  return { campo: null, mensaje: 'No se pudo completar la operación.' }
}

const setValueAsTextoOpcional = (valor: string) => (valor === '' ? null : valor)

function ClienteAlta() {
  const navigate = useNavigate()
  const crear = useCrearCliente()

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<DatosClienteCrear>({
    resolver: zodResolver(esquemaClienteCrear),
    defaultValues: {
      nombre: '',
      direccion: '',
      contacto: '',
      razon_social: null,
      documento_tipo: null,
      documento_numero: null,
      telefono: null,
      email: null,
      codigo: null,
      estado_facturacion_default: null,
    },
  })

  const alEnviar = handleSubmit(async (datos) => {
    try {
      // Grupo 8, tarea 8.2 (decisión del usuario 2026-09-29): vuelve al
      // listado, no a la ficha recién creada -- el listado ya muestra el
      // cliente nuevo (la mutación invalida `clavesClientes.clientes()`).
      await crear.mutateAsync(datos)
      navigate('/admin/clientes')
    } catch (error) {
      const { campo, mensaje } = mensajeDeError(error)
      // `estado` no es un campo del alta (D7: el cliente siempre nace
      // ACTIVO): un código de error que mapee a ese campo se muestra como
      // mensaje general acá.
      const campoValido = campo && campo !== 'estado' ? campo : null
      setError(campoValido ?? 'root', { message: mensaje })
    }
  })

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Nuevo cliente" />
      <Card>
        <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
          <Campo id="nombre" etiqueta="Nombre" error={errors.nombre?.message}>
            <input id="nombre" className="rounded-md border border-border px-2 py-1 text-sm" {...register('nombre')} />
          </Campo>
          <Campo id="direccion" etiqueta="Dirección" error={errors.direccion?.message}>
            <input
              id="direccion"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('direccion')}
            />
          </Campo>
          <Campo id="contacto" etiqueta="Contacto" error={errors.contacto?.message}>
            <input
              id="contacto"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('contacto')}
            />
          </Campo>
          <Campo id="razon_social" etiqueta="Razón social (opcional)">
            <input
              id="razon_social"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('razon_social', { setValueAs: setValueAsTextoOpcional })}
            />
          </Campo>
          <div className="flex gap-3">
            <Campo id="documento_tipo" etiqueta="Tipo de documento (opcional)">
              <select
                id="documento_tipo"
                className="rounded-md border border-border px-2 py-1 text-sm"
                {...register('documento_tipo', { setValueAs: setValueAsTextoOpcional })}
              >
                <option value="">Sin documento</option>
                {TIPOS_DOCUMENTO.map((tipo) => (
                  <option key={tipo} value={tipo}>
                    {tipo}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo id="documento_numero" etiqueta="Número de documento" error={errors.documento_numero?.message}>
              <input
                id="documento_numero"
                className="rounded-md border border-border px-2 py-1 text-sm"
                {...register('documento_numero', { setValueAs: setValueAsTextoOpcional })}
              />
            </Campo>
          </div>
          <Campo id="codigo" etiqueta="Código (opcional)" error={errors.codigo?.message}>
            <input
              id="codigo"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('codigo', { setValueAs: setValueAsTextoOpcional })}
            />
          </Campo>
          <Campo id="telefono" etiqueta="Teléfono (opcional)">
            <input
              id="telefono"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('telefono', { setValueAs: setValueAsTextoOpcional })}
            />
          </Campo>
          <Campo id="email" etiqueta="Email (opcional)">
            <input
              id="email"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('email', { setValueAs: setValueAsTextoOpcional })}
            />
          </Campo>

          {errors.root?.message && <Alert>{errors.root.message}</Alert>}

          <div className="flex gap-2">
            <Boton type="submit" disabled={crear.isPending}>
              Crear cliente
            </Boton>
            <Link to="/admin/clientes" className="text-sm text-primary/70 hover:text-primary">
              Cancelar
            </Link>
          </div>
        </form>
      </Card>
    </main>
  )
}

function ClienteEdicion({ clienteId }: { clienteId: string }) {
  const cliente = useCliente(clienteId)
  const modificar = useModificarCliente()

  if (cliente.isPending) {
    return (
      <main>
        <p>Cargando…</p>
      </main>
    )
  }

  if (cliente.isError) {
    return (
      <main>
        <p role="alert">No se pudo obtener el cliente.</p>
      </main>
    )
  }

  return <ClienteEdicionFormulario clienteId={clienteId} detalle={cliente.data} modificar={modificar} />
}

function ClienteEdicionFormulario({
  clienteId,
  detalle,
  modificar,
}: {
  clienteId: string
  detalle: Cliente
  modificar: ReturnType<typeof useModificarCliente>
}) {
  const navigate = useNavigate()
  const [datosPendientes, setDatosPendientes] = useState<DatosClienteModificar | null>(null)
  const [textoConfirmacion, setTextoConfirmacion] = useState('')

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<DatosClienteModificar>({
    resolver: zodResolver(esquemaClienteModificar),
    values: {
      nombre: detalle.nombre,
      direccion: detalle.direccion,
      contacto: detalle.contacto,
      razon_social: detalle.razon_social,
      documento_tipo: detalle.documento_tipo,
      documento_numero: detalle.documento_numero,
      telefono: detalle.telefono,
      email: detalle.email,
      codigo: detalle.codigo,
      estado_facturacion_default: detalle.estado_facturacion_default,
      estado: detalle.estado as (typeof ESTADOS_CLIENTE)[number],
    },
  })

  async function enviar(datos: DatosClienteModificar) {
    try {
      await modificar.mutateAsync({ clienteId, ...datos })
      // Grupo 8, tarea 8.2 (decisión del usuario 2026-09-29): vuelve al
      // listado, mismo criterio que el alta.
      navigate('/admin/clientes')
    } catch (error) {
      const { campo, mensaje } = mensajeDeError(error)
      setError(campo ?? 'root', { message: mensaje })
    }
  }

  const alEnviar = handleSubmit(async (datos) => {
    // `design.md` D7 (confirmación tipeada, solo frontend): inactivar exige
    // tipear el nombre del cliente en un diálogo ANTES de enviar
    // `CLIENTE_MODIFICAR` con `estado = INACTIVO`. El texto confirmado NO
    // viaja en el comando -- la protección real es la máquina de estados y
    // CLI-06/ADR-030 en el servidor; esto solo evita un clic apurado.
    if (datos.estado === 'INACTIVO' && detalle.estado !== 'INACTIVO') {
      setDatosPendientes(datos)
      setTextoConfirmacion('')
      return
    }
    await enviar(datos)
  })

  const confirmarInactivacion = async () => {
    if (!datosPendientes) return
    await enviar(datosPendientes)
    setDatosPendientes(null)
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader
        titulo={detalle.nombre}
        acciones={
          <SiTienePermiso permiso="GESTIONAR_CREDITO">
            <Link
              to={`/admin/clientes/${clienteId}/credito`}
              className="text-sm text-primary/70 hover:text-primary hover:underline"
            >
              Crédito
            </Link>
          </SiTienePermiso>
        }
      />

      {/* Grupo 8, tarea 8.1: bug vs. spec -- la ficha no mostraba el
          crédito en solo lectura (escenario "La ficha muestra el crédito
          en solo lectura", `design.md` D3). Visible para quien puede ver
          la ficha (`GESTIONAR_CLIENTES`), con o sin `GESTIONAR_CREDITO`:
          el enlace de edición de arriba es el único que exige el segundo
          permiso. */}
      <Card>
        <h2 className="text-sm font-medium text-primary">Crédito</h2>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-primary/70">Límite de crédito</dt>
          <dd>{valorVigente(detalle.limite_credito)}</dd>
          <dt className="text-primary/70">Política de crédito</dt>
          <dd>{detalle.politica_credito ?? HEREDA_DE_LA_ORGANIZACION}</dd>
          <dt className="text-primary/70">Tolerancia</dt>
          <dd>{textoTolerancia(detalle.tolerancia_offline_tipo, detalle.tolerancia_offline_valor)}</dd>
        </dl>
      </Card>

      <SaldoDeCuenta cuentaTipo="CLIENTE" entidadId={clienteId} />

      <Card>
        <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
          <Campo id="nombre" etiqueta="Nombre" error={errors.nombre?.message}>
            <input id="nombre" className="rounded-md border border-border px-2 py-1 text-sm" {...register('nombre')} />
          </Campo>
          <Campo id="direccion" etiqueta="Dirección" error={errors.direccion?.message}>
            <input
              id="direccion"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('direccion')}
            />
          </Campo>
          <Campo id="contacto" etiqueta="Contacto" error={errors.contacto?.message}>
            <input
              id="contacto"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('contacto')}
            />
          </Campo>
          <Campo id="razon_social" etiqueta="Razón social (opcional)">
            <input
              id="razon_social"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('razon_social', { setValueAs: setValueAsTextoOpcional })}
            />
          </Campo>
          <div className="flex gap-3">
            <Campo id="documento_tipo" etiqueta="Tipo de documento (opcional)">
              <select
                id="documento_tipo"
                className="rounded-md border border-border px-2 py-1 text-sm"
                {...register('documento_tipo', { setValueAs: setValueAsTextoOpcional })}
              >
                <option value="">Sin documento</option>
                {TIPOS_DOCUMENTO.map((tipo) => (
                  <option key={tipo} value={tipo}>
                    {tipo}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo id="documento_numero" etiqueta="Número de documento" error={errors.documento_numero?.message}>
              <input
                id="documento_numero"
                className="rounded-md border border-border px-2 py-1 text-sm"
                {...register('documento_numero', { setValueAs: setValueAsTextoOpcional })}
              />
            </Campo>
          </div>
          <Campo id="codigo" etiqueta="Código (opcional)" error={errors.codigo?.message}>
            <input
              id="codigo"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('codigo', { setValueAs: setValueAsTextoOpcional })}
            />
          </Campo>
          <Campo id="telefono" etiqueta="Teléfono (opcional)">
            <input
              id="telefono"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('telefono', { setValueAs: setValueAsTextoOpcional })}
            />
          </Campo>
          <Campo id="email" etiqueta="Email (opcional)">
            <input
              id="email"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('email', { setValueAs: setValueAsTextoOpcional })}
            />
          </Campo>

          <Campo id="estado" etiqueta="Estado" error={errors.estado?.message}>
            <select id="estado" className="rounded-md border border-border px-2 py-1 text-sm" {...register('estado')}>
              {ESTADOS_CLIENTE.map((estado) => (
                <option key={estado} value={estado}>
                  {estado}
                </option>
              ))}
            </select>
          </Campo>

          {errors.root?.message && <Alert>{errors.root.message}</Alert>}

          <div className="flex gap-2">
            <Boton type="submit" disabled={modificar.isPending}>
              Guardar cambios
            </Boton>
            <Link to="/admin/clientes" className="text-sm text-primary/70 hover:text-primary">
              Volver
            </Link>
          </div>
        </form>
      </Card>

      <Dialogo
        abierto={datosPendientes !== null}
        titulo="Confirmar inactivación"
        onCerrar={() => setDatosPendientes(null)}
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm text-primary/80">
            Un cliente inactivo no puede volver a estar activo si ya tiene operaciones (CLI-06). Para confirmar,
            escribí el nombre completo del cliente:
          </p>
          <p className="text-sm text-primary/70">
            <strong>{detalle.nombre}</strong>
            {detalle.codigo && ` · Código ${detalle.codigo}`}
            {detalle.documento_numero && ` · Documento ${detalle.documento_tipo} ${detalle.documento_numero}`}
          </p>
          <input
            aria-label="Nombre del cliente para confirmar"
            className="rounded-md border border-border px-2 py-1 text-sm"
            value={textoConfirmacion}
            onChange={(evento) => setTextoConfirmacion(evento.target.value)}
          />
          <div className="flex gap-2">
            <Boton
              type="button"
              variante="peligro"
              disabled={textoConfirmacion !== detalle.nombre || modificar.isPending}
              onClick={() => void confirmarInactivacion()}
            >
              Inactivar cliente
            </Boton>
            <Boton type="button" variante="secundario" onClick={() => setDatosPendientes(null)}>
              Cancelar
            </Boton>
          </div>
        </div>
      </Dialogo>
    </main>
  )
}

export default ClienteFormScreen
