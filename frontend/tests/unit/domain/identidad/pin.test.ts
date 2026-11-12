/**
 * Change 18b, tareas 14.2 y 14.3 (RED de "Mi PIN"): reglas de la pantalla del PIN de autorización
 * y de "Mi PIN" (ADR-011, ADR-019; `design.md` D21). La validación local es una ayuda: el servidor
 * valida igual (TR-10), incluida la regla de "PIN trivial".
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  filasDelPinDeAutorizacion,
  mensajeDeErrorDePin,
  ofreceMiPin,
  PERMISOS_DE_MI_PIN,
  validarPinNuevo,
} from '../../../../src/domain/identidad/pin'
import { PERMISOS_DE_AUTORIZACION } from '../../../../src/domain/identidad/roles'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('ofreceMiPin: la entrada del menú solo con algún permiso de autorización (D21 punto 9)', () => {
  it('usa los mismos permisos que la lista de roles (ADR-011)', () => {
    expect([...PERMISOS_DE_MI_PIN]).toEqual([...PERMISOS_DE_AUTORIZACION])
  })

  const con = (...permisos: string[]) => (p: string) => permisos.includes(p)

  it.each(['AUTORIZAR_DESCUENTO', 'SUPERAR_CREDITO', 'VENDER_CLIENTE_SUSPENDIDO', 'USAR_LISTA_ANTERIOR'])(
    'con %s se ofrece',
    (permiso) => {
      expect(ofreceMiPin(con(permiso))).toBe(true)
    },
  )

  it('un vendedor sin permisos de autorización no la ve', () => {
    expect(ofreceMiPin(con('VENDER', 'REGISTRAR_COBRANZA', 'DESCUENTO_MANUAL'))).toBe(false)
    expect(ofreceMiPin(con())).toBe(false)
  })
})

describe('validarPinNuevo (dos veces iguales, al menos 6 dígitos)', () => {
  it('un PIN de 6 dígitos repetido igual es válido', () => {
    expect(validarPinNuevo('482913', '482913')).toEqual({ valido: true })
    expect(validarPinNuevo('48291357', '48291357')).toEqual({ valido: true })
  })

  it('las dos veces tienen que coincidir', () => {
    expect(validarPinNuevo('482913', '482914')).toEqual({ valido: false, mensaje: 'Los dos PIN tienen que ser iguales.' })
  })

  it.each(['', '12345', '48291a', '48 913', '４８２９１３'])('"%s" no tiene el formato (6 números o más)', (pin) => {
    const r = validarPinNuevo(pin, pin)
    expect(r.valido).toBe(false)
    if (!r.valido) expect(r.mensaje).toBe('El PIN tiene que tener al menos 6 números, sin letras ni espacios.')
  })

  it('no decide si es fácil de adivinar: eso lo resuelve el servidor', () => {
    expect(validarPinNuevo('123456', '123456')).toEqual({ valido: true })
  })

  it('no persiste el PIN en ningún almacenamiento ni en IndexedDB', () => {
    const guardar = vi.spyOn(Storage.prototype, 'setItem')
    const abrir = vi.fn()
    vi.stubGlobal('indexedDB', { open: abrir })

    validarPinNuevo('482913', '482913')
    validarPinNuevo('482913', '000000')

    expect(guardar).not.toHaveBeenCalled()
    expect(abrir).not.toHaveBeenCalled()
  })
})

describe('mensajeDeErrorDePin', () => {
  it.each([
    ['IDENTIDAD_CONTRASENA_INCORRECTA', 'La contraseña no es correcta.'],
    [
      'IDENTIDAD_PIN_AUTORIZACION_INVALIDO',
      'El PIN no sirve: tiene que tener al menos 6 números y no puede ser fácil de adivinar, como 123456 o 111111.',
    ],
    ['PERMISO_REQUERIDO', 'No tenés permiso para hacer esto.'],
    [
      'IDENTIDAD_ROL_SIN_AUTORIZACION_PARA_PIN',
      'El rol de esa persona no autoriza excepciones, así que no puede tener PIN de autorización.',
    ],
  ])('%s se dice en palabras claras', (codigo, mensaje) => {
    expect(mensajeDeErrorDePin(codigo, 'texto del servidor')).toBe(mensaje)
  })

  it('el bloqueo por intentos conserva el mensaje del servidor (trae el momento del desbloqueo)', () => {
    expect(mensajeDeErrorDePin('IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS', 'Demasiados intentos. Desbloqueo: 10:25.')).toBe(
      'Demasiados intentos. Desbloqueo: 10:25.',
    )
  })

  it('un código desconocido muestra el mensaje del servidor', () => {
    expect(mensajeDeErrorDePin('OTRO', 'Algo pasó.')).toBe('Algo pasó.')
  })
})

describe('filasDelPinDeAutorizacion (D21 parte A)', () => {
  const roles = [
    { id: 'r-sup', nombre: 'Supervisor', activo: true, permisos: ['AUTORIZAR_DESCUENTO', 'VENDER'] },
    { id: 'r-ven', nombre: 'Vendedor', activo: true, permisos: ['VENDER'] },
    { id: 'r-viejo', nombre: 'Viejo', activo: false, permisos: ['SUPERAR_CREDITO'] },
  ]
  const usuarios = [
    { id: 'u1', usuario: 'marta', nombre: 'Marta', rol_id: 'r-sup', estado: 'ACTIVO', tiene_pin_autorizacion: true, email: null },
    { id: 'u2', usuario: 'pedro', nombre: 'Pedro', rol_id: 'r-ven', estado: 'ACTIVO', tiene_pin_autorizacion: false, email: null },
    { id: 'u3', usuario: 'ana', nombre: 'Ana', rol_id: 'r-sup', estado: 'INACTIVO', tiene_pin_autorizacion: false, email: null },
    { id: 'u4', usuario: 'luis', nombre: 'Luis', rol_id: 'r-viejo', estado: 'ACTIVO', tiene_pin_autorizacion: false, email: null },
    { id: 'u5', usuario: 'eva', nombre: 'Eva', rol_id: 'r-sup', estado: 'ACTIVO', tiene_pin_autorizacion: false, email: null },
  ]

  it('lista los usuarios activos cuyo rol confiere algún permiso de autorización, con su rol y si tienen PIN', () => {
    expect(filasDelPinDeAutorizacion(usuarios, roles)).toEqual([
      { usuarioId: 'u5', nombre: 'Eva', rol: 'Supervisor', tienePin: false },
      { usuarioId: 'u1', nombre: 'Marta', rol: 'Supervisor', tienePin: true },
    ])
  })

  it('no lista a quien no autoriza (Pedro), ni a un inactivo (Ana), ni a un usuario de un rol inactivo (Luis)', () => {
    const ids = filasDelPinDeAutorizacion(usuarios, roles).map((f) => f.usuarioId)
    expect(ids).not.toContain('u2')
    expect(ids).not.toContain('u3')
    expect(ids).not.toContain('u4')
  })

  it('ordena por nombre', () => {
    const nombres = filasDelPinDeAutorizacion([...usuarios].reverse(), roles).map((f) => f.nombre)
    expect(nombres).toEqual(['Eva', 'Marta'])
  })
})
