import { zodResolver } from '@hookform/resolvers/zod'
import { useRef } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import { etiquetasDeSentido, type CuentaTipo, type Sentido } from '../../../domain/cuentas-corrientes/presentacion'
import {
  esquemaSaldoInicial,
  resolverOperationId,
  type DatosSaldoInicial,
  type EnvioPendiente,
} from '../../../domain/cuentas-corrientes/saldoInicialSchema'
import { ErrorDeCuentasCorrientes } from '../../../features/cuentas-corrientes/errores'
import { esErrorDeRed, useRegistrarSaldoInicial } from '../../../features/cuentas-corrientes/hooks'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { generarOperationId } from '../../../lib/api/operationId'

const SIN_PERMISO = 'No tenés permiso para registrar saldos iniciales.'
const AVISO_SIN_CONEXION = 'Se necesita conexión para completar esta operación. Probá de nuevo cuando tengas conexión.'
const AVISO_REQUIERE_CONEXION =
  'Este dato requiere conexión con el servidor y no se guarda para enviar después: si se corta la conexión, volvé a intentarlo.'
const MENSAJE_GENERICO = 'No se pudo completar la operación.'

const COLECCION: Record<CuentaTipo, string> = { CLIENTE: 'clientes', PROVEEDOR: 'proveedores' }
const SENTIDOS: Sentido[] = ['AUMENTA', 'REDUCE']

/** Sin permiso: el formulario no se monta (mismo criterio que el resto de las
 * pantallas de `/admin`, ADR-027). */
function SaldoInicialSinPermiso() {
  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Registrar saldo inicial" />
      <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
    </main>
  )
}

/**
 * Formulario de saldo inicial (change 08, tarea 7.4; `design.md` D1, D3, D5,
 * D13; spec `administracion-de-cuentas-corrientes`). Rutas
 * `/admin/clientes/:entidadId/cuenta-corriente/saldo-inicial` y su par de
 * proveedores. El permiso es `IMPORTAR_DATOS` (D1), de `['yo']` vía
 * `<SiTienePermiso>`: sin él, el formulario no se monta y no se envía nada.
 */
export function SaldoInicialScreen({ cuentaTipo }: { cuentaTipo: CuentaTipo }) {
  const { entidadId } = useParams<{ entidadId: string }>()
  return (
    <SiTienePermiso permiso="IMPORTAR_DATOS" fallback={<SaldoInicialSinPermiso />}>
      {entidadId ? <FormularioDeSaldoInicial cuentaTipo={cuentaTipo} entidadId={entidadId} /> : null}
    </SiTienePermiso>
  )
}

function mensajeDeError(error: unknown): string {
  if (esErrorDeRed(error)) {
    return AVISO_SIN_CONEXION
  }
  return error instanceof ErrorDeCuentasCorrientes ? error.message : MENSAJE_GENERICO
}

function FormularioDeSaldoInicial({ cuentaTipo, entidadId }: { cuentaTipo: CuentaTipo; entidadId: string }) {
  const navigate = useNavigate()
  const registrar = useRegistrarSaldoInicial()
  // Envío cortado por la red antes de recibir respuesta: su `operation_id` se
  // conserva para reenviarlo si el usuario reintenta lo mismo (INV-06, TR-07).
  // Un ref y no estado: no cambia lo que se dibuja.
  const pendienteRef = useRef<EnvioPendiente | null>(null)
  const rutaDeLaCuenta = `/admin/${COLECCION[cuentaTipo]}/${entidadId}/cuenta-corriente`
  const etiquetas = etiquetasDeSentido(cuentaTipo)

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<DatosSaldoInicial>({
    resolver: zodResolver(esquemaSaldoInicial),
    defaultValues: { importe: '', sentido: 'AUMENTA' },
  })

  async function enviar(datos: DatosSaldoInicial) {
    const operationId = resolverOperationId(pendienteRef.current, datos, generarOperationId)
    try {
      await registrar.mutateAsync({
        cuenta_tipo: cuentaTipo,
        entidad_id: entidadId,
        importe: datos.importe,
        sentido: datos.sentido,
        operationId,
      })
      pendienteRef.current = null
      navigate(rutaDeLaCuenta)
    } catch (error) {
      // Corte de red: puede que el servidor sí lo haya procesado, así que se
      // reenvía con el mismo `operation_id`. Un rechazo con respuesta HTTP ya
      // está resuelto: reenviar es una operación nueva.
      pendienteRef.current = esErrorDeRed(error) ? { datos, operationId } : null
      setError('root', { message: mensajeDeError(error) })
    }
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Registrar saldo inicial" />
      <Card>
        <form onSubmit={(evento) => void handleSubmit(enviar)(evento)} noValidate className="flex flex-col gap-4">
          <p className="text-sm text-primary/70">{AVISO_REQUIERE_CONEXION}</p>

          <Campo id="importe" etiqueta="Importe" error={errors.importe?.message}>
            <input
              id="importe"
              inputMode="decimal"
              autoComplete="off"
              className="rounded-md border border-border px-2 py-1 text-sm"
              {...register('importe')}
            />
          </Campo>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium text-primary">Saldo</legend>
            {SENTIDOS.map((sentido) => (
              <label key={sentido} className="flex items-center gap-2 text-sm text-primary">
                <input type="radio" value={sentido} {...register('sentido')} />
                {etiquetas[sentido]}
              </label>
            ))}
            {errors.sentido?.message && (
              <p role="alert" className="text-sm text-danger">
                {errors.sentido.message}
              </p>
            )}
          </fieldset>

          {errors.root?.message && <Alert>{errors.root.message}</Alert>}

          <div className="flex items-center gap-3">
            <Boton type="submit" disabled={registrar.isPending}>
              Registrar saldo inicial
            </Boton>
            <Link to={rutaDeLaCuenta} className="text-sm text-primary/70 hover:text-primary">
              Cancelar
            </Link>
          </div>
        </form>
      </Card>
    </main>
  )
}

export default SaldoInicialScreen
