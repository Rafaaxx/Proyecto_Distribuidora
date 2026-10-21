import { useState } from 'react'
import { useFieldArray, useForm, useWatch } from 'react-hook-form'
import { Link, useSearchParams } from 'react-router-dom'

import { Ayuda } from '../../../components/ui/Ayuda'
import { Alert } from '../../../components/ui/Alert'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import { Campo } from '../../../components/ui/Field'
import { PageHeader } from '../../../components/ui/PageHeader'
import {
  calcularFaltanteDeMedios,
  construirSolicitudDeCobranza,
  decidirConfirmacionDeCobranza,
  etiquetaDeFaltante,
  puedeRegistrarCobranza,
  textoDeSaldoResultante,
  type FormularioDeCobranza,
  type LecturaDeSaldoDeCliente,
  type MedioDePagoDeFormulario,
} from '../../../domain/cobranzas/formularioCobranza'
import { textoDeSaldo } from '../../../domain/cuentas-corrientes/presentacion'
import type { CobranzaRegistrarResultado } from '../../../features/cobranzas/api'
import { campoDelError, ErrorDeCobranzas, PermisoRequeridoCobranzasError, type CampoDelFormulario } from '../../../features/cobranzas/errores'
import { useOpcionesDeClientes, useRegistrarCobranza, useSaldoDelCliente } from '../../../features/cobranzas/hooks'
import { useMediosPago } from '../../../features/compras/hooks'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { SiTienePermiso } from '../../../features/identidad/SiTienePermiso'
import { generarOperationId } from '../../../lib/api/operationId'
import { MediosDeCobranza } from './MediosDeCobranza'

/**
 * Alta de cobranza (change 17, tarea 14.2; spec `administracion-de-cobranzas`). Solo con
 * `REGISTRAR_COBRANZA`. Toda la cuenta (faltante de medios, saldo resultante, aviso de saldo a
 * favor, esquema, cuerpo del comando) vive en `domain/cobranzas/formularioCobranza.ts`; este
 * componente solo la pinta. El `Operation-Id` se conserva mientras el contenido no cambia
 * (INV-06) y el identificador de la cobranza, mientras no se registra otra: un reintento nunca
 * duplica. El cliente puede venir precargado en `?cliente=<id>` desde su cuenta corriente,
 * también si no figura en el selector (D14, D19).
 */

const SIN_PERMISO = 'No tenés permiso para registrar cobranzas.'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-1 text-sm'
const MEDIO_VACIO: MedioDePagoDeFormulario = { medioPagoId: '', importe: '', referencia: '' }
const VALORES_INICIALES: FormularioDeCobranza = { clienteId: '', importe: '', observacion: '', medios: [MEDIO_VACIO] }

type ErroresDeCampo = Partial<Record<CampoDelFormulario, string>>

export function CobranzaFormScreen() {
  return (
    <SiTienePermiso
      permiso="REGISTRAR_COBRANZA"
      fallback={
        <main className="flex flex-col gap-4">
          <PageHeader titulo="Registrar cobranza" />
          <p className="text-sm text-primary/70">{SIN_PERMISO}</p>
        </main>
      }
    >
      <CobranzaFormulario />
    </SiTienePermiso>
  )
}

function CobranzaFormulario() {
  const [parametros] = useSearchParams()
  const precargado = parametros.get('cliente') ?? ''
  const { register, control, setValue, reset } = useForm<FormularioDeCobranza>({
    defaultValues: { ...VALORES_INICIALES, clienteId: precargado },
  })
  const mediosField = useFieldArray({ control, name: 'medios' })
  const formulario = useWatch({ control }) as FormularioDeCobranza

  const [cobranzaId, setCobranzaId] = useState(generarOperationId)
  const [busqueda, setBusqueda] = useState('')
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const [erroresDeCampo, setErroresDeCampo] = useState<ErroresDeCampo>({})
  const [erroresDeMedio, setErroresDeMedio] = useState<Record<number, string>>({})
  const [confirmando, setConfirmando] = useState(false)
  const [registrada, setRegistrada] = useState<CobranzaRegistrarResultado | null>(null)

  const clientes = useOpcionesDeClientes(busqueda)
  const saldo = useSaldoDelCliente(formulario.clienteId === '' ? undefined : formulario.clienteId)
  const mediosPago = useMediosPago()
  const registrar = useRegistrarCobranza()

  const opciones = clientes.data?.pages.flatMap((pagina) => pagina.items) ?? []
  // Un cliente que no figura en el selector (inactivo, o fuera de la búsqueda) se ofrece igual si vino precargado.
  const faltaPrecargado = precargado !== '' && !opciones.some((c) => c.id === precargado)
  const contexto = {
    mediosQueRequierenReferencia: new Set((mediosPago.data?.items ?? []).filter((m) => m.requiere_referencia).map((m) => m.id)),
  }
  const habilitado = puedeRegistrarCobranza(formulario, contexto)
  const faltante = calcularFaltanteDeMedios(formulario.importe, formulario.medios)
  const lecturaDeSaldo: LecturaDeSaldoDeCliente = saldo.isError
    ? { estado: 'error' }
    : saldo.isSuccess
      ? { estado: 'leido', saldo: saldo.data }
      : { estado: 'cargando' }
  const confirmacion = decidirConfirmacionDeCobranza(lecturaDeSaldo, formulario.importe)
  const esperandoSaldo = formulario.clienteId !== '' && confirmacion.tipo === 'esperar'
  const operationId = useOperationIdPorContenido({ formulario })

  const enviar = async () => {
    setConfirmando(false)
    setErrorGeneral(null)
    setErroresDeCampo({})
    setErroresDeMedio({})
    try {
      setRegistrada(await registrar.mutateAsync({ ...construirSolicitudDeCobranza(formulario, cobranzaId), operationId }))
    } catch (error) {
      if (error instanceof PermisoRequeridoCobranzasError) {
        setErrorGeneral(SIN_PERMISO)
      } else if (error instanceof ErrorDeCobranzas && error.medio !== null) {
        setErroresDeMedio({ [error.medio]: error.message })
      } else if (error instanceof ErrorDeCobranzas && campoDelError(error) !== null) {
        setErroresDeCampo({ [campoDelError(error) as CampoDelFormulario]: error.message })
      } else if (error instanceof ErrorDeCobranzas) {
        setErrorGeneral(error.message)
      } else {
        setErrorGeneral('No se pudo enviar la cobranza. Revisá la conexión y reintentá: se reenvía la misma operación.')
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

  if (registrada) {
    return (
      <main className="flex flex-col gap-4">
        <PageHeader titulo="Cobranza registrada" />
        <Card className="flex flex-col gap-2 text-sm text-primary">
          <p>La cobranza quedó asentada en la cuenta del cliente.</p>
          <p data-testid="saldo-final">{textoDeSaldo('CLIENTE', registrada.saldo)}</p>
          <p>{registrada.jornada_id ? 'La cobranza quedó en tu jornada.' : 'La cobranza quedó sin jornada.'}</p>
          <div className="flex flex-wrap gap-3">
            <Link to={`/admin/cobranzas/${registrada.cobranza_id}`} className="text-primary/70 hover:text-primary hover:underline">
              Ver la cobranza
            </Link>
            <Link to="/admin/cobranzas" className="text-primary/70 hover:text-primary hover:underline">
              Volver al listado
            </Link>
            <button
              type="button"
              className="text-primary/70 hover:text-primary hover:underline"
              onClick={() => {
                reset(VALORES_INICIALES)
                setCobranzaId(generarOperationId())
                setRegistrada(null)
              }}
            >
              Registrar otra cobranza
            </button>
          </div>
        </Card>
      </main>
    )
  }

  return (
    <main className="flex flex-col gap-4">
      <PageHeader titulo="Registrar cobranza" />
      <form onSubmit={alEnviar} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-primary/70">
          Registrar una cobranza requiere conexión: no se guarda para enviarla después.
        </p>
        {errorGeneral && <Alert>{errorGeneral}</Alert>}

        <Card className="flex flex-wrap items-end gap-3">
          <div data-testid="campo-busqueda">
            <Campo id="cobranza-busqueda" etiqueta="Buscar cliente">
              <input
                id="cobranza-busqueda"
                className={CLASE_CONTROL}
                placeholder="Nombre o código"
                value={busqueda}
                onChange={(evento) => setBusqueda(evento.target.value)}
              />
            </Campo>
          </div>
          <div data-testid="campo-cliente">
            <Campo id="cobranza-cliente" etiqueta="Cliente" error={erroresDeCampo.cliente}>
              <select
                id="cobranza-cliente"
                className={CLASE_CONTROL}
                value={formulario.clienteId}
                onChange={(evento) => setValue('clienteId', evento.target.value)}
              >
                <option value="">Elegí un cliente</option>
                {faltaPrecargado && <option value={precargado}>Cliente de la cuenta corriente</option>}
                {opciones.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nombre}
                  </option>
                ))}
              </select>
            </Campo>
          </div>
          <div data-testid="campo-importe">
            <Campo id="cobranza-importe" etiqueta="Importe" error={erroresDeCampo.importe}>
              <input id="cobranza-importe" className={`${CLASE_CONTROL} w-40`} inputMode="decimal" {...register('importe')} />
            </Campo>
          </div>
          <div data-testid="campo-observacion">
            <Campo id="cobranza-observacion" etiqueta="Observación (opcional)" error={erroresDeCampo.observacion}>
              <input id="cobranza-observacion" className={CLASE_CONTROL} maxLength={500} {...register('observacion')} />
            </Campo>
          </div>
        </Card>

        <Card className="flex items-center gap-1 text-sm text-primary">
          <p>
            Jornada: la cobranza entra sola en tu jornada abierta, si tenés una; si no, queda sin jornada.
          </p>
          <Ayuda clave="cobranzas.jornada" />
        </Card>

        {formulario.clienteId !== '' && (
          <Card className="flex flex-col gap-1 text-sm text-primary">
            {saldo.isPending && <p className="text-primary/70">Cargando saldo…</p>}
            {saldo.isError && <Alert>{confirmacion.tipo === 'saldo-ilegible' ? confirmacion.mensaje : ''}</Alert>}
            {saldo.isSuccess && (
              <>
                <p data-testid="saldo-actual">{textoDeSaldo('CLIENTE', saldo.data)}</p>
                <div className="flex items-center gap-1">
                  <p data-testid="saldo-resultante">
                    Saldo después de la cobranza: {textoDeSaldoResultante(saldo.data, formulario.importe)}
                  </p>
                  <Ayuda clave="cobranzas.saldoAFavor" />
                </div>
              </>
            )}
          </Card>
        )}

        <MediosDeCobranza
          idsDeFilas={mediosField.fields.map((campo) => campo.id)}
          medios={formulario.medios}
          mediosDePago={mediosPago.data?.items ?? []}
          registrar={(indice, campo) => register(`medios.${indice}.${campo}` as const)}
          alAgregar={() => mediosField.append(MEDIO_VACIO)}
          alQuitar={(indice) => mediosField.remove(indice)}
          erroresDeMedio={erroresDeMedio}
          pie={
            <p className="text-sm text-primary" data-testid="diferencia-medios">
              {etiquetaDeFaltante(faltante)}
            </p>
          }
        />

        <div className="flex gap-2">
          <Boton type="submit" disabled={!habilitado || registrar.isPending || esperandoSaldo}>
            Confirmar cobranza
          </Boton>
          <Link to="/admin/cobranzas" className="self-center text-sm text-primary/70 hover:text-primary">
            Cancelar
          </Link>
        </div>
      </form>

      <Dialogo abierto={confirmando} titulo="Confirmar cobranza" onCerrar={() => setConfirmando(false)}>
        <div className="flex flex-col gap-3">
          <p className="text-sm text-primary">
            {confirmacion.tipo === 'saldo-a-favor' || confirmacion.tipo === 'saldo-ilegible' ? confirmacion.mensaje : null}
          </p>
          <p className="text-sm text-primary/70">
            {confirmacion.tipo === 'saldo-ilegible'
              ? 'Si la cobranza supera la deuda, el excedente queda como saldo a favor del cliente y se descuenta solo de su próxima compra. ¿Querés registrarla igual?'
              : 'Ese saldo se descuenta solo de la próxima compra del cliente. Si no es lo que querés, revisá el importe.'}
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

export default CobranzaFormScreen
