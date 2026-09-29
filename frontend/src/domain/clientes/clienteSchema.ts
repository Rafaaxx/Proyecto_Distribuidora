import { z } from 'zod'

/**
 * Validación de los formularios de cliente (change 07, grupo 5, tareas 5.3
 * y 5.4). Mismo criterio que `domain/proveedores/proveedorSchema.ts`: solo
 * UX -- unicidad de código/documento (D1), longitud por tipo de documento
 * (CLI-05) y las reglas de crédito (CRE-01, CRE-03, CRE-06) las valida el
 * servidor (`DOCUMENTO_INVALIDO`, `CODIGO_DUPLICADO`,
 * `LIMITE_CREDITO_INVALIDO`, …).
 *
 * Sin campos de crédito (D3) ni `lista_precio_id` (D2: sin FK hasta el
 * change 13) -- la ficha de alta/edición no los ofrece.
 */
// `razon_social`/`documento_tipo`/`documento_numero`/`telefono`/`email`/
// `codigo` llegan de un `<input>` de texto: el componente convierte `''` a
// `null` con `setValueAs` (mismo criterio que `cuit` en
// `proveedorSchema.ts`) antes de que Zod los vea, así que acá ya son
// `string | null`.
const camposFichaCliente = {
  nombre: z.string().trim().min(1, 'Ingresá un nombre.'),
  direccion: z.string().trim().min(1, 'Ingresá una dirección.'),
  contacto: z.string().trim().min(1, 'Ingresá un contacto.'),
  razon_social: z.string().nullable(),
  documento_tipo: z.string().nullable(),
  documento_numero: z.string().nullable(),
  telefono: z.string().nullable(),
  email: z.string().nullable(),
  codigo: z.string().nullable(),
  estado_facturacion_default: z.string().nullable(),
}

export const esquemaClienteCrear = z.object(camposFichaCliente)
export type DatosClienteCrear = z.infer<typeof esquemaClienteCrear>

/** Catálogo cerrado de `clientes/domain/estado.py` (`01` §18). */
export const ESTADOS_CLIENTE = ['ACTIVO', 'SUSPENDIDO', 'INACTIVO'] as const

/** Catálogo de tipo de documento (CLI-05): la longitud exacta por tipo
 * (CUIT 11 dígitos, DNI 7 a 8) la valida el servidor. */
export const TIPOS_DOCUMENTO = ['DNI', 'CUIT'] as const

export const esquemaClienteModificar = z.object({
  ...camposFichaCliente,
  estado: z.enum(ESTADOS_CLIENTE),
})
export type DatosClienteModificar = z.infer<typeof esquemaClienteModificar>

/** Catálogo cerrado de política de crédito (`03` §4, CRE-03). */
export const POLITICAS_CREDITO = ['ADVERTIR', 'AUTORIZAR', 'BLOQUEAR'] as const

/** Catálogo cerrado de tipo de tolerancia offline (`03` §4, CRE-06). */
export const TIPOS_TOLERANCIA_OFFLINE = ['IMPORTE', 'PORCENTAJE'] as const

const patronDecimal = /^-?\d+(\.\d+)?$/

/**
 * Los tres campos de crédito son opcionales porque `null`/vacío significa
 * HEREDAR de la organización (CRE-03, CRE-06, D8), no "dejar como está":
 * ese es exactamente el contrato de `ClienteCreditoModificarRequest` en el
 * backend. El límite y la tolerancia viajan como string (INV-03,
 * `CLAUDE.md` §4); el componente convierte `''` a `null` antes de que Zod
 * los vea.
 */
export const esquemaClienteCredito = z.object({
  limite_credito: z
    .string()
    .nullable()
    .refine((valor) => valor === null || patronDecimal.test(valor), 'Ingresá un importe válido.'),
  politica_credito: z.enum(POLITICAS_CREDITO).nullable(),
  tolerancia_offline_tipo: z.enum(TIPOS_TOLERANCIA_OFFLINE).nullable(),
  tolerancia_offline_valor: z
    .string()
    .nullable()
    .refine((valor) => valor === null || patronDecimal.test(valor), 'Ingresá un valor válido.'),
})
export type DatosClienteCredito = z.infer<typeof esquemaClienteCredito>

/** Nombre del consumidor final (D4, ADR-029): la proposal usa "Consumidor
 * final" como default, y el comando lo recibe como dato. */
export const esquemaConsumidorFinalConfigurar = z.object({
  nombre: z.string().trim().min(1, 'Ingresá un nombre.'),
})
export type DatosConsumidorFinalConfigurar = z.infer<typeof esquemaConsumidorFinalConfigurar>
