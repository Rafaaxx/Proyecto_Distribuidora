import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import type { CarritoDeRuta, InfoDeLista, LineaArmada, MotivoLocal, VentaArmada } from '../../../domain/ruta/armadoDeVentaLocal'
import type { ProductoOfrecido } from '../../../domain/ruta/carritoDeRuta'
import { formatearDinero } from '../../../domain/ruta/lecturasLocales'
import { admiteCajas, admiteUnidadesSueltas, type PresentacionDeVenta } from '../../../domain/ventas/composicion'
import { avisoDeTope } from '../../../domain/ventas/descuentosDeVenta'
import { AMBITO_DE_DESCUENTO_MANUAL, AMBITO_DE_LISTA_ANTERIOR, etiquetaDeVersion } from '../../../domain/ventas/presentacion'

/**
 * Paso 2 de la venta de ruta: el pedido (change 22a, `design.md` D14; PRC-21, PRC-22, VTA-02,
 * VTA-10, DSC-05, DSC-06, STK-06). Buscador de productos con el precio de la versión, cajas y
 * unidades, descuentos y aviso de stock del vehículo. Solo pinta lo que arma el dominio.
 */
const CLASE_CONTROL = 'w-full rounded-md border border-border px-2 py-2 text-sm'

export interface PasoPedidoProps {
  clienteNombre: string
  armada: VentaArmada
  carrito: CarritoDeRuta
  busqueda: string
  ofrecidos: readonly ProductoOfrecido[]
  presentacionesDe: (productoId: string) => PresentacionDeVenta[]
  nombreDe: (productoId: string) => string
  motivos: readonly MotivoLocal[]
  alBuscar: (texto: string) => void
  alCambiarCliente: () => void
  alAgregar: (producto: ProductoOfrecido) => void
  alCambiarCantidades: (productoId: string, cambio: { cajas?: string; unidades?: string }) => void
  alQuitar: (productoId: string) => void
  alCambiarGeneral: (texto: string) => void
  alCambiarPropio: (lineaId: string, texto: string) => void
  alCambiarMotivoDescuento: (motivoId: string) => void
  alCambiarLista: (listaId: string) => void
  alCambiarVersion: (versionId: string) => void
  alCambiarMotivoLista: (motivoId: string) => void
  alSiguiente: () => void
}

type PropsDeLista = Pick<PasoPedidoProps, 'carrito' | 'motivos' | 'alCambiarLista' | 'alCambiarVersion' | 'alCambiarMotivoLista'> & {
  lista: InfoDeLista
}

function BloqueDeLista({ lista, carrito, motivos, alCambiarLista, alCambiarVersion, alCambiarMotivoLista }: PropsDeLista) {
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
        <label htmlFor="vender-lista" className="text-sm font-medium text-primary">
          Lista de precios
        </label>
        <Ayuda clave="ventas.listaAnterior" />
      </div>
      <select id="vender-lista" className={CLASE_CONTROL} value={carrito.listaId} onChange={(e) => alCambiarLista(e.target.value)}>
        <option value="">La del cliente</option>
        {lista.listas.map((l) => (
          <option key={l.id} value={l.id}>
            {l.nombre}
          </option>
        ))}
      </select>
      <label htmlFor="vender-version" className="text-sm font-medium text-primary">
        Versión
      </label>
      <select id="vender-version" className={CLASE_CONTROL} value={carrito.versionId} onChange={(e) => alCambiarVersion(e.target.value)}>
        <option value="">La vigente</option>
        {lista.versionesElegibles.map((v) => (
          <option key={v.id} value={v.id}>
            {etiquetaDeVersion(v.numero, v.estado)}
          </option>
        ))}
      </select>
      {lista.usaOtra && (
        <>
          <label htmlFor="vender-motivo-lista" className="text-sm font-medium text-primary">
            Motivo
          </label>
          <select
            id="vender-motivo-lista"
            className={CLASE_CONTROL}
            value={carrito.motivoListaId}
            onChange={(e) => alCambiarMotivoLista(e.target.value)}
          >
            <option value="">Sin motivo</option>
            {motivos
              .filter((m) => m.ambito === AMBITO_DE_LISTA_ANTERIOR)
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.nombre}
                </option>
              ))}
          </select>
        </>
      )}
    </Card>
  )
}

interface PropsDeLinea {
  linea: LineaArmada
  puedeDarDescuento: boolean
  propio: string
  errorDePropio: string | undefined
  alCambiarPropio: (lineaId: string, texto: string) => void
}

function LineaDelItem({ linea, puedeDarDescuento, propio, errorDePropio, alCambiarPropio }: PropsDeLinea) {
  const etiqueta = `${linea.productoNombre} · ${linea.presentacionNombre}`
  return (
    <li className="flex min-w-0 flex-col gap-1 border-t border-border pt-2 text-sm text-primary">
      <span className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="break-words">
          {linea.cantidad} × {linea.presentacionNombre}
        </span>
        <span className="font-semibold">{formatearDinero(linea.neto)}</span>
      </span>
      {linea.descuentos.length > 0 && (
        <span className="text-xs text-primary/70">
          Bruto {formatearDinero(linea.bruto)} · descuento −{formatearDinero(linea.descuentoTotal)}
        </span>
      )}
      {linea.avisoDeStock !== null && (
        <span className="flex items-center gap-1 text-xs font-medium text-danger">
          {linea.avisoDeStock}
          <Ayuda clave="ruta.stockDelVehiculo" />
        </span>
      )}
      {puedeDarDescuento && (
        <div className="flex flex-col gap-1">
          <label htmlFor={`propio-${linea.lineaId}`} className="text-xs text-primary/70">
            Descuento de {etiqueta} (%)
          </label>
          <input
            id={`propio-${linea.lineaId}`}
            inputMode="decimal"
            className={CLASE_CONTROL}
            value={propio}
            onChange={(e) => alCambiarPropio(linea.lineaId, e.target.value)}
          />
          {errorDePropio && <span className="text-xs text-danger">{errorDePropio}</span>}
        </div>
      )}
    </li>
  )
}

export function PasoPedido(props: PasoPedidoProps) {
  const { armada, carrito, ofrecidos, motivos } = props
  const contexto = armada.contextoDeDescuento
  const hayManual = armada.lineas.some((l) => l.descuentos.some((d) => d.origen === 'MANUAL'))

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <p className="flex flex-wrap items-center gap-2 text-sm text-primary">
        <span className="break-words">Cliente: {props.clienteNombre}</span>
        <button type="button" className="underline" onClick={props.alCambiarCliente}>
          Cambiar
        </button>
      </p>

      {armada.lista.ofreceOtra && (
        <BloqueDeLista
          lista={armada.lista}
          carrito={carrito}
          motivos={motivos}
          alCambiarLista={props.alCambiarLista}
          alCambiarVersion={props.alCambiarVersion}
          alCambiarMotivoLista={props.alCambiarMotivoLista}
        />
      )}

      <div className="flex flex-col gap-1">
        <label htmlFor="vender-buscar-producto" className="text-sm font-medium text-primary">
          Buscar producto
        </label>
        <input
          id="vender-buscar-producto"
          type="search"
          className={CLASE_CONTROL}
          placeholder="Nombre o código"
          value={props.busqueda}
          onChange={(e) => props.alBuscar(e.target.value)}
        />
      </div>
      <ul className="flex flex-col gap-2">
        {ofrecidos.map((producto) => (
          <li key={producto.id} className="flex min-w-0 flex-col gap-1 rounded-md border border-border bg-surface p-3">
            <span className="break-words text-sm font-semibold text-primary">{producto.nombre}</span>
            {producto.conPrecio ? (
              <span className="flex flex-wrap items-center gap-x-2 text-xs text-primary/70">
                {producto.presentaciones.map((p) => (
                  <span key={p.id}>
                    {p.nombre} {p.precio === null ? '' : formatearDinero(p.precio)}
                  </span>
                ))}
                <Ayuda clave="ventas.precio" />
              </span>
            ) : (
              <span className="text-xs text-danger">{producto.mensaje}</span>
            )}
            {producto.conPrecio && (
              <Boton
                variante="secundario"
                className="self-start"
                aria-label={`Agregar ${producto.nombre}`}
                disabled={carrito.items.some((i) => i.productoId === producto.id)}
                onClick={() => props.alAgregar(producto)}
              >
                Agregar
              </Boton>
            )}
          </li>
        ))}
      </ul>

      <div className="flex flex-col gap-2">
        {carrito.items.length === 0 && <p className="text-sm text-primary/70">Todavía no cargaste productos.</p>}
        {carrito.items.map((item) => {
          const nombre = props.nombreDe(item.productoId)
          const presentaciones = props.presentacionesDe(item.productoId)
          const error = armada.erroresPorProducto[item.productoId]
          return (
            <Card key={item.productoId} className="flex min-w-0 flex-col gap-2">
              <div className="flex items-start justify-between gap-2">
                <span className="break-words text-sm font-semibold text-primary">{nombre}</span>
                <Boton variante="secundario" aria-label={`Quitar ${nombre}`} onClick={() => props.alQuitar(item.productoId)}>
                  Quitar
                </Boton>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {admiteCajas(presentaciones) && (
                  <label className="flex min-w-0 flex-col gap-1 text-xs text-primary/70">
                    <span className="flex items-center gap-1">
                      Cajas
                      <Ayuda clave="ventas.cajasYUnidades" />
                    </span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min={0}
                      aria-label={`Cajas de ${nombre}`}
                      className={CLASE_CONTROL}
                      value={String(item.cajas)}
                      onChange={(e) => props.alCambiarCantidades(item.productoId, { cajas: e.target.value })}
                    />
                  </label>
                )}
                {admiteUnidadesSueltas(presentaciones) && (
                  <label className="flex min-w-0 flex-col gap-1 text-xs text-primary/70">
                    <span>Unidades</span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min={0}
                      aria-label={`Unidades de ${nombre}`}
                      className={CLASE_CONTROL}
                      value={String(item.unidades)}
                      onChange={(e) => props.alCambiarCantidades(item.productoId, { unidades: e.target.value })}
                    />
                  </label>
                )}
              </div>
              {error && <Alert>{error}</Alert>}
              <ul className="flex flex-col gap-2">
                {armada.lineas
                  .filter((l) => l.productoId === item.productoId)
                  .map((linea) => (
                    <LineaDelItem
                      key={linea.lineaId}
                      linea={linea}
                      puedeDarDescuento={armada.puedeDarDescuento}
                      propio={carrito.propios[linea.lineaId] ?? ''}
                      errorDePropio={armada.erroresDePropios[linea.lineaId]}
                      alCambiarPropio={props.alCambiarPropio}
                    />
                  ))}
              </ul>
            </Card>
          )
        })}
      </div>

      {contexto !== null && armada.puedeDarDescuento && (
        <Card className="flex flex-col gap-2">
          <div className="flex items-center gap-1">
            <label htmlFor="vender-descuento-general" className="text-sm font-medium text-primary">
              Descuento general (%)
            </label>
            <Ayuda clave="ventas.descuentoGeneral" />
          </div>
          <input
            id="vender-descuento-general"
            inputMode="decimal"
            className={CLASE_CONTROL}
            value={carrito.generalTexto}
            onChange={(e) => props.alCambiarGeneral(e.target.value)}
          />
          {armada.errorDelGeneral && <span className="text-xs text-danger">{armada.errorDelGeneral}</span>}
          <p className="flex items-center gap-1 text-xs text-primary/70">
            {avisoDeTope(contexto)}
            <Ayuda clave="ventas.topeDescuento" />
          </p>
          {hayManual && contexto.motivoObligatorio && (
            <>
              <div className="flex items-center gap-1">
                <label htmlFor="vender-motivo-descuento" className="text-sm font-medium text-primary">
                  Motivo del descuento
                </label>
                <Ayuda clave="ventas.motivoDescuento" />
              </div>
              <select
                id="vender-motivo-descuento"
                className={CLASE_CONTROL}
                value={carrito.motivoDescuentoId}
                onChange={(e) => props.alCambiarMotivoDescuento(e.target.value)}
              >
                <option value="">Elegí el motivo</option>
                {motivos
                  .filter((m) => m.ambito === AMBITO_DE_DESCUENTO_MANUAL)
                  .map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.nombre}
                    </option>
                  ))}
              </select>
            </>
          )}
        </Card>
      )}

      <Card className="flex flex-col gap-1 text-sm text-primary">
        <p data-testid="total-de-la-venta" className="text-base font-semibold">
          Total: {formatearDinero(armada.total)}
        </p>
        {armada.lineas.some((l) => l.descuentos.length > 0) && (
          <p className="flex items-center gap-1 text-xs text-primary/70">
            Incluye descuentos
            <Ayuda clave="ventas.descuentosAutomaticos" />
          </p>
        )}
      </Card>

      <Boton disabled={armada.lineas.length === 0 || Object.keys(armada.erroresPorProducto).length > 0} onClick={props.alSiguiente}>
        Siguiente
      </Boton>
    </div>
  )
}
