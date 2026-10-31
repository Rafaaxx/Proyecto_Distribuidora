import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { Boton } from '../../../components/ui/Button'
import { Dialogo } from '../../../components/ui/Dialog'
import {
  armarConfirmacionDeRuta,
  armarVentaDeRuta,
  permisoRequeridoPara,
  type CarritoDeRuta,
  type DatosParaVender,
} from '../../../domain/ruta/armadoDeVentaLocal'
import {
  agregarMedio,
  agregarProducto,
  cambiarCantidades,
  cambiarMedio,
  carritoNuevo,
  clientesParaElegir,
  hayLineas,
  leerCantidad,
  presentacionesDeVenta,
  productosOfrecidos,
  quitarMedio,
  quitarProducto,
  type ProductoOfrecido,
} from '../../../domain/ruta/carritoDeRuta'
import { personasQueDebenPonerPin, type TipoDeAutorizacion } from '../../../domain/ventas/autorizacionDeVenta'
import { generarOperationId } from '../../../lib/api/operationId'
import { obtenerOGenerarDispositivoId } from '../../../lib/dispositivo/dispositivoId'
import { confirmarVentaLocal } from '../../../sync/confirmarVentaLocal'
import { APP_VERSION } from '../../../sync/appVersion'
import { useAhora } from '../datos/useAhora'
import { useDatosParaVender } from '../datos/paraVender'
import { DialogoDePinSupervisor } from './DialogoDePinSupervisor'
import { useGuardaDelCarrito } from './contextoGuarda'
import { PasoCliente } from './PasoCliente'
import { PasoCobro } from './PasoCobro'
import { PasoPedido } from './PasoPedido'
import { verificarSupervisores, type PersonaQueAutoriza } from './verificarSupervisores'

/**
 * Vender en `/ruta` (change 22a, `design.md` D1, D4, D12, D14): una pantalla por pasos pensada
 * para el teléfono (Cliente, Pedido, Cobro y confirmación). Toda venta se confirma en el
 * teléfono y queda en la cola, haya o no señal. El carrito vive solo en memoria (VTA-07) y avisa
 * a la guarda mientras tiene líneas. Sin lógica de negocio: el armado, las reglas y la
 * transacción son funciones de `domain/ruta/` y `sync/`.
 */
type Paso = 'cliente' | 'pedido' | 'cobro'

const TITULO_DEL_PASO: Record<Paso, string> = {
  cliente: 'Paso 1 de 3: cliente',
  pedido: 'Paso 2 de 3: pedido',
  cobro: 'Paso 3 de 3: cobro y confirmación',
}

export function VenderScreen() {
  const lectura = useDatosParaVender()

  if (lectura.estado === 'cargando') return <p className="text-sm text-primary">Cargando…</p>
  if (lectura.estado === 'sin_datos') {
    return <p className="text-sm text-primary">Vender necesita los datos del día: abrí la jornada para descargarlos.</p>
  }
  if (!lectura.datos.sesion.permisos.includes('VENDER')) {
    return <p className="text-sm text-primary">No tenés permiso para vender.</p>
  }
  return <VentaDeRuta datos={lectura.datos} />
}

const MENSAJE_DE_FALLA = 'No se pudo guardar la venta. Probá de nuevo.'

function VentaDeRuta({ datos }: { datos: DatosParaVender }) {
  const navegar = useNavigate()
  const [parametros] = useSearchParams()
  const guarda = useGuardaDelCarrito()
  const ahora = useAhora()

  const clienteInicial = datos.clientes.some((c) => c.id === parametros.get('cliente')) ? (parametros.get('cliente') ?? '') : ''
  const [carrito, setCarrito] = useState<CarritoDeRuta>(() => carritoNuevo(clienteInicial, generarOperationId))
  const [paso, setPaso] = useState<Paso>(clienteInicial === '' ? 'cliente' : 'pedido')
  const [busquedaCliente, setBusquedaCliente] = useState('')
  const [busquedaProducto, setBusquedaProducto] = useState('')
  const [confirmando, setConfirmando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pidiendoPin, setPidiendoPin] = useState(false)
  const [verificando, setVerificando] = useState(false)
  const [errorDePin, setErrorDePin] = useState<string | null>(null)
  const [descartando, setDescartando] = useState(false)

  // D12: mientras hay líneas o una confirmación en curso, la guarda impide aplicar una versión nueva.
  const abierto = hayLineas(carrito) || confirmando
  const { marcar } = guarda
  useEffect(() => {
    marcar(abierto)
  }, [abierto, marcar])
  useEffect(() => () => marcar(false), [marcar])

  const armada = useMemo(() => armarVentaDeRuta(datos, carrito, ahora), [datos, carrito, ahora])

  const versionDePrecios = armada.lista.versionId ?? ''
  const ofrecidos = useMemo(
    () => productosOfrecidos(datos, versionDePrecios, busquedaProducto),
    [datos, versionDePrecios, busquedaProducto],
  )
  const clientes = useMemo(() => clientesParaElegir(datos, busquedaCliente), [datos, busquedaCliente])
  const nombreDeProducto = (productoId: string) => datos.productos.find((p) => p.id === productoId)?.nombre ?? '—'
  const actualizar = (cambio: (c: CarritoDeRuta) => CarritoDeRuta) => setCarrito(cambio)

  const personas: PersonaQueAutoriza[] = personasQueDebenPonerPin(armada.autorizacionesNecesarias, armada.seleccion).map((id) => {
    const tipo = armada.autorizacionesNecesarias.find((t) => armada.seleccion[t] === id) as TipoDeAutorizacion
    return { id, nombre: armada.autorizadores.find((a) => a.id === id)?.nombre ?? id, permiso: permisoRequeridoPara(tipo) }
  })

  const guardar = async (verificados: string[]) => {
    setConfirmando(true)
    setError(null)
    try {
      const dispositivoId = await obtenerOGenerarDispositivoId()
      // Se vuelve a armar con la hora de ahora: el número y los precios vigentes son los de confirmar.
      const momento = new Date()
      const entrada = armarConfirmacionDeRuta(datos, carrito, armarVentaDeRuta(datos, carrito, momento), {
        usuarioId: datos.sesion.usuario.id,
        dispositivoId,
        ahora: momento,
        appVersion: APP_VERSION,
        autorizadoresVerificados: verificados,
      })
      const resultado = await confirmarVentaLocal(entrada)
      marcar(false)
      navegar(`/ruta/ventas/${resultado.venta.venta_id}`, { replace: true })
    } catch {
      // No quedó nada guardado: el carrito sigue abierto y se reintenta con la misma operación (INV-06).
      setError(MENSAJE_DE_FALLA)
      setConfirmando(false)
    }
  }

  const alConfirmar = () => {
    if (personas.length > 0) {
      setErrorDePin(null)
      setPidiendoPin(true)
      return
    }
    void guardar([])
  }

  const alVerificarPin = async (pins: Record<string, string>) => {
    setVerificando(true)
    setErrorDePin(null)
    const resultado = await verificarSupervisores(datos.sesion.usuario.id, personas, pins)
    setVerificando(false)
    if (resultado.tipo === 'error') {
      setErrorDePin(resultado.mensaje)
      return
    }
    setPidiendoPin(false)
    await guardar(resultado.verificados)
  }

  const alCancelar = () => (hayLineas(carrito) ? setDescartando(true) : navegar('/ruta'))

  const clienteNombre = armada.cliente?.nombre ?? ''

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-primary">Vender</h1>
        <button type="button" className="text-sm text-primary/70 underline" onClick={alCancelar}>
          Cancelar
        </button>
      </div>
      <p className="text-xs text-primary/70">{TITULO_DEL_PASO[paso]}</p>

      {paso === 'cliente' && (
        <PasoCliente
          clientes={clientes}
          busqueda={busquedaCliente}
          alBuscar={setBusquedaCliente}
          alElegir={(clienteId) => {
            actualizar((c) => ({ ...c, clienteId }))
            setPaso('pedido')
          }}
        />
      )}

      {paso === 'pedido' && (
        <PasoPedido
          clienteNombre={clienteNombre}
          armada={armada}
          carrito={carrito}
          busqueda={busquedaProducto}
          ofrecidos={ofrecidos}
          presentacionesDe={(productoId) => presentacionesDeVenta(datos, productoId)}
          nombreDe={nombreDeProducto}
          motivos={datos.motivos}
          alBuscar={setBusquedaProducto}
          alCambiarCliente={() => setPaso('cliente')}
          alAgregar={(producto: ProductoOfrecido) =>
            actualizar((c) =>
              agregarProducto(c, { productoId: producto.id, presentaciones: presentacionesDeVenta(datos, producto.id) }, generarOperationId),
            )
          }
          alCambiarCantidades={(productoId, cambio) =>
            actualizar((c) =>
              cambiarCantidades(c, productoId, {
                ...(cambio.cajas === undefined ? {} : { cajas: leerCantidad(cambio.cajas) }),
                ...(cambio.unidades === undefined ? {} : { unidades: leerCantidad(cambio.unidades) }),
              }),
            )
          }
          alQuitar={(productoId) => actualizar((c) => quitarProducto(c, productoId))}
          alCambiarGeneral={(texto) => actualizar((c) => ({ ...c, generalTexto: texto }))}
          alCambiarPropio={(lineaId, texto) => actualizar((c) => ({ ...c, propios: { ...c.propios, [lineaId]: texto } }))}
          alCambiarMotivoDescuento={(motivoId) => actualizar((c) => ({ ...c, motivoDescuentoId: motivoId }))}
          alCambiarLista={(listaId) => actualizar((c) => ({ ...c, listaId, versionId: '' }))}
          alCambiarVersion={(versionId) =>
            actualizar((c) => ({
              ...c,
              versionId,
              listaId: versionId !== '' && c.listaId === '' ? (armada.lista.listaId ?? '') : c.listaId,
            }))
          }
          alCambiarMotivoLista={(motivoId) => actualizar((c) => ({ ...c, motivoListaId: motivoId }))}
          alSiguiente={() => setPaso('cobro')}
        />
      )}

      {paso === 'cobro' && (
        <PasoCobro
          armada={armada}
          carrito={carrito}
          mediosPago={datos.mediosPago}
          confirmando={confirmando}
          error={error}
          alAgregarMedio={() => actualizar(agregarMedio)}
          alCambiarMedio={(indice, cambio) => actualizar((c) => cambiarMedio(c, indice, cambio))}
          alQuitarMedio={(indice) => actualizar((c) => quitarMedio(c, indice))}
          alCambiarObservacion={(texto) => actualizar((c) => ({ ...c, observacionCobranza: texto }))}
          alAceptarExceso={(acepta) => actualizar((c) => ({ ...c, aceptaExceso: acepta }))}
          alElegirSupervisor={(tipo, id) => actualizar((c) => ({ ...c, seleccion: { ...c.seleccion, [tipo]: id } }))}
          alVenderIgual={(acepta) => actualizar((c) => ({ ...c, venderIgual: acepta }))}
          alConfirmar={alConfirmar}
          alVolver={() => setPaso('pedido')}
        />
      )}

      {pidiendoPin && (
        <DialogoDePinSupervisor
          personas={personas}
          verificando={verificando}
          error={errorDePin}
          onVerificar={(pins) => void alVerificarPin(pins)}
          onCancelar={() => setPidiendoPin(false)}
        />
      )}

      <Dialogo abierto={descartando} titulo="¿Descartar la venta?" onCerrar={() => setDescartando(false)}>
        <p className="mb-3 text-sm text-primary">Si salís ahora se pierde lo que cargaste. Todavía no se confirmó nada.</p>
        <div className="flex justify-end gap-2">
          <Boton variante="secundario" onClick={() => setDescartando(false)}>
            Seguir vendiendo
          </Boton>
          <Boton
            variante="peligro"
            onClick={() => {
              marcar(false)
              navegar('/ruta')
            }}
          >
            Descartar
          </Boton>
        </div>
      </Dialogo>
    </div>
  )
}

export default VenderScreen
