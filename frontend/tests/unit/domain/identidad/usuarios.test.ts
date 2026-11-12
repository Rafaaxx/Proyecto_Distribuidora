/**
 * Change 20b, tareas 10.1 a 10.4 (D5, D6, D8, D10, D12, D16, D20): reglas puras de las pantallas
 * de usuarios, roles y "Mi contraseña" (spec `identidad/administracion-de-usuarios`,
 * `identidad/administracion-de-roles`, `identidad/autenticacion-y-sesion`; ADR-027, ADR-028,
 * ADR-053, ADR-056, DSC-06, INV-01, INV-03). Solo UX: el servidor valida igual.
 */

import { describe, expect, it } from 'vitest'

import {
  avisosDeBaja,
  enlaceDeUsuariosConTopePropio,
  esquemaAltaDeUsuario,
  esquemaContrasenaDeUsuario,
  esquemaEdicionDeUsuario,
  esquemaMiContrasena,
  esquemaNombreDeRol,
  esquemaTopePropio,
  mensajeDeErrorDeUsuarios,
  rolesAsignables,
  textoDeTopesPorRol,
  topePropioSinEfecto,
} from '../../../../src/domain/identidad/usuarios'

const ALTA_VALIDA = {
  usuario: 'laura',
  nombre: 'Laura Gómez',
  email: 'laura@ejemplo.com',
  rol_id: 'r1',
  password: 'una-clave-larga',
  confirmacion: 'una-clave-larga',
}

describe('esquemaAltaDeUsuario (D9, D8, INV-01)', () => {
  it('recorta nombre y usuario, deja el email vacío como nulo y no envía la confirmación', () => {
    const salida = esquemaAltaDeUsuario.parse({ ...ALTA_VALIDA, usuario: ' laura ', nombre: '  Laura Gómez ', email: '  ' })

    expect(salida).toEqual({
      usuario: 'laura',
      nombre: 'Laura Gómez',
      email: null,
      rol_id: 'r1',
      password: 'una-clave-larga',
    })
  })

  it.each([
    ['confirmación distinta', { confirmacion: 'otra-clave-larga' }, 'confirmacion'],
    ['contraseña corta', { password: 'corta', confirmacion: 'corta' }, 'password'],
    ['contraseña en blanco', { password: '        ', confirmacion: '        ' }, 'password'],
    ['nombre vacío', { nombre: '   ' }, 'nombre'],
    ['nombre de 201 caracteres', { nombre: 'a'.repeat(201) }, 'nombre'],
    ['usuario vacío', { usuario: ' ' }, 'usuario'],
    ['sin rol', { rol_id: '' }, 'rol_id'],
  ])('rechaza %s y marca el campo', (_titulo, cambio, campo) => {
    const resultado = esquemaAltaDeUsuario.safeParse({ ...ALTA_VALIDA, ...cambio })

    expect(resultado.success).toBe(false)
    expect(resultado.error?.issues.map((i) => i.path[0])).toContain(campo)
  })

  it('acepta una contraseña de 8 caracteres sin mayúsculas ni números (D9: sin reglas de composición)', () => {
    expect(esquemaAltaDeUsuario.safeParse({ ...ALTA_VALIDA, password: 'abcdefgh', confirmacion: 'abcdefgh' }).success).toBe(true)
  })
})

describe('esquemaEdicionDeUsuario (D9)', () => {
  it('recorta el nombre y vuelve nulo el email vacío', () => {
    expect(esquemaEdicionDeUsuario.parse({ nombre: ' Ana ', email: '' })).toEqual({ nombre: 'Ana', email: null })
  })

  it('rechaza el nombre en blanco', () => {
    expect(esquemaEdicionDeUsuario.safeParse({ nombre: '  ', email: '' }).success).toBe(false)
  })
})

describe('esquemaContrasenaDeUsuario (D8)', () => {
  it('lleva solo la contraseña y exige que la confirmación coincida', () => {
    expect(esquemaContrasenaDeUsuario.parse({ contrasena: 'clave-nueva-1', confirmacion: 'clave-nueva-1' })).toEqual({
      contrasena: 'clave-nueva-1',
    })
    const distinta = esquemaContrasenaDeUsuario.safeParse({ contrasena: 'clave-nueva-1', confirmacion: 'clave-nueva-2' })
    expect(distinta.success).toBe(false)
    expect(distinta.error?.issues[0]?.path).toEqual(['confirmacion'])
  })

  it('rechaza menos de 8 caracteres', () => {
    expect(esquemaContrasenaDeUsuario.safeParse({ contrasena: 'corta', confirmacion: 'corta' }).success).toBe(false)
  })
})

describe('esquemaMiContrasena (D20, ADR-018)', () => {
  const VALIDA = { actual: 'la-de-siempre', nueva: 'clave-nueva-1', confirmacion: 'clave-nueva-1' }

  it('lleva la actual y la nueva; la confirmación es solo de interfaz', () => {
    expect(esquemaMiContrasena.parse(VALIDA)).toEqual({ actual: 'la-de-siempre', nueva: 'clave-nueva-1' })
  })

  it.each([
    ['confirmación distinta', { confirmacion: 'otra-distinta' }, 'confirmacion'],
    ['nueva corta', { nueva: 'corta', confirmacion: 'corta' }, 'nueva'],
    ['sin la actual', { actual: '' }, 'actual'],
  ])('rechaza %s', (_titulo, cambio, campo) => {
    const resultado = esquemaMiContrasena.safeParse({ ...VALIDA, ...cambio })

    expect(resultado.success).toBe(false)
    expect(resultado.error?.issues.map((i) => i.path[0])).toContain(campo)
  })
})

describe('esquemaTopePropio (D12, INV-03)', () => {
  it.each([
    ['5', '0.050000'],
    ['12,5', '0.125000'],
    ['100', '1.000000'],
  ])('el porcentaje %s viaja como la fracción %s', (escrito, fraccion) => {
    expect(esquemaTopePropio.parse({ tope_descuento: escrito })).toEqual({ tope_descuento: fraccion })
  })

  it('vacío significa volver al tope del rol (null)', () => {
    expect(esquemaTopePropio.parse({ tope_descuento: '  ' })).toEqual({ tope_descuento: null })
  })

  it.each(['120', '-1', 'cinco', '5,12345'])('rechaza %s', (escrito) => {
    expect(esquemaTopePropio.safeParse({ tope_descuento: escrito }).success).toBe(false)
  })
})

describe('topePropioSinEfecto (D12)', () => {
  it('avisa cuando el rol no tiene descuento manual y hay tope propio', () => {
    expect(topePropioSinEfecto(['VENDER'], '0.050000')).toBe(true)
  })

  it('no avisa con el permiso, ni sin tope propio', () => {
    expect(topePropioSinEfecto(['VENDER', 'DESCUENTO_MANUAL'], '0.050000')).toBe(false)
    expect(topePropioSinEfecto(['VENDER'], null)).toBe(false)
  })
})

describe('esquemaNombreDeRol (D10)', () => {
  it('recorta el nombre', () => {
    expect(esquemaNombreDeRol.parse({ nombre: '  Repartidor ' })).toEqual({ nombre: 'Repartidor' })
  })

  it.each(['   ', 'a'.repeat(101)])('rechaza un nombre vacío o de más de 100 caracteres', (nombre) => {
    expect(esquemaNombreDeRol.safeParse({ nombre }).success).toBe(false)
  })

  it('acepta 100 caracteres justos', () => {
    expect(esquemaNombreDeRol.safeParse({ nombre: 'a'.repeat(100) }).success).toBe(true)
  })
})

describe('rolesAsignables (D7, D9)', () => {
  const roles = [
    { id: '1', nombre: 'A', activo: true },
    { id: '2', nombre: 'B', activo: false },
  ]

  it('ofrece solo los roles activos', () => {
    expect(rolesAsignables(roles).map((r) => r.id)).toEqual(['1'])
  })

  it('mantiene el rol actual del usuario aunque esté de baja, para poder mostrarlo', () => {
    expect(rolesAsignables(roles, '2').map((r) => r.id)).toEqual(['1', '2'])
  })
})

describe('textoDeTopesPorRol (tarea 8.6)', () => {
  it.each([
    [3, 1, '3 (1 inactivo)'],
    [3, 2, '3 (2 inactivos)'],
    [3, 0, '3'],
    [0, 0, '0'],
  ])('total %s con %s inactivos -> %s', (total, inactivos, texto) => {
    expect(textoDeTopesPorRol(total, inactivos)).toBe(texto)
  })
})

describe('enlaceDeUsuariosConTopePropio', () => {
  it('filtra por el rol y por tope propio', () => {
    expect(enlaceDeUsuariosConTopePropio('abc')).toBe('/admin/usuarios?rol_id=abc&con_tope_propio=true')
  })
})

describe('avisosDeBaja (D6)', () => {
  it('avisa de la jornada abierta nombrando la ubicación', () => {
    const avisos = avisosDeBaja({ jornadas: ['Camión 1'], clientesAsignados: 0, masDeLosContados: false })

    expect(avisos).toHaveLength(1)
    expect(avisos[0]).toContain('Camión 1')
    expect(avisos[0]).toContain('jornada')
  })

  it('avisa de los clientes asignados con la cantidad', () => {
    const avisos = avisosDeBaja({ jornadas: [], clientesAsignados: 12, masDeLosContados: false })

    expect(avisos).toEqual([expect.stringContaining('12 clientes')])
  })

  it('con un solo cliente usa el singular, y con muchos dice "más de"', () => {
    expect(avisosDeBaja({ jornadas: [], clientesAsignados: 1, masDeLosContados: false })[0]).toContain('1 cliente asignado')
    expect(avisosDeBaja({ jornadas: [], clientesAsignados: 100, masDeLosContados: true })[0]).toContain('más de 100')
  })

  it('sin jornada ni clientes no hay avisos', () => {
    expect(avisosDeBaja({ jornadas: [], clientesAsignados: 0, masDeLosContados: false })).toEqual([])
  })
})

describe('mensajeDeErrorDeUsuarios (D16, D20)', () => {
  it.each([
    'IDENTIDAD_AUTOBAJA',
    'IDENTIDAD_ROL_INACTIVO',
    'IDENTIDAD_USUARIO_DUPLICADO',
    'IDENTIDAD_SIN_ADMINISTRADOR',
    'IDENTIDAD_NOMBRE_DE_ROL_INVALIDO',
    'IDENTIDAD_NOMBRE_DE_ROL_DUPLICADO',
    'IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS',
    'IDENTIDAD_CONTRASENA_INCORRECTA',
    'IDENTIDAD_CONTRASENA_INVALIDA',
    'IDENTIDAD_CONTRASENA_NUEVA_IGUAL_A_ACTUAL',
    'IDENTIDAD_LOGIN_BLOQUEADO_POR_INTENTOS',
    'IDENTIDAD_TOPE_DESCUENTO_FUERA_DE_RANGO',
    'IDENTIDAD_TRANSICION_ESTADO_USUARIO_INVALIDA',
    'VENDEDOR_INVALIDO',
    'CLIENTE_CONSUMIDOR_FINAL_SIN_VENDEDOR',
    'PERMISO_REQUERIDO',
  ])('explica %s en palabras simples, sin repetir el código', (codigo) => {
    const mensaje = mensajeDeErrorDeUsuarios(codigo, 'texto del servidor')

    expect(mensaje).not.toBe('texto del servidor')
    expect(mensaje).not.toContain('IDENTIDAD_')
    expect(mensaje.length).toBeGreaterThan(20)
  })

  it('explica la baja de rol con la cantidad de usuarios activos', () => {
    expect(mensajeDeErrorDeUsuarios('IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS', 'x', { usuariosActivos: 3 })).toContain('3 usuarios activos')
    expect(mensajeDeErrorDeUsuarios('IDENTIDAD_ROL_CON_USUARIOS_ACTIVOS', 'x', { usuariosActivos: 1 })).toContain('1 usuario activo')
  })

  it('conserva el mensaje del servidor con un código desconocido o ausente', () => {
    expect(mensajeDeErrorDeUsuarios('OTRO', 'texto del servidor')).toBe('texto del servidor')
    expect(mensajeDeErrorDeUsuarios(null, 'texto del servidor')).toBe('texto del servidor')
  })
})
