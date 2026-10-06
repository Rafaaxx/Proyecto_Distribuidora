import { useState } from 'react'
import { useFieldArray, useForm, useWatch } from 'react-hook-form'
import { Link, useSearchParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Campo } from '../../../components/ui/Field'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { PageHeader } from '../../../components/ui/PageHeader'
import { textoDeSaldo } from '../../../domain/cuentas-corrientes/presentacion'
import { AVISO_SALDO_ILEGIBLE, decidirConfirmacionDePago, type LecturaDeSaldo } from '../../../domain/pagos-proveedores/confirmacionDePago'
import {
  calcularFaltanteDeMedios,
  construirSolicitudDePago,
  etiquetaDeDiferencia,
  puedeRegistrarPago,
  textoDeSaldoResultante,
  type FormularioDePago,
  type MedioDePagoDeFormulario,
} from '../../../domain/pagos-proveedores/formularioPago'
import type { MedioPago } from '../../../features/compras/api'
import { useMediosPago } from '../../../features/compras/hooks'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import type { PagoRegistrarResultado } from '../../../features/pagos-proveedores/api'
import { ErrorDePagos, PermisoRequeridoPagosError } from '../../../features/pagos-proveedores/errores'
import { useRegistrarPago, useSaldoDelProveedor } from '../../../features/pagos-proveedores/hooks'
import { useOpcionesDeProveedores, useProveedor } from '../../../features/proveedores/useListados'

/**
 * Alta de pago a proveedor (change 12, tarea 9.1; spec `administracion-de-pagos`). Solo con
 * `REGISTRAR_PAGO_PROVEEDOR` (D7). Toda la cuenta (faltante de medios, saldo resultante, aviso
 * de saldo a favor, esquema, cuerpo del comando) vive en
 * `domain/pagos-proveedores/formularioPago.ts`; este componente solo la pinta. El
 * `Operation-Id` se conserva mientras el contenido no cambia (INV-06). El proveedor puede
 * venir precargado en `?proveedor=<id>` desde su cuenta corriente, también si está inactivo
 * (D5, D11).
 */

const SIN_PERMISO = 'No tenés permiso para registrar pagos a proveedores.'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const MEDIO_VACIO: MedioDePagoDeFormulario = { medioPagoId: '', importe: '', referencia: '' }

function fechaDeHoy(): string {
  const ahora = new Date()
  const mes = String(ahora.getMonth() + 1).padStart(2, '0')
  const dia = String(ahora.getDate()).padStart(2, '0')
  return `${String(ahora.getFullYear())}-${mes}-${dia}`
}

function valoresIniciales(proveedorId: string): FormularioDePago {
  return { proveedorId, fecha: fechaDeHoy(), importe: '', observacion: '', medios: [MEDIO_VACIO] }
}

export function PagoFormScreen() {
  return (
    <SiTienePermiso
      permiso="REGISTRAR_PAGO_PROVEEDOR"
      fallback={
        <main className="flex flex-col gap-4">
          <PageHeader titulo="Nuevo pago a proveedor" />
          <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
        </main>
      }
    >
      <PagoFormulario />
    </SiTienePermiso>
  )
}

function PagoFormulario() {
  const [parametros] = useSearchParams()
  const precargado = parametros.get('proveedor') ?? ''
  const { register, control, setValue, reset } = useForm<FormularioDePago>({ defaultValues: valoresIniciales(precargado) })
  const mediosField = useFieldArray({ control, name: 'medios' })
  const formulario = useWatch({ control }) as FormularioDePago

  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const [erroresDeMedio, setErroresDeMedio] = useState<Record<number, string>>({})
  const [confirmando, setConfirmando] = useState(false)
  const [registrado, setRegistrado] = useState<PagoRegistrarResultado | null>(null)

  const proveedores = useOpcionesDeProveedores()
  const proveedorPrecargado = useProveedor(precargado === '' ? undefined : precargado)
  const saldo = useSaldoDelProveedor(formulario.proveedorId === '' ? undefined : formulario.proveedorId)
  const mediosPago = useMediosPago()
  const registrar = useRegistrarPago()

  const opciones = proveedores.data?.pages.flatMap((pagina) => pagina.items) ?? []
  // Un proveedor inactivo no figura en las opciones: se ofrece igual si vino precargado (D5).
  const faltaPrecargado = precargado !== '' && !opciones.some((p) => p.id === precargado)
  const medioDePago = (id: string): MedioPago | undefined => mediosPago.data?.items.find((m) => m.id === id)
  const contexto = {
    hoy: fechaDeHoy(),
    mediosQueRequierenReferencia: new Set((mediosPago.data?.items ?? []).filter((m) => m.requiere_referencia).map((m) => m.id)),
  }
  const habilitado = puedeRegistrarPago(formulario, contexto)
  const diferencia = calcularFaltanteDeMedios(formulario.importe, formulario.medios)
  const lecturaDeSaldo: LecturaDeSaldo = saldo.isError
    ? { estado: 'error' }
    : saldo.isSuccess
      ? { estado: 'leido', saldo: saldo.data }
      : { estado: 'cargando' }
  const confirmacion = decidirConfirmacionDePago(lecturaDeSaldo, formulario.importe)
  const esperandoSaldo = formulario.proveedorId !== '' && confirmacion.tipo === 'esperar'
  const operationId = useOperationIdPorContenido({ formulario })

  const enviar = async () => {
    setConfirmando(false)
    setErrorGeneral(null)
    setErroresDeMedio({})
    try {
      setRegistrado(await registrar.mutateAsync({ ...construirSolicitudDePago(formulario), operationId }))
    } catch (error) {
      if (error instanceof PermisoRequeridoPagosError) {
        setErrorGeneral(SIN_PERMISO)
      } else if (error instanceof ErrorDePagos && error.medio !== null) {
        setErroresDeMedio({ [error.medio]: error.message })
      } else if (error instanceof ErrorDePagos) {
        setErrorGeneral(error.message)
      } else {
        setErrorGeneral('No se pudo enviar el pago. Revisá la conexión y reintentá: se reenvía la misma operación.')
      }
    }
  }

  const alEnviar = (evento: React.SyntheticEvent) => {
    evento.preventDefault()
    if (!habilitado || registrar.isPending || esperandoSaldo) return
    if (confirmacion.tipo === 'saldo-a-favor' || confirmacion.tipo === 'saldo-ilegible') {
      setConfirmando(true)
      return
    }
    void enviar()
  }

  if (registrado) {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Pago registrado" />
        <Card className="flex flex-col gap-2 text-sm text-primary">
          <p>El pago quedó asentado en la cuenta del proveedor.</p>
          <p data-testid="saldo-final">{textoDeSaldo('PROVEEDOR', registrado.saldo)}</p>
          <div className="flex flex-wrap gap-3">
            <Link to={`/admin/pagos-proveedores/${registrado.pago_id}`} className="text-primary/70 hover:text-primary hover:underline">
              Ver el pago
            </Link>
            <Link to="/admin/pagos-proveedores" className="text-primary/70 hover:text-primary hover:underline">
              Volver al listado
            </Link>
            <button
              type="button"
              className="text-primary/70 hover:text-primary hover:underline"
              onClick={() => {
                reset(valoresIniciales(''))
                setRegistrado(null)
              }}
            >
              Registrar otro pago
            </button>
          </div>
        </Card>
      </main>
    )
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Nuevo pago a proveedor" />
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-primary/70">
          Registrar un pago requiere conexión: no se guarda para enviarlo después.
        </p>
        {errorGeneral && <Alert>{errorGeneral}</Alert>}

        <Card className="flex flex-wrap items-end gap-3">
          <Campo id="pago-proveedor" etiqueta="Proveedor">
            <select
              id="pago-proveedor"
              className={CLASE_CONTROL}
              value={formulario.proveedorId}
              onChange={(evento) => setValue('proveedorId', evento.target.value)}
            >
              <option value="">Elegí un proveedor</option>
              {faltaPrecargado && (
                <option value={precargado}>{proveedorPrecargado.data?.nombre ?? 'Proveedor de la cuenta corriente'}</option>
              )}
              {opciones.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre}
                </option>
              ))}
            </select>
          </Campo>
          <Campo id="pago-fecha" etiqueta="Fecha del pago">
            <input id="pago-fecha" type="date" className={CLASE_CONTROL} {...register('fecha')} />
          </Campo>
          <Campo id="pago-importe" etiqueta="Importe">
            <input id="pago-importe" className={`${CLASE_CONTROL} w-40`} inputMode="decimal" {...register('importe')} />
          </Campo>
          <Campo id="pago-observacion" etiqueta="Observación (opcional)">
            <input id="pago-observacion" className={CLASE_CONTROL} maxLength={500} {...register('observacion')} />
          </Campo>
        </Card>

        {formulario.proveedorId !== '' && (
          <Card className="flex flex-col gap-1 text-sm text-primary">
            {saldo.isPending && <p className="text-primary/70">Cargando saldo…</p>}
            {saldo.isError && <Alert>{AVISO_SALDO_ILEGIBLE}</Alert>}
            {saldo.isSuccess && (
              <>
                <p data-testid="saldo-actual">{textoDeSaldo('PROVEEDOR', saldo.data)}</p>
                <p data-testid="saldo-resultante">Saldo después del pago: {textoDeSaldoResultante(saldo.data, formulario.importe)}</p>
              </>
            )}
          </Card>
        )}

        <Card className="flex flex-col gap-3">
          <h2 className="text-base font-semibold text-primary">Medios de pago</h2>
          {mediosField.fields.map((campo, indice) => {
            const requiereReferencia = medioDePago(formulario.medios[indice]?.medioPagoId ?? '')?.requiere_referencia === true
            return (
              <div key={campo.id} data-testid={`medio-${indice}`} className="flex flex-col gap-2">
                <div className="flex flex-wrap items-end gap-3">
                  <Campo id={`medios.${indice}.medioPagoId`} etiqueta="Medio de pago">
                    <select id={`medios.${indice}.medioPagoId`} className={CLASE_CONTROL} {...register(`medios.${indice}.medioPagoId` as const)}>
                      <option value="">Elegí un medio</option>
                      {(mediosPago.data?.items ?? []).map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.nombre}
                        </option>
                      ))}
                    </select>
                  </Campo>
                  <Campo id={`medios.${indice}.importe`} etiqueta="Importe del medio">
                    <input id={`medios.${indice}.importe`} className={`${CLASE_CONTROL} w-32`} inputMode="decimal" {...register(`medios.${indice}.importe` as const)} />
                  </Campo>
                  {requiereReferencia && (
                    <Campo id={`medios.${indice}.referencia`} etiqueta="Referencia (obligatoria)">
                      <input id={`medios.${indice}.referencia`} required className={CLASE_CONTROL} {...register(`medios.${indice}.referencia` as const)} />
                    </Campo>
                  )}
                  {mediosField.fields.length > 1 && (
                    <Boton variante="peligro" onClick={() => mediosField.remove(indice)}>
                      Quitar medio
                    </Boton>
                  )}
                </div>
                {erroresDeMedio[indice] && <Alert>{erroresDeMedio[indice]}</Alert>}
              </div>
            )
          })}
          <Boton variante="secundario" className="self-start" onClick={() => mediosField.append(MEDIO_VACIO)}>
            Agregar medio
          </Boton>
          <p className="text-sm text-primary" data-testid="diferencia-medios">
            {etiquetaDeDiferencia(diferencia)}
          </p>
        </Card>

        <div className="flex gap-2">
          <Boton type="submit" disabled={!habilitado || registrar.isPending || esperandoSaldo}>
            Confirmar pago
          </Boton>
          <Link to="/admin/pagos-proveedores" className="self-center text-sm text-primary/70 hover:text-primary">
            Cancelar
          </Link>
        </div>
      </form>

      <Dialogo abierto={confirmando} titulo="Confirmar pago" onCerrar={() => setConfirmando(false)}>
        <div className="flex flex-col gap-3">
          <p className="text-sm text-primary">{confirmacion.tipo === 'ninguna' || confirmacion.tipo === 'esperar' ? null : confirmacion.mensaje}</p>
          <p className="text-sm text-primary/70">
            {confirmacion.tipo === 'saldo-ilegible'
              ? 'Si el pago supera la deuda, el excedente queda como saldo a nuestro favor y se descuenta solo de la próxima compra a crédito del proveedor. ¿Querés registrarlo igual?'
              : 'Ese saldo se descuenta solo de la próxima compra a crédito del proveedor. Si no es lo que querés, revisá el importe.'}
          </p>
          <div className="flex gap-2">
            <Boton onClick={() => void enviar()}>Aceptar y registrar</Boton>
            <Boton variante="secundario" onClick={() => setConfirmando(false)}>
              Cancelar
            </Boton>
          </div>
        </div>
      </Dialogo>
    </main>
  )
}

export default PagoFormScreen
