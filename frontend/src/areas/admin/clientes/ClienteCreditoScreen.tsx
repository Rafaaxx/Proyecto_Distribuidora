import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  POLITICAS_CREDITO,
  TIPOS_TOLERANCIA_OFFLINE,
  esquemaClienteCredito,
  type DatosClienteCredito,
} from '../../../domain/clientes/clienteSchema'
import type { Cliente } from '../../../features/clientes/api'
import { ErrorDeClientes } from '../../../features/clientes/errores'
import { campoDeCreditoParaCodigo, type CampoCredito } from '../../../features/clientes/mapaErrorACampo'
import { useCliente } from '../../../features/clientes/useListados'
import { esErrorDeRed, useModificarCreditoCliente } from '../../../features/clientes/useMutaciones'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { formatearImporte, parsearImporteDesdeApi } from '../../../lib/money'

const SIN_PERMISO_DE_CREDITO = 'No tenés permiso para gestionar el crédito de clientes.'
const AVISO_SIN_CONEXION = 'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.'

function CreditoSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Crédito" />
      <p className="text-sm text-primary/70">{SIN_PERMISO_DE_CREDITO}</p>
    </main>
  )
}

function mensajeDeError(error: unknown): { campo: CampoCredito | null; mensaje: string } {
  if (esErrorDeRed(error)) {
    return { campo: null, mensaje: AVISO_SIN_CONEXION }
  }
  if (error instanceof ErrorDeClientes) {
    return { campo: campoDeCreditoParaCodigo(error.codigo), mensaje: error.message }
  }
  return { campo: null, mensaje: 'No se pudo completar la operación.' }
}

const setValueAsTextoOpcional = (valor: string) => (valor === '' ? null : valor)

/** Formatea un importe de la API (`"150000.00"` o `null`) para mostrar el
 * valor vigente antes de editarlo (`lib/money.ts`, INV-03: nunca pasa por
 * `number`). `null` significa HEREDA de la organización (CRE-03, D8), no
 * cero -- se muestra distinto de un importe real. */
function valorVigente(valorApi: string | null): string {
  return valorApi === null ? 'Hereda de la organización' : formatearImporte(parsearImporteDesdeApi(valorApi))
}

/**
 * Edición del crédito de un cliente (change 07, grupo 5, tarea 5.4;
 * `design.md` D3, D8, D9 enmienda 2026-09-29). Pantalla separada de la
 * ficha: dos comandos, dos permisos (D3) -- `GESTIONAR_CREDITO`, no
 * `GESTIONAR_CLIENTES`.
 *
 * Decidida **solo** con `GESTIONAR_CREDITO` de la consulta de sesión
 * `['yo']` (ADR-027/028): sin el permiso, el formulario no se monta.
 */
export function ClienteCreditoScreen() {
  const { clienteId } = useParams<{ clienteId: string }>()
  if (!clienteId) return null
  return (
    <SiTienePermiso permiso="GESTIONAR_CREDITO" fallback={<CreditoSinPermiso />}>
      <ClienteCreditoContenido clienteId={clienteId} />
    </SiTienePermiso>
  )
}

function ClienteCreditoContenido({ clienteId }: { clienteId: string }) {
  const cliente = useCliente(clienteId)
  const modificar = useModificarCreditoCliente()

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

  return <ClienteCreditoFormulario clienteId={clienteId} detalle={cliente.data} modificar={modificar} />
}

function ClienteCreditoFormulario({
  clienteId,
  detalle,
  modificar,
}: {
  clienteId: string
  detalle: Cliente
  modificar: ReturnType<typeof useModificarCreditoCliente>
}) {
  const navigate = useNavigate()

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<DatosClienteCredito>({
    resolver: zodResolver(esquemaClienteCredito),
    values: {
      limite_credito: detalle.limite_credito,
      politica_credito: detalle.politica_credito as (typeof POLITICAS_CREDITO)[number] | null,
      tolerancia_offline_tipo: detalle.tolerancia_offline_tipo as (typeof TIPOS_TOLERANCIA_OFFLINE)[number] | null,
      tolerancia_offline_valor: detalle.tolerancia_offline_valor,
    },
  })

  const alEnviar = handleSubmit(async (datos) => {
    try {
      await modificar.mutateAsync({ clienteId, ...datos })
      // Grupo 8, tarea 8.2 (decisión del usuario 2026-09-29): vuelve a la
      // ficha del cliente, no se queda en la pantalla de crédito.
      navigate(`/admin/clientes/${clienteId}`)
    } catch (error) {
      const { campo, mensaje } = mensajeDeError(error)
      setError(campo ?? 'root', { message: mensaje })
    }
  })

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo={`Crédito de ${detalle.nombre}`} />
      <Card>
        <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
          <p className="text-sm text-primary/70">
            Límite vigente: <strong>{valorVigente(detalle.limite_credito)}</strong>
          </p>

          <Campo id="limite_credito" etiqueta="Límite de crédito (vacío = hereda)" error={errors.limite_credito?.message}>
            <input
              id="limite_credito"
              inputMode="decimal"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('limite_credito', { setValueAs: setValueAsTextoOpcional })}
            />
          </Campo>

          <Campo id="politica_credito" etiqueta="Política de crédito (vacío = hereda)">
            <select
              id="politica_credito"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('politica_credito', { setValueAs: setValueAsTextoOpcional })}
            >
              <option value="">Hereda de la organización</option>
              {POLITICAS_CREDITO.map((politica) => (
                <option key={politica} value={politica}>
                  {politica}
                </option>
              ))}
            </select>
          </Campo>

          <div className="flex gap-3">
            <Campo id="tolerancia_offline_tipo" etiqueta="Tipo de tolerancia (vacío = hereda)">
              <select
                id="tolerancia_offline_tipo"
                className="rounded-md border border-border px-2 py-1 text-sm"
                {...register('tolerancia_offline_tipo', { setValueAs: setValueAsTextoOpcional })}
              >
                <option value="">Hereda de la organización</option>
                {TIPOS_TOLERANCIA_OFFLINE.map((tipo) => (
                  <option key={tipo} value={tipo}>
                    {tipo}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo
              id="tolerancia_offline_valor"
              etiqueta="Valor de tolerancia"
              error={errors.tolerancia_offline_valor?.message}
            >
              <input
                id="tolerancia_offline_valor"
                inputMode="decimal"
                className="rounded-md border border-border px-2 py-1 text-sm"
                {...register('tolerancia_offline_valor', { setValueAs: setValueAsTextoOpcional })}
              />
            </Campo>
          </div>

          {errors.root?.message && <Alert>{errors.root.message}</Alert>}

          <div className="flex gap-2">
            <Boton type="submit" disabled={modificar.isPending}>
              Guardar crédito
            </Boton>
            <Link to={`/admin/clientes/${clienteId}`} className="text-sm text-primary/70 hover:text-primary">
              Volver a la ficha
            </Link>
          </div>
        </form>
      </Card>
    </main>
  )
}

export default ClienteCreditoScreen
