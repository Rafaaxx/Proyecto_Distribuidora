import { useEffect, useMemo, useRef, useState } from 'react'
import { useBlocker, useNavigate, useSearchParams } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { Dialogo } from '../../../components/ui/Dialog'
import type { DatosParaVender } from '../../../domain/ruta/armadoDeVentaLocal'
import { AVISO_LO_YA_VENDIDO, textoDeJornadaNoAbierta } from '../../../domain/ruta/avisoDeJornada'
import { clientesParaElegir } from '../../../domain/ruta/carritoDeRuta'
import { evaluarCobranzaLocal } from '../../../domain/ruta/cobranzaLocal'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'
import {
  textoDeConfirmacionDeCobranza,
  textoDeSaldoAFavor,
  textosDeErroresDeCobranza,
} from '../../../domain/ruta/textosDeCobranza'
import type { MedioDePagoDeFormulario } from '../../../domain/pagos-proveedores/formularioPago'
import { generarOperationId } from '../../../lib/api/operationId'
import { obtenerOGenerarDispositivoId } from '../../../lib/dispositivo/dispositivoId'
import { APP_VERSION } from '../../../sync/appVersion'
import { dispararTrasVenta } from '../../../sync/disparadores'
import { leerJornadaNoAbierta } from '../../../sync/estadoDeJornada'
import { registrarCobranzaLocal } from '../../../sync/registrarCobranzaLocal'
import { AVISO_DE_VERSION_MINIMA, ventaBloqueadaPorVersion } from '../../../sync/versionMinima'
import { useDatosParaVender } from '../datos/paraVender'
import { useGuardaDelCarrito } from '../ventas/contextoGuarda'
import { MediosDeCobro } from '../ventas/MediosDeCobro'
import { PasoCliente } from '../ventas/PasoCliente'

const CLASE_CONTROL = 'w-full rounded-md border border-border px-2 py-2 text-sm'
const MENSAJE_DE_FALLA = 'No se pudo guardar la cobranza. Probá de nuevo.'
const MEDIO_NUEVO: MedioDePagoDeFormulario = { medioPagoId: '', importe: '', referencia: '' }

/**
 * Cobrar en `/ruta` (change 23, `design.md` D1, D3, D4, D7, D8; COB-01, COB-02, INV-08, CLI-03,
 * CC-04, INV-01, INV-06): cliente (sin el consumidor final), saldo local actual, importe, medios
 * con referencia, observación y saldo resultante. «Confirmar cobranza» valida con
 * `evaluarCobranzaLocal`, pide la confirmación (con el aviso de saldo a favor) y guarda en UNA
 * transacción local (`registrarCobranzaLocal`), con o sin señal; después dispara el envío. Sin
 * lógica de negocio: las reglas viven en `domain/ruta/` y `sync/`.
 */
export function CobrarScreen() {
  const lectura = useDatosParaVender()

  if (lectura.estado === 'cargando') return <p className="text-sm text-primary">Cargando…</p>
  if (lectura.estado === 'sin_datos') {
    return <p className="text-sm text-primary">Cobrar necesita los datos del día: abrí la jornada para descargarlos.</p>
  }
  if (!lectura.datos.sesion.permisos.includes('REGISTRAR_COBRANZA')) {
    return <p className="text-sm text-primary">No tenés permiso para cobrar.</p>
  }
  return <CobranzaDeRuta datos={lectura.datos} />
}

function CobranzaDeRuta({ datos }: { datos: DatosParaVender }) {
  const navegar = useNavigate()
  const [parametros] = useSearchParams()
  const guarda = useGuardaDelCarrito()

  const todos = useMemo(() => clientesParaElegir(datos, ''), [datos])
  const pedido = todos.find((c) => c.cliente.id === parametros.get('cliente'))
  const [clienteId, setClienteId] = useState(pedido !== undefined && !pedido.cliente.es_consumidor_final ? pedido.cliente.id : '')
  const [busqueda, setBusqueda] = useState('')
  const [importe, setImporte] = useState('')
  const [medios, setMedios] = useState<MedioDePagoDeFormulario[]>([MEDIO_NUEVO])
  const [observacion, setObservacion] = useState('')
  const [errores, setErrores] = useState<string[]>([])
  const [falla, setFalla] = useState<string | null>(null)
  const [confirmando, setConfirmando] = useState(false)
  const [guardando, setGuardando] = useState(false)
  // Los identificadores se generan al abrir el formulario y se reutilizan al reintentar (INV-06).
  const cobranzaId = useRef(generarOperationId())
  const operationId = useRef(generarOperationId())
  const enCurso = useRef(false)
  const salidaLibre = useRef(false)

  const elegido = todos.find((c) => c.cliente.id === clienteId)
  const clientes = useMemo(
    () => clientesParaElegir(datos, busqueda).filter((c) => !c.cliente.es_consumidor_final),
    [datos, busqueda],
  )
  const evaluacion = evaluarCobranzaLocal({
    cliente: elegido === undefined ? null : { id: elegido.cliente.id, nombre: elegido.cliente.nombre, es_consumidor_final: false },
    saldoActual: elegido?.saldoConsiderado ?? null,
    importe,
    observacion,
    medios,
    mediosPago: datos.mediosPago,
  })

  // Con algo cargado, la guarda impide aplicar una versión nueva y toda salida pregunta (02 §13.5).
  const hayDatos =
    importe.trim() !== '' ||
    observacion.trim() !== '' ||
    medios.some((m) => m.medioPagoId !== '' || m.importe.trim() !== '' || m.referencia.trim() !== '')
  const abierto = hayDatos || guardando
  const { marcar } = guarda
  useEffect(() => {
    marcar(abierto)
  }, [abierto, marcar])
  useEffect(() => () => marcar(false), [marcar])

  const bloqueador = useBlocker(() => !salidaLibre.current && hayDatos)
  useEffect(() => {
    if (!hayDatos) return undefined
    const avisar = (evento: BeforeUnloadEvent) => {
      evento.preventDefault()
      evento.returnValue = ''
    }
    window.addEventListener('beforeunload', avisar)
    return () => window.removeEventListener('beforeunload', avisar)
  }, [hayDatos])

  /** D7: por debajo de la versión mínima y con la jornada no abierta no se confirma; el formulario sigue. */
  const motivoDeCorte = async (): Promise<string | null> => {
    if (await ventaBloqueadaPorVersion(APP_VERSION)) return AVISO_DE_VERSION_MINIMA
    const noAbierta = await leerJornadaNoAbierta()
    return noAbierta === null ? null : `${textoDeJornadaNoAbierta(noAbierta.estado)} ${AVISO_LO_YA_VENDIDO}`
  }

  const alConfirmar = async () => {
    setFalla(null)
    if (!evaluacion.valida) {
      setErrores(textosDeErroresDeCobranza(evaluacion))
      return
    }
    setErrores([])
    const corte = await motivoDeCorte()
    if (corte !== null) {
      setFalla(corte)
      return
    }
    setConfirmando(true)
  }

  const registrar = async () => {
    if (enCurso.current) return
    enCurso.current = true
    setGuardando(true)
    setFalla(null)
    try {
      const corte = await motivoDeCorte()
      if (corte !== null || evaluacion.importe === null || elegido === undefined) {
        setFalla(corte ?? MENSAJE_DE_FALLA)
        setConfirmando(false)
        enCurso.current = false
        setGuardando(false)
        return
      }
      const resultado = await registrarCobranzaLocal({
        cobranzaId: cobranzaId.current,
        operationId: operationId.current,
        clienteId: elegido.cliente.id,
        importe: evaluacion.importe,
        medios: evaluacion.medios,
        observacion: evaluacion.observacion,
        usuarioId: datos.sesion.usuario.id,
        dispositivoId: await obtenerOGenerarDispositivoId(),
        ahora: new Date(),
        appVersion: APP_VERSION,
      })
      salidaLibre.current = true
      marcar(false)
      // D1: con o sin señal va por la cola; con señal se envía enseguida, como la venta.
      dispararTrasVenta()
      navegar(`/ruta/cobranzas/${resultado.cobranza.cobranza_id}`, { replace: true })
    } catch {
      // No quedó nada guardado: el formulario sigue y se reintenta con la misma operación (INV-06).
      setConfirmando(false)
      setFalla(MENSAJE_DE_FALLA)
      enCurso.current = false
      setGuardando(false)
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <h1 className="text-lg font-semibold text-primary">Cobrar</h1>
          <Ayuda clave="ruta.cobrar" />
        </div>
        <button type="button" className="text-sm text-primary/70 underline" onClick={() => navegar('/ruta')}>
          Cancelar
        </button>
      </div>

      {elegido === undefined ? (
        <PasoCliente clientes={clientes} busqueda={busqueda} alBuscar={setBusqueda} alElegir={(id) => setClienteId(id)} />
      ) : (
        <>
          <Card className="flex flex-col gap-1 text-sm text-primary">
            <p className="break-words text-base font-semibold">{elegido.cliente.nombre}</p>
            <p data-testid="saldo-actual">Saldo actual: {formatearDinero(elegido.saldoConsiderado ?? '0.00')}</p>
            <button type="button" className="self-start text-xs text-primary/70 underline" onClick={() => setClienteId('')}>
              Cambiar cliente
            </button>
          </Card>

          <Card className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="cobrar-importe" className="text-sm font-medium text-primary">
                Importe a cobrar
              </label>
              <input
                id="cobrar-importe"
                inputMode="decimal"
                className={CLASE_CONTROL}
                value={importe}
                onChange={(e) => setImporte(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-1">
              <h2 className="text-sm font-semibold text-primary">Medios de pago</h2>
              <Ayuda clave="ruta.medios" />
            </div>
            <MediosDeCobro
              medios={medios}
              mediosPago={datos.mediosPago}
              alAgregar={() => setMedios((actuales) => [...actuales, MEDIO_NUEVO])}
              alCambiar={(indice, cambio) => setMedios((actuales) => actuales.map((m, i) => (i === indice ? { ...m, ...cambio } : m)))}
              alQuitar={(indice) => setMedios((actuales) => actuales.filter((_, i) => i !== indice))}
            />
            <div className="flex flex-col gap-1">
              <label htmlFor="cobrar-observacion" className="text-xs text-primary/70">
                Observación (opcional)
              </label>
              <input
                id="cobrar-observacion"
                className={CLASE_CONTROL}
                value={observacion}
                onChange={(e) => setObservacion(e.target.value)}
              />
            </div>
          </Card>

          <Card className="flex items-center gap-1 text-sm text-primary">
            <p data-testid="saldo-despues">Saldo después del cobro: {formatearDinero(evaluacion.saldoResultante ?? '0.00')}</p>
            <Ayuda clave="ruta.saldoDespuesDelCobro" />
          </Card>

          {errores.length > 0 && (
            <Alert>
              {errores.map((texto) => (
                <span key={texto} className="block">
                  {texto}
                </span>
              ))}
            </Alert>
          )}
          {falla !== null && (
            <Alert>
              {falla}
              {falla === AVISO_DE_VERSION_MINIMA && (
                <>
                  {' '}
                  <Ayuda clave="ruta.versionMinima" />
                </>
              )}
            </Alert>
          )}
          <Boton disabled={guardando} onClick={() => void alConfirmar()}>
            Confirmar cobranza
          </Boton>
        </>
      )}

      <Dialogo
        abierto={confirmando && evaluacion.importe !== null && elegido !== undefined}
        titulo={textoDeConfirmacionDeCobranza(evaluacion.importe ?? '0.00', elegido?.cliente.nombre ?? '')}
        onCerrar={() => setConfirmando(false)}
      >
        <div className="flex flex-col gap-3">
          {evaluacion.importeAFavor !== null && <p className="text-sm text-primary">{textoDeSaldoAFavor(evaluacion.importeAFavor)}</p>}
          <div className="flex justify-end gap-2">
            <Boton variante="secundario" disabled={guardando} onClick={() => setConfirmando(false)}>
              Volver
            </Boton>
            <Boton disabled={guardando} onClick={() => void registrar()}>
              Registrar
            </Boton>
          </div>
        </div>
      </Dialogo>

      <Dialogo abierto={bloqueador.state === 'blocked'} titulo="¿Descartar la cobranza?" onCerrar={() => bloqueador.reset?.()}>
        <p className="mb-3 text-sm text-primary">Si salís ahora se pierde lo que cargaste. Todavía no se registró nada.</p>
        <div className="flex justify-end gap-2">
          <Boton variante="secundario" onClick={() => bloqueador.reset?.()}>
            Seguir cobrando
          </Boton>
          <Boton
            variante="peligro"
            onClick={() => {
              salidaLibre.current = true
              marcar(false)
              bloqueador.proceed?.()
            }}
          >
            Descartar
          </Boton>
        </div>
      </Dialogo>
    </div>
  )
}

export default CobrarScreen
