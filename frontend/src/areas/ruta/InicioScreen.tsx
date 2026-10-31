import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert } from '../../components/ui/Alert'
import { Ayuda } from '../../components/ui/Ayuda'
import { Boton } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { asegurarAlmacenamientoPersistente, type EstadoDeAlmacenamiento } from '../../lib/almacenamiento'
import { useConectado } from '../../lib/conexion'
import { formatearFechaHora } from '../../lib/fecha'
import { actualizarDatos, type ResultadoActualizacion } from '../../sync/actualizarDatos'
import { useDatosDeInicio } from './datos/lecturas'
import { useVentasSinEnviar } from './datos/ventas'
import { useSesionRutaActiva } from './sesion/contextoSesion'

/**
 * Inicio de `/ruta` (change 21, `design.md` D2, D11, D18, D19; RUT-03, RUT-09, SYN-11): usuario,
 * jornada y ubicación, conexión, hora de los datos con "Actualizar datos", advertencia de
 * almacenamiento y accesos. Lee siempre de la base local; solo la consulta de la jornada al
 * entrar y "Actualizar datos" usan la red. Sin lógica de negocio: las decisiones viven en
 * `sesion/entrada.ts` y `sync/`.
 */
const ACCESOS = [
  { a: '/ruta/clientes', texto: 'Clientes' },
  { a: '/ruta/productos', texto: 'Productos' },
  { a: '/ruta/stock', texto: 'Stock' },
  { a: '/ruta/cuenta', texto: 'Mi cuenta' },
  { a: '/ruta/ayuda', texto: 'Ayuda' },
] as const

const MENSAJES_DE_FALLA: Record<Exclude<ResultadoActualizacion, 'actualizados'>, string> = {
  sin_jornada: 'No se pudieron actualizar los datos: no tenés una jornada abierta.',
  sesion_vencida: 'No se pudieron actualizar los datos: tu sesión venció. Cerrá la aplicación y volvé a abrirla para ingresar de nuevo.',
  sin_red: 'No se pudieron actualizar los datos: no hay conexión con el servidor.',
  error: 'No se pudieron actualizar los datos. Probá de nuevo en unos minutos.',
}

const MOTIVO_SIN_DATOS = 'Vender necesita los datos del día: abrí la jornada para descargarlos.'
const MOTIVO_SIN_JORNADA = 'Vender requiere una jornada abierta.'

function textoDeSinEnviar(cantidad: number): string {
  if (cantidad === 0) return 'Todo enviado'
  return cantidad === 1 ? '1 venta sin enviar' : `${cantidad} ventas sin enviar`
}

const CLASE_ENLACE =
  'inline-flex items-center justify-center rounded-md border border-border bg-surface-muted px-3 py-3 text-sm font-medium text-primary hover:bg-surface'

export function InicioScreen() {
  const datos = useDatosDeInicio()
  const { entrada, reintentarEntrada } = useSesionRutaActiva()
  const conectado = useConectado()
  const [actualizando, setActualizando] = useState(false)
  const [falla, setFalla] = useState<string | null>(null)
  const [almacenamiento, setAlmacenamiento] = useState<EstadoDeAlmacenamiento | 'pendiente'>('pendiente')

  const fechaBootstrap = datos.estado === 'listo' ? datos.fechaBootstrap : null
  const sinEnviar = useVentasSinEnviar(datos.estado === 'listo' ? datos.usuario.id : null)

  // D18: se pide en cada arranque mientras no esté concedido y de nuevo tras cada bootstrap aplicado.
  useEffect(() => {
    if (fechaBootstrap === null) return undefined
    let vigente = true
    void asegurarAlmacenamientoPersistente().then((estado) => {
      if (vigente) setAlmacenamiento(estado)
    })
    return () => {
      vigente = false
    }
  }, [fechaBootstrap])

  const actualizar = async () => {
    setActualizando(true)
    setFalla(null)
    const resultado = await actualizarDatos()
    setActualizando(false)
    if (resultado !== 'actualizados') setFalla(MENSAJES_DE_FALLA[resultado])
  }

  if (datos.estado === 'cargando') {
    return (
      <p role="status" className="text-sm text-primary">
        Cargando…
      </p>
    )
  }

  const sinJornada = entrada.tipo === 'sin_jornada'
  const puedeAbrir = datos.estado === 'listo' && datos.permisos.includes('ABRIR_JORNADA')
  // Vender (change 22a, D1, D13, D14): con VENDER en el bootstrap, jornada abierta y datos del día.
  const ofreceVender = datos.estado === 'sin_datos' || (datos.estado === 'listo' && datos.permisos.includes('VENDER'))
  const motivoSinVender = datos.estado === 'sin_datos' ? MOTIVO_SIN_DATOS : sinJornada ? MOTIVO_SIN_JORNADA : null

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-primary">
          {datos.estado === 'listo' ? `Hola, ${datos.usuario.nombre}` : 'Área de ruta'}
        </h1>
        <span className="rounded-md border border-border px-2 py-0.5 text-xs font-medium text-primary">
          {conectado ? 'Con conexión' : 'Sin conexión'}
        </span>
      </div>

      <Card className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-primary">Jornada</h2>
        {sinJornada ? (
          <>
            <p className="text-sm text-primary">
              {datos.estado === 'listo'
                ? 'Tu jornada ya no figura abierta en el servidor. Los datos que ves son los de la última descarga.'
                : 'Todavía no hay datos descargados: abrí una jornada para descargarlos.'}
            </p>
            {puedeAbrir || datos.estado === 'sin_datos' ? (
              conectado ? (
                <Link to="/ruta/jornada/abrir" className={CLASE_ENLACE}>
                  Abrir jornada
                </Link>
              ) : (
                <div className="flex flex-col gap-1">
                  <Boton variante="secundario" disabled>
                    Abrir jornada
                  </Boton>
                  <p className="text-sm text-primary/70">Abrir la jornada requiere conexión.</p>
                </div>
              )
            ) : null}
          </>
        ) : (
          datos.estado === 'listo' && (
            <p className="text-sm text-primary">Jornada abierta en {datos.jornada.ubicacion_nombre ?? 'tu ubicación'}</p>
          )
        )}
      </Card>

      {datos.estado === 'listo' && (
        <Card className="flex flex-col gap-2">
          <div className="flex items-center gap-1">
            <p className="text-sm font-semibold text-primary">Datos de {formatearFechaHora(datos.fechaBootstrap).trim()}</p>
            <Ayuda clave="ruta.datosDelDia" />
          </div>
          <div className="flex flex-col gap-1">
            <Boton variante="secundario" disabled={!conectado || actualizando} onClick={() => void actualizar()}>
              Actualizar datos
            </Boton>
            {!conectado && <p className="text-sm text-primary/70">Actualizar requiere conexión.</p>}
          </div>
          {falla && (
            <Alert>
              <span>{falla}</span>{' '}
              <Boton variante="secundario" disabled={actualizando} onClick={() => void actualizar()}>
                Reintentar
              </Boton>
            </Alert>
          )}
        </Card>
      )}

      {ofreceVender && (
        <Card className="flex flex-col gap-2">
          {sinEnviar !== null && (
            <div className="flex items-center gap-1">
              <p className="text-sm font-semibold text-primary">{textoDeSinEnviar(sinEnviar)}</p>
              <Ayuda clave="ruta.ventaSinEnviar" />
            </div>
          )}
          {motivoSinVender === null ? (
            <Link to="/ruta/vender" className={CLASE_ENLACE}>
              Vender
            </Link>
          ) : (
            <div className="flex flex-col gap-1">
              <Boton variante="secundario" disabled>
                Vender
              </Boton>
              <p className="text-sm text-primary/70">{motivoSinVender}</p>
            </div>
          )}
          {datos.estado === 'listo' && (
            <Link to="/ruta/ventas" className={CLASE_ENLACE}>
              Ventas de hoy
            </Link>
          )}
        </Card>
      )}

      {entrada.tipo === 'error' && (
        <Alert>
          <span>No se pudo consultar tu jornada.</span>{' '}
          <Boton variante="secundario" onClick={() => void reintentarEntrada()}>
            Reintentar
          </Boton>
        </Alert>
      )}

      {almacenamiento !== 'concedido' && almacenamiento !== 'pendiente' && (
        <div
          role="status"
          data-testid="aviso-almacenamiento"
          className="flex w-full min-w-0 max-w-full items-start gap-1 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          <span className="min-w-0 flex-1 break-words">El navegador puede borrar los datos de esta aplicación.</span>
          <Ayuda clave="ruta.almacenamiento" />
        </div>
      )}

      <nav aria-label="Accesos" className="grid grid-cols-2 gap-2">
        {ACCESOS.map((acceso) => (
          <Link key={acceso.a} to={acceso.a} className={CLASE_ENLACE}>
            {acceso.texto}
          </Link>
        ))}
      </nav>
    </div>
  )
}

export default InicioScreen
