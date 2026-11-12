import { obtenerYo } from '../../../features/identidad/api'
import { hayPinDefinido } from '../../../lib/sesionLocal/pin'
import { borrarSesionLocal, fijarUsuarioLocal, usuarioLocalId } from '../../../lib/sesionLocal/sesionLocal'
import { pendientesDeOtrosUsuarios, type PendientesDeUnVendedor } from '../../../sync/ventasPendientes'

/**
 * Lógica de la sesión local de `/ruta` sin React (change 21, D14, D15, D16).
 */
export type EstadoInicialDeRuta = 'login' | 'pedir_pin'

/** Arranque o recarga: con usuario y PIN guardados se pide el PIN; si no, iniciar sesión. */
export async function estadoInicialDeRuta(): Promise<EstadoInicialDeRuta> {
  const [usuario, pin] = await Promise.all([usuarioLocalId(), hayPinDefinido()])
  return usuario !== undefined && pin ? 'pedir_pin' : 'login'
}

export interface UsuarioRegistrado {
  cambioDeUsuario: boolean
  hayPin: boolean
  /** Ventas sin enviar que dejó otro usuario en este teléfono (D16); se avisa y no se borran. */
  pendientesDeOtro: PendientesDeUnVendedor[]
}

/**
 * Tras un login correcto: si el usuario es distinto del de la sesión local (o no había ninguno
 * conocido) se borran sesión, PIN y datos maestros del anterior ANTES de usar el dispositivo
 * (D16). Las operaciones pendientes se conservan. Un bloqueo por intentos (mismo usuario, sin
 * PIN) conserva los datos y exige definir un PIN nuevo (D15).
 */
export async function registrarUsuarioTrasLogin(): Promise<UsuarioRegistrado> {
  const yo = await obtenerYo()
  const anterior = await usuarioLocalId()
  const cambioDeUsuario = anterior !== undefined && anterior !== yo.usuario.id

  if (anterior !== yo.usuario.id) {
    await borrarSesionLocal()
  }
  await fijarUsuarioLocal(yo.usuario.id)
  return {
    cambioDeUsuario,
    hayPin: await hayPinDefinido(),
    // No depende del usuario anterior: "Cerrar sesión" borra `usuario_local_id`, pero la cola
    // guarda `sobre.usuario_id` y alcanza para saber qué pendientes son de otro.
    pendientesDeOtro: await pendientesDeOtrosUsuarios(yo.usuario.id),
  }
}
