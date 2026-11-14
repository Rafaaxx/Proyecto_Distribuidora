import { Link } from 'react-router-dom'

import { clasesDeBoton } from '../components/ui/botonEstilos'
import { useTituloDePagina } from '../lib/useTituloDePagina'

/**
 * Página de presentación de `/`: cuenta qué es el sistema y para qué sirve, y lleva a cada área.
 * Sin lógica de negocio ni dependencias nuevas; los textos viven como datos arriba del componente.
 * Solo afirma lo que el sistema hace hoy (etapa 1, `docs/00-vision-y-alcance.md` §6.1).
 */

type IconoId =
  | 'telefono'
  | 'pdf'
  | 'stock'
  | 'precios'
  | 'cuentas'
  | 'utilidad'
  | 'jornada'
  | 'reportes'
  | 'usuarios'
  | 'copias'
  | 'papel'
  | 'balanza'
  | 'deuda'
  | 'etiqueta'
  | 'sincronizar'
  | 'oficina'
  | 'candado'
  | 'historial'

/** Trazos de 24x24, uno o varios por ícono. Decorativos: siempre van con `aria-hidden`. */
const TRAZOS: Record<IconoId, string[]> = {
  telefono: ['M8 2.5h8a1.5 1.5 0 0 1 1.5 1.5v16a1.5 1.5 0 0 1-1.5 1.5H8A1.5 1.5 0 0 1 6.5 20V4A1.5 1.5 0 0 1 8 2.5Z', 'M11 18.5h2'],
  pdf: ['M7 3h7l4 4v14H7V3Z', 'M14 3v4h4', 'M9.5 12h6M9.5 15.5h6'],
  stock: ['M3.5 8 12 3.5 20.5 8v8L12 20.5 3.5 16V8Z', 'M3.5 8 12 12.5 20.5 8', 'M12 12.5v8'],
  precios: ['M3.5 12.5 12 4h8v8l-8.5 8.5-8-8Z', 'M15.5 8.5h.01'],
  cuentas: ['M4 6.5h16v11H4v-11Z', 'M4 10.5h16', 'M7.5 14.5h3'],
  utilidad: ['M4 19.5V10M10 19.5V5M16 19.5v-7M21 19.5H3'],
  jornada: ['M5 4.5h14v16H5v-16Z', 'M9 4.5v-1.5h6v1.5', 'M8.5 12l2 2 4-4'],
  reportes: ['M4 20V4', 'M4 20h16', 'M8 16l3.5-4 3 2.5L19 8'],
  usuarios: ['M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z', 'M2.5 20c.5-3.5 3.2-5.5 6.5-5.5s6 2 6.5 5.5', 'M16.5 5a3 3 0 0 1 0 6M18 14.8c1.8.6 3 2.3 3.5 5.2'],
  copias: ['M12 3.5c4.7 0 8 1.4 8 3v10.5c0 1.6-3.3 3-8 3s-8-1.4-8-3V6.5c0-1.6 3.3-3 8-3Z', 'M4 12c0 1.6 3.3 3 8 3s8-1.4 8-3', 'M4 6.5c0 1.6 3.3 3 8 3s8-1.4 8-3'],
  papel: ['M6 3h9l3 3v15H6V3Z', 'M9 10h6M9 13.5h6M9 17h3', 'M3 7l3 3'],
  balanza: ['M12 4v16M7 20h10', 'M5 7h14', 'M5 7l-2.5 6a2.8 2.8 0 0 0 5 0L5 7ZM19 7l-2.5 6a2.8 2.8 0 0 0 5 0L19 7Z'],
  deuda: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z', 'M12 7v5l3 2'],
  etiqueta: ['M3.5 12.5 12 4h8v8l-8.5 8.5-8-8Z', 'M15.5 8.5h.01', 'M7 17l-2-2'],
  sincronizar: ['M20 11a8 8 0 0 0-14.5-3.5M4 5v3.5h3.5', 'M4 13a8 8 0 0 0 14.5 3.5M20 19v-3.5h-3.5'],
  oficina: ['M4 20.5V8.5h8v12M12 20.5V4.5h8v16M3 20.5h18', 'M7 12h2M7 16h2M15 8h2M15 12h2M15 16h2'],
  candado: ['M6 11h12v9.5H6V11Z', 'M8.5 11V8a3.5 3.5 0 0 1 7 0v3', 'M12 15v2'],
  historial: ['M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4', 'M12 8v4.5l3 1.5'],
}

function Icono({ id, className = 'size-6' }: { id: IconoId; className?: string }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {TRAZOS[id].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  )
}

interface Elemento {
  icono: IconoId
  titulo: string
  texto: string
}

const PROBLEMAS: readonly Elemento[] = [
  {
    icono: 'papel',
    titulo: 'Los papeles de la ruta',
    texto:
      'El vendedor carga la venta y el cobro en el teléfono. Se terminaron las libretas, las planillas y el pasar en limpio a la noche.',
  },
  {
    icono: 'balanza',
    titulo: 'El stock que no cierra',
    texto:
      'Cada depósito y cada camión tiene su stock. Las transferencias y los ajustes quedan con su motivo, y la rendición muestra las diferencias.',
  },
  {
    icono: 'deuda',
    titulo: 'Las deudas difíciles de seguir',
    texto:
      'Cada cliente y cada proveedor tiene su cuenta corriente. Ves cuánto se debe, cuándo se cobró y cuándo se pagó.',
  },
  {
    icono: 'etiqueta',
    titulo: 'Los precios desactualizados',
    texto:
      'Listas de precios con historial y vigencia. Publicás una versión nueva y el vendedor vende con el precio correcto.',
  },
]

const FUNCIONES_CALLE: readonly Elemento[] = [
  {
    icono: 'telefono',
    titulo: 'Venta desde el teléfono',
    texto: 'Vendé y cobrá en el momento. Sin señal también: las ventas se guardan y se envían solas al volver la conexión.',
  },
  {
    icono: 'pdf',
    titulo: 'Nota de venta en PDF',
    texto: 'Un comprobante generado en el momento para el cliente.',
  },
  {
    icono: 'jornada',
    titulo: 'Jornada y rendición',
    texto: 'Al volver, el vendedor rinde lo que vendió, cobró y le quedó en el vehículo.',
  },
  {
    icono: 'usuarios',
    titulo: 'Dispositivo y PIN',
    texto: 'Cada teléfono queda registrado y se abre con el PIN del vendedor.',
  },
]

const FUNCIONES_OFICINA: readonly Elemento[] = [
  {
    icono: 'stock',
    titulo: 'Stock por depósito y camión',
    texto: 'Transferencias entre ubicaciones y ajustes con motivo, siempre con historial.',
  },
  {
    icono: 'precios',
    titulo: 'Precios y descuentos',
    texto: 'Listas con historial y descuentos con reglas y autorización.',
  },
  {
    icono: 'cuentas',
    titulo: 'Cuentas, cobranzas y pagos',
    texto: 'Cuenta corriente de clientes y proveedores, con cobranzas y pagos registrados.',
  },
  {
    icono: 'utilidad',
    titulo: 'Costos y utilidad',
    texto: 'Costo promedio y utilidad por venta, visibles según el permiso de cada usuario.',
  },
  {
    icono: 'jornada',
    titulo: 'Observaciones y revisión',
    texto: 'Revisá las rendiciones, dejá observaciones y resolvé las diferencias.',
  },
  {
    icono: 'reportes',
    titulo: 'Reportes',
    texto: 'Ventas, rendiciones y saldos de clientes y proveedores.',
  },
]

const PASOS: readonly Elemento[] = [
  {
    icono: 'telefono',
    titulo: 'El vendedor vende y cobra',
    texto: 'Desde el teléfono, con o sin señal. Cada venta queda guardada en el aparato.',
  },
  {
    icono: 'sincronizar',
    titulo: 'Las ventas se sincronizan',
    texto: 'Cuando hay conexión, se envían solas y sin duplicarse, aunque se corte a mitad de camino.',
  },
  {
    icono: 'oficina',
    titulo: 'La oficina controla',
    texto: 'Stock, cuentas corrientes y reportes al día, con lo que pasó realmente en la ruta.',
  },
]

const CONFIANZA: readonly Elemento[] = [
  {
    icono: 'usuarios',
    titulo: 'Cada uno con su usuario',
    texto: 'Roles y permisos: cada persona ve y hace solo lo que le corresponde.',
  },
  {
    icono: 'historial',
    titulo: 'Nada se borra',
    texto: 'Si hay un error, se corrige con un movimiento inverso y queda registrado quién y cuándo.',
  },
  {
    icono: 'copias',
    titulo: 'Copias de seguridad',
    texto: 'Realizadas de manera automática, restauración incluida.',
  },
]

const TELEFONO_VISIBLE = '+54 9 261 650-7807'
const TELEFONO_ENLACE = 'tel:+5492616507807'

const TARJETA =
  'rounded-lg border border-border bg-surface p-5 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-md motion-reduce:transition-none motion-reduce:hover:translate-y-0'
const CAJA_ICONO = 'flex size-11 shrink-0 items-center justify-center rounded-md bg-surface-muted text-primary'
const ETIQUETA_SECCION = 'text-sm font-semibold uppercase tracking-wider text-primary'
const TITULO_SECCION = 'mt-2 text-2xl font-bold tracking-tight text-primary md:text-4xl'
const SECCION = 'mx-auto w-full max-w-6xl px-4 py-12 md:py-20'

function Accesos({ idContexto }: { idContexto: string }) {
  return (
    <nav aria-label={`Accesos ${idContexto}`} className="flex flex-col gap-3 sm:flex-row">
      <Link to="/admin" className={`${clasesDeBoton('primario', 'grande')} px-6 py-3`}>
        Entrar a la administración
      </Link>
      <Link to="/ruta" className={`${clasesDeBoton('secundario', 'grande')} px-6 py-3`}>
        Entrar como vendedor
      </Link>
    </nav>
  )
}

function Tarjeta({ icono, titulo, texto, nivel }: Elemento & { nivel: 'h3' | 'h4' }) {
  const Titulo = nivel
  return (
    <li className={`${TARJETA} flex flex-col gap-3`}>
      <span className={CAJA_ICONO}>
        <Icono id={icono} />
      </span>
      <Titulo className="text-base font-semibold text-primary">{titulo}</Titulo>
      <p className="text-sm leading-relaxed">{texto}</p>
    </li>
  )
}

function Fondo() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      className="pointer-events-none absolute inset-0 size-full text-border opacity-60"
    >
      <defs>
        <pattern id="trama-inicial" width="28" height="28" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1.2" fill="currentColor" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#trama-inicial)" />
    </svg>
  )
}

export function PaginaInicial() {
  useTituloDePagina('Inicio')

  return (
    <div className="min-h-screen overflow-x-hidden bg-surface text-base">
      <header className="relative isolate overflow-hidden border-b border-border bg-gradient-to-b from-surface-muted to-surface">
        <Fondo />
        <div className="relative mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-16 md:py-28">
          <p className={ETIQUETA_SECCION}>Distribuidora</p>
          <h1 className="max-w-4xl text-4xl font-bold tracking-tight text-primary md:text-6xl">
            Tu distribuidora en orden, desde la oficina hasta la calle
          </h1>
          <p className="max-w-2xl text-lg leading-relaxed md:text-xl">
            Vendé y cobrá desde el teléfono, con o sin señal. Controlá stock, precios y cuentas corrientes desde un
            solo lugar. Sin papeles y sin planillas sueltas.
          </p>
          <Accesos idContexto="de la portada" />
        </div>
      </header>

      <main>
        <section aria-labelledby="resuelve" className={SECCION}>
          <p className={ETIQUETA_SECCION}>El día a día</p>
          <h2 id="resuelve" className={TITULO_SECCION}>
            Qué resuelve
          </h2>
          <p className="mt-3 max-w-2xl">Los problemas de siempre de una distribuidora, con una respuesta concreta.</p>
          <ul className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2">
            {PROBLEMAS.map((p) => (
              <Tarjeta key={p.titulo} {...p} nivel="h3" />
            ))}
          </ul>
        </section>

        <section aria-labelledby="funciones" className="border-y border-border bg-surface-muted">
          <div className={SECCION}>
            <p className={ETIQUETA_SECCION}>Funciones</p>
            <h2 id="funciones" className={TITULO_SECCION}>
              Todo lo que necesitás para operar
            </h2>

            <h3 className="mt-10 text-xl font-semibold text-primary">En la calle</h3>
            <ul className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
              {FUNCIONES_CALLE.map((f) => (
                <Tarjeta key={f.titulo} {...f} nivel="h4" />
              ))}
            </ul>

            <h3 className="mt-12 text-xl font-semibold text-primary">En la oficina</h3>
            <ul className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {FUNCIONES_OFICINA.map((f) => (
                <Tarjeta key={f.titulo} {...f} nivel="h4" />
              ))}
            </ul>
          </div>
        </section>

        <section aria-labelledby="como-funciona" className={SECCION}>
          <p className={ETIQUETA_SECCION}>En tres pasos</p>
          <h2 id="como-funciona" className={TITULO_SECCION}>
            Cómo funciona
          </h2>
          <ol className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
            {PASOS.map((paso, i) => (
              <li key={paso.titulo} className={`${TARJETA} flex flex-col gap-3`}>
                <div className="flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground"
                  >
                    {i + 1}
                  </span>
                  <span className={CAJA_ICONO}>
                    <Icono id={paso.icono} />
                  </span>
                </div>
                <h3 className="text-base font-semibold text-primary">{paso.titulo}</h3>
                <p className="text-sm leading-relaxed">{paso.texto}</p>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="confianza" className="border-y border-border bg-surface-muted">
          <div className={SECCION}>
            <h2 id="confianza" className={TITULO_SECCION}>
              Seguridad y confianza
            </h2>
            <ul className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
              {CONFIANZA.map((c) => (
                <Tarjeta key={c.titulo} {...c} nivel="h3" />
              ))}
            </ul>
          </div>
        </section>

        <section aria-labelledby="cierre" className={SECCION}>
          <div className="flex flex-col gap-6 rounded-lg border border-border bg-gradient-to-br from-primary to-primary/80 p-8 text-primary-foreground shadow-md md:p-12">
            <h2 id="cierre" className="max-w-2xl text-2xl font-bold tracking-tight md:text-4xl">
              Empezá cuando quieras
            </h2>
            <p className="max-w-2xl">Elegí tu lugar: la oficina o la ruta.</p>
            <div className="rounded-lg bg-surface p-4 text-primary">
              <Accesos idContexto="del cierre" />
            </div>
          </div>
        </section>

        <section aria-labelledby="contacto" className={SECCION}>
          <p className={ETIQUETA_SECCION}>Hablemos</p>
          <h2 id="contacto" className={TITULO_SECCION}>
            Contacto
          </h2>
          <p className="mt-3 max-w-2xl">¿Querés saber más o necesitás ayuda? Llamanos.</p>
          <a
            href={TELEFONO_ENLACE}
            className={`${clasesDeBoton('primario', 'grande')} mt-6 w-full px-6 py-3 text-lg sm:w-auto`}
          >
            {TELEFONO_VISIBLE}
          </a>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-6 text-sm sm:flex-row sm:items-center sm:justify-between">
          <p className="inline-flex items-center gap-2 font-semibold text-primary">
            <Icono id="candado" className="size-4" />
            Distribuidora
          </p>
          <p>Ventas, stock y cuentas corrientes en un solo lugar.</p>
          <nav aria-label="Información legal" className="flex flex-wrap gap-x-4 gap-y-1">
            <Link to="/privacidad" className="underline underline-offset-2 hover:text-primary">
              Política de privacidad
            </Link>
            <Link to="/terminos" className="underline underline-offset-2 hover:text-primary">
              Términos y condiciones
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  )
}
