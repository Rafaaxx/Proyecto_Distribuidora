import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Alert } from '../../../components/ui/Alert'
import { Ayuda } from '../../../components/ui/Ayuda'
import { Boton } from '../../../components/ui/Button'
import { Card } from '../../../components/ui/Card'
import { esquemaApertura, ubicacionesParaAbrir } from '../../../domain/stock/jornadas'
import { useOperationIdPorContenido } from '../../../features/compras/useOperationIdPorContenido'
import { abrirJornada, listarUbicaciones, type Ubicacion } from '../../../features/stock/api'
import { ErrorDeStock, mensajeDeErrorDeStock } from '../../../features/stock/errores'
import { useConectado } from '../../../lib/conexion'
import { useDatosDeInicio } from '../datos/lecturas'
import { useSesionRutaActiva } from '../sesion/contextoSesion'

/**
 * Abrir jornada desde `/ruta` (change 21, `design.md` D11, D19; RUT-01, RUT-03, INV-06, INV-16).
 * Reutiliza el comando `JORNADA_ABRIR` del servidor (`features/stock/api.ts`), solo con conexión
 * y con `ABRIR_JORNADA` (la sesión local ya trae los permisos). Reintenta con el mismo
 * `Operation-Id` mientras no cambia la ubicación. Al abrir, vuelve al inicio y encadena el
 * bootstrap (`reintentarEntrada`). Sin TanStack Query: es del área `/admin`.
 */
const TITULO = 'Abrir jornada'
const CLASE_CONTROL = 'rounded-md border border-border px-2 py-2 text-sm'
const MAXIMO_DE_PAGINAS = 20

async function leerUbicacionesActivas(): Promise<Ubicacion[]> {
  const todas: Ubicacion[] = []
  let cursor: string | undefined
  for (let pagina = 0; pagina < MAXIMO_DE_PAGINAS; pagina += 1) {
    const resultado = await listarUbicaciones(true, cursor)
    todas.push(...resultado.items)
    if (!resultado.cursor_siguiente) break
    cursor = resultado.cursor_siguiente
  }
  return todas
}

export function AbrirJornadaScreen() {
  const datos = useDatosDeInicio()
  if (datos.estado === 'cargando') return null
  if (datos.estado === 'listo' && !datos.permisos.includes('ABRIR_JORNADA')) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-lg font-semibold text-primary">{TITULO}</h1>
        <p className="text-sm text-primary">No tenés permiso para abrir jornadas.</p>
        <Link to="/ruta" className="text-sm underline">
          Volver al inicio
        </Link>
      </div>
    )
  }
  return <Formulario />
}

function Formulario() {
  const navigate = useNavigate()
  const conectado = useConectado()
  const { reintentarEntrada } = useSesionRutaActiva()
  const [ubicaciones, setUbicaciones] = useState<Ubicacion[]>([])
  const [falloLaLista, setFalloLaLista] = useState(false)
  const [ubicacionId, setUbicacionId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const operationId = useOperationIdPorContenido({ ubicacion_id: ubicacionId })

  const cargar = useCallback(async () => {
    try {
      setUbicaciones(await leerUbicacionesActivas())
      setFalloLaLista(false)
    } catch {
      setFalloLaLista(true)
    }
  }, [])

  useEffect(() => {
    if (!navigator.onLine) return undefined
    let vigente = true
    leerUbicacionesActivas()
      .then((lista) => {
        if (vigente) setUbicaciones(lista)
      })
      .catch(() => {
        if (vigente) setFalloLaLista(true)
      })
    return () => {
      vigente = false
    }
  }, [])

  const opciones = ubicacionesParaAbrir(ubicaciones)

  const enviar = async () => {
    const validado = esquemaApertura.safeParse({ ubicacion_id: ubicacionId })
    if (!validado.success) {
      setError(validado.error.issues[0]?.message ?? 'Elegí la ubicación que vas a tomar.')
      return
    }
    setError(null)
    setEnviando(true)
    try {
      await abrirJornada(validado.data.ubicacion_id, operationId)
      navigate('/ruta')
      await reintentarEntrada()
    } catch (falla) {
      setError(mensajeDeErrorDeStock(falla, 'apertura'))
      // Otra jornada la tomó antes: se vuelve a leer qué ubicaciones quedan libres.
      if (falla instanceof ErrorDeStock && falla.codigo === 'UBICACION_TOMADA') void cargar()
    } finally {
      setEnviando(false)
    }
  }

  return (
    <main className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-primary">{TITULO}</h1>
        <Link to="/ruta" className="text-sm underline">
          Volver al inicio
        </Link>
      </div>
      <Card>
        <form
          onSubmit={(evento) => {
            evento.preventDefault()
            void enviar()
          }}
          noValidate
          className="flex flex-col gap-4"
        >
          {!conectado && <p className="text-sm text-primary/70">Abrir la jornada requiere conexión.</p>}
          {falloLaLista && <Alert>No se pudieron obtener las ubicaciones.</Alert>}
          <div className="flex flex-col gap-1 text-sm text-primary">
            <div className="flex items-center gap-1">
              <label htmlFor="jornada-ubicacion">Ubicación</label>
              <Ayuda clave="stock.tomaActual" />
            </div>
            <select
              id="jornada-ubicacion"
              className={CLASE_CONTROL}
              value={ubicacionId}
              onChange={(evento) => setUbicacionId(evento.target.value)}
            >
              <option value="">Elegí la ubicación</option>
              {opciones.map((ubicacion) => (
                <option key={ubicacion.id} value={ubicacion.id}>
                  {ubicacion.nombre}
                </option>
              ))}
            </select>
          </div>
          {error && <Alert>{error}</Alert>}
          <div>
            <Boton type="submit" disabled={!conectado || enviando}>
              {TITULO}
            </Boton>
          </div>
        </form>
      </Card>
    </main>
  )
}

export default AbrirJornadaScreen
