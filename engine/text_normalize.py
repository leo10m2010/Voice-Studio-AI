"""Normalización de texto en español (Perú) para el motor TTS.

Qwen3-TTS pronuncia mal las cadenas numéricas (issue #328 del modelo): lee
"S/ 25.50", "3:30 pm" o "15/08/2026" carácter a carácter, en otro idioma o
directamente los omite. Aquí reescribimos esas formas a palabras antes de
mandar el texto al modelo.

Solo biblioteca estándar: el motor se empaqueta con PyInstaller y cada
dependencia nueva engorda el instalador y rompe el build sin ruedas.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["normalize_spanish", "numero_a_palabras"]

# El modelo se usa para spots publicitarios: por encima de mil millones no hay
# cifra realista, y así evitamos generar frases interminables.
_MAX_CARDINAL = 999_999_999


# --------------------------------------------------------------------------
# Cardinales
# --------------------------------------------------------------------------

_UNIDADES = (
    "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho",
    "nueve", "diez", "once", "doce", "trece", "catorce", "quince",
    "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte",
    "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco",
    "veintiséis", "veintisiete", "veintiocho", "veintinueve",
)

_DECENAS = {
    3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta",
    7: "setenta", 8: "ochenta", 9: "noventa",
}

_CENTENAS = {
    1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos",
    5: "quinientos", 6: "seiscientos", 7: "setecientos", 8: "ochocientos",
    9: "novecientos",
}

_CENTENAS_FEM = {
    1: "ciento", 2: "doscientas", 3: "trescientas", 4: "cuatrocientas",
    5: "quinientas", 6: "seiscientas", 7: "setecientas", 8: "ochocientas",
    9: "novecientas",
}


def _hasta_noventa_y_nueve(n: int, femenino: bool, apocope: bool) -> str:
    if n < 30:
        # "uno" se apocopa en "un" delante de sustantivo masculino, de "mil"
        # y de "millones"; en femenino pasa a "una".
        if n == 1:
            return "un" if apocope else ("una" if femenino else "uno")
        if n == 21:
            return "veintiún" if apocope else ("veintiuna" if femenino else "veintiuno")
        return _UNIDADES[n]
    decena, unidad = divmod(n, 10)
    if not unidad:
        return _DECENAS[decena]
    return _DECENAS[decena] + " y " + _hasta_noventa_y_nueve(unidad, femenino, apocope)


def _menor_de_mil(n: int, femenino: bool = False, apocope: bool = False) -> str:
    if n == 100:
        return "cien"  # "cien" solo cuando va solo; "ciento uno" en cuanto hay resto
    centena, resto = divmod(n, 100)
    partes = []
    if centena:
        tabla = _CENTENAS_FEM if femenino else _CENTENAS
        partes.append(tabla[centena])
    if resto:
        partes.append(_hasta_noventa_y_nueve(resto, femenino, apocope))
    return " ".join(partes)


def numero_a_palabras(n: int, femenino: bool = False, apocope: bool = False) -> str | None:
    """Cardinal en palabras, o None si la cifra queda fuera de rango."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    if n < 0 or n > _MAX_CARDINAL:
        return None
    if n == 0:
        return "cero"

    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes = []

    if millones == 1:
        partes.append("un millón")
    elif millones:
        partes.append(_menor_de_mil(millones, apocope=True) + " millones")

    if miles == 1:
        partes.append("mil")  # nunca "un mil"
    elif miles:
        partes.append(_menor_de_mil(miles, femenino=femenino, apocope=True) + " mil")

    if unidades:
        partes.append(_menor_de_mil(unidades, femenino=femenino, apocope=apocope))

    return " ".join(partes)


# --------------------------------------------------------------------------
# Literales numéricos
# --------------------------------------------------------------------------

# Tres formas, en este orden: separador de miles con punto (1.250.000,50),
# separador de miles con coma —el uso peruano— (1,250.50) y número simple.
_NUM = (
    r"[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?"
    r"|[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?"
    r"|\d+(?:[.,]\d+)?"
)

_RE_MILES_PUNTO = re.compile(r"[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?")
_RE_MILES_COMA = re.compile(r"[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?")
_RE_SIMPLE = re.compile(r"(\d+)(?:[.,](\d+))?")


def _partir_numero(bruto: str):
    """Separa un literal en (dígitos enteros, dígitos decimales)."""
    texto = bruto.strip()
    if _RE_MILES_PUNTO.fullmatch(texto):
        entero, _, decimal = texto.partition(",")
        return entero.replace(".", ""), decimal
    if _RE_MILES_COMA.fullmatch(texto):
        entero, _, decimal = texto.partition(".")
        return entero.replace(",", ""), decimal
    coincidencia = _RE_SIMPLE.fullmatch(texto)
    if not coincidencia:
        return None
    return coincidencia.group(1), coincidencia.group(2) or ""


def _decimales_a_palabras(digitos: str) -> str | None:
    if digitos.startswith("0"):
        # "25,05" leído como "cero cinco" para no confundirlo con "25,5".
        return " ".join(_UNIDADES[int(d)] for d in digitos)
    return numero_a_palabras(int(digitos))


def _literal_a_palabras(bruto: str, femenino: bool = False) -> str | None:
    partes = _partir_numero(bruto)
    if partes is None:
        return None
    entero, decimal = partes
    if len(entero) >= 3 and entero.startswith("0"):
        # "007", "0800": tres o más dígitos con ceros delante son un código,
        # no una cantidad. Con dos ("08 de agosto") sí es una cantidad.
        palabras = " ".join(_UNIDADES[int(d)] for d in entero)
    else:
        palabras = numero_a_palabras(int(entero), femenino=femenino)
    if palabras is None:
        return None
    if decimal and set(decimal) != {"0"}:
        cola = _decimales_a_palabras(decimal)
        if cola is None:
            return None
        return palabras + " con " + cola
    return palabras


# --------------------------------------------------------------------------
# Utilidades de sustitución
# --------------------------------------------------------------------------

def _sub(patron: re.Pattern, funcion, texto: str) -> str:
    """Aplica una sustitución dejando intacto lo que la regla no sepa manejar."""

    def envoltura(coincidencia):
        try:
            resultado = funcion(coincidencia)
        except Exception:
            return coincidencia.group(0)
        return coincidencia.group(0) if resultado is None else resultado

    return patron.sub(envoltura, texto)


# --------------------------------------------------------------------------
# Moneda
# --------------------------------------------------------------------------

_RE_SOLES = re.compile(r"(?<!\w)S\s*/\s*\.?\s*(" + _NUM + r")(?!\w)", re.IGNORECASE)
_RE_DOLARES = re.compile(r"(?<!\w)(?:US\s*)?\$\s*(" + _NUM + r")(?!\w)", re.IGNORECASE)


def _partes_monetarias(bruto: str):
    partes = _partir_numero(bruto)
    if partes is None:
        return None
    entero, decimal = partes
    valor = int(entero)
    if valor > _MAX_CARDINAL:
        return None
    # "S/ 25.5" son 50 céntimos, no 5: se completa a dos dígitos.
    fraccion = int((decimal + "00")[:2]) if decimal else 0
    return valor, fraccion


def _frase_moneda(valor: int, fraccion: int, sing: str, plur: str,
                  csing: str, cplur: str) -> str | None:
    partes = []
    if valor or not fraccion:
        entero = numero_a_palabras(valor, apocope=True)
        if entero is None:
            return None
        partes.append(entero + " " + (sing if valor == 1 else plur))
    if fraccion:
        cents = numero_a_palabras(fraccion, apocope=True)
        if cents is None:
            return None
        frase = cents + " " + (csing if fraccion == 1 else cplur)
        partes.append(("con " + frase) if partes else frase)
    return " ".join(partes)


def _rep_soles(coincidencia):
    partes = _partes_monetarias(coincidencia.group(1))
    if partes is None:
        return None
    return _frase_moneda(partes[0], partes[1], "sol", "soles", "céntimo", "céntimos")


def _rep_dolares(coincidencia):
    partes = _partes_monetarias(coincidencia.group(1))
    if partes is None:
        return None
    return _frase_moneda(partes[0], partes[1], "dólar", "dólares", "centavo", "centavos")


# La moneda también viene escrita con letras ("21 soles"), y ahí hace falta la
# apócope: "veintiún soles", no "veintiuno soles".
_RE_MONEDA_PALABRA = re.compile(
    r"(?<![\w.,])(" + _NUM + r")\s+(soles|sol|d[óo]lares|d[óo]lar)(?!\w)",
    re.IGNORECASE,
)


def _rep_moneda_palabra(coincidencia):
    partes = _partes_monetarias(coincidencia.group(1))
    if partes is None:
        return None
    if coincidencia.group(2).lower().startswith("sol"):
        return _frase_moneda(partes[0], partes[1], "sol", "soles", "céntimo", "céntimos")
    return _frase_moneda(partes[0], partes[1], "dólar", "dólares", "centavo", "centavos")


# --------------------------------------------------------------------------
# Porcentaje
# --------------------------------------------------------------------------

_RE_PORCENTAJE = re.compile(r"(?<![\w.,])(" + _NUM + r")\s*%")


def _rep_porcentaje(coincidencia):
    palabras = _literal_a_palabras(coincidencia.group(1))
    if palabras is None:
        return None
    return palabras + " por ciento"


# --------------------------------------------------------------------------
# Fechas
# --------------------------------------------------------------------------

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
)

_RE_FECHA = re.compile(r"(?<![\w/-])(\d{1,2})([/-])(\d{1,2})\2(\d{4}|\d{2})(?![\w/-])")
# Sin año exigimos mes de dos dígitos para no tragarnos fracciones como "3/4".
_RE_FECHA_CORTA = re.compile(r"(?<![\w/-])(\d{1,2})/(\d{2})(?![\w/-])")


def _dia_y_mes(dia: int, mes: int):
    if not 1 <= dia <= 31 or not 1 <= mes <= 12:
        return None
    palabra_dia = "primero" if dia == 1 else numero_a_palabras(dia)
    if palabra_dia is None:
        return None
    return palabra_dia + " de " + _MESES[mes - 1]


def _rep_fecha(coincidencia):
    dia = int(coincidencia.group(1))
    mes = int(coincidencia.group(3))
    bruto_anio = coincidencia.group(4)
    base = _dia_y_mes(dia, mes)
    if base is None:
        return None
    anio = int(bruto_anio)
    if len(bruto_anio) == 2:
        # "15/08/26" en publicidad siempre mira al futuro cercano.
        anio = 2000 + anio if anio < 70 else 1900 + anio
    palabras_anio = numero_a_palabras(anio)
    if palabras_anio is None:
        return None
    return base + " de " + palabras_anio


def _rep_fecha_corta(coincidencia):
    return _dia_y_mes(int(coincidencia.group(1)), int(coincidencia.group(2)))


# --------------------------------------------------------------------------
# Horas
# --------------------------------------------------------------------------

_RE_HORA = re.compile(
    r"(?<![\d:])(2[0-3]|[01]?\d):([0-5]\d)"
    r"(?:\s*([apAP])\s*\.?\s*[mM](?!\w))?(?![\d:])"
)


def _franja_del_dia(hora24: int, minuto: int, meridiano: str | None) -> str:
    # Sin "am/pm" y con hora de reloj de 12 no hay forma de saber si es
    # mañana o tarde: mejor callar que inventar.
    if meridiano is None and hora24 < 13:
        return ""
    if minuto == 0 and hora24 == 12:
        return "del mediodía"
    if minuto == 0 and hora24 == 0:
        return "de la medianoche"
    if hora24 < 6:
        return "de la madrugada"
    if hora24 < 12:
        return "de la mañana"
    if hora24 < 20:
        return "de la tarde"
    return "de la noche"


def _rep_hora(coincidencia):
    hora24 = int(coincidencia.group(1))
    minuto = int(coincidencia.group(2))
    sufijo = coincidencia.group(3)
    meridiano = sufijo.lower() if sufijo else None

    if meridiano == "p" and hora24 < 12:
        hora24 += 12
    elif meridiano == "a" and hora24 == 12:
        hora24 = 0

    hora12 = hora24 % 12 or 12
    palabras = numero_a_palabras(hora12, femenino=True)  # "la una", "las dos"
    if palabras is None:
        return None
    partes = [palabras]

    if minuto == 15:
        partes.append("y cuarto")
    elif minuto == 30:
        partes.append("y media")
    elif minuto:
        minutos = numero_a_palabras(minuto)
        if minutos is None:
            return None
        partes.append("y " + minutos)

    franja = _franja_del_dia(hora24, minuto, meridiano)
    if franja:
        partes.append(franja)
    return " ".join(partes)


# --------------------------------------------------------------------------
# Grados, ordinales y abreviaturas
# --------------------------------------------------------------------------

_RE_GRADOS = re.compile(r"(\d+)\s*[°º]\s*([CF])(?!\w)")

_ORDINALES_M = {
    1: "primero", 2: "segundo", 3: "tercero", 4: "cuarto", 5: "quinto",
    6: "sexto", 7: "séptimo", 8: "octavo", 9: "noveno", 10: "décimo",
}
_ORDINALES_F = {
    1: "primera", 2: "segunda", 3: "tercera", 4: "cuarta", 5: "quinta",
    6: "sexta", 7: "séptima", 8: "octava", 9: "novena", 10: "décima",
}
_ORDINALES_SUFIJO = {
    "1er": "primer", "1ero": "primero", "1ro": "primero",
    "1ra": "primera", "1era": "primera",
    "2do": "segundo", "2da": "segunda",
    "3er": "tercer", "3ero": "tercero", "3ro": "tercero",
    "3ra": "tercera", "3era": "tercera",
    "4to": "cuarto", "4ta": "cuarta",
    "5to": "quinto", "5ta": "quinta",
    "6to": "sexto", "6ta": "sexta",
    "7mo": "séptimo", "7ma": "séptima",
    "8vo": "octavo", "8va": "octava",
    "9no": "noveno", "9na": "novena",
    "10mo": "décimo", "10ma": "décima",
}

_RE_ORDINAL_SUFIJO = re.compile(
    r"(?<!\w)(\d{1,2}(?:ero|era|er|ro|ra|do|da|to|ta|mo|ma|vo|va|no|na))(?!\w)",
    re.IGNORECASE,
)
_RE_ORDINAL_MASC = re.compile(r"(?<!\w)(\d{1,3})\s*[°º]")
_RE_ORDINAL_FEM = re.compile(r"(?<!\w)(\d{1,3})\s*ª")

_ABREVIATURAS = {
    "av": "avenida", "avda": "avenida", "jr": "jirón", "psje": "pasaje",
    "urb": "urbanización", "dr": "doctor", "dra": "doctora",
    "sr": "señor", "sra": "señora", "srta": "señorita",
    "ing": "ingeniero", "nro": "número", "etc": "etcétera",
}
_RE_ABREVIATURA = re.compile(
    r"(?<!\w)(" + "|".join(sorted(_ABREVIATURAS, key=len, reverse=True)) + r")\.[ \t]*",
    re.IGNORECASE,
)
_RE_NUMERO_ABREV = re.compile(r"(?<!\w)N\s*[°º]\s*", re.IGNORECASE)


def _rep_grados(coincidencia):
    valor = int(coincidencia.group(1))
    palabras = numero_a_palabras(valor, apocope=True)
    if palabras is None:
        return None
    return palabras + (" grado" if valor == 1 else " grados")


def _rep_ordinal_sufijo(coincidencia):
    return _ORDINALES_SUFIJO.get(coincidencia.group(1).lower())


def _rep_ordinal_masc(coincidencia):
    valor = int(coincidencia.group(1))
    if valor in _ORDINALES_M:
        return _ORDINALES_M[valor] + " "
    # Por encima de décimo, "45°" es casi siempre temperatura o ángulo:
    # nadie escribe "45°" para "cuadragésimo quinto" en un spot.
    palabras = numero_a_palabras(valor, apocope=True)
    if palabras is None:
        return None
    return palabras + " grados "


def _rep_ordinal_fem(coincidencia):
    valor = int(coincidencia.group(1))
    if valor not in _ORDINALES_F:
        return None
    return _ORDINALES_F[valor] + " "


def _rep_abreviatura(coincidencia):
    # Se emite con espacio final para no pegar la palabra siguiente cuando
    # el original venía sin separación ("Dr.Pérez").
    return _ABREVIATURAS[coincidencia.group(1).lower()] + " "


# --------------------------------------------------------------------------
# Símbolos, multiplicadores y rangos
# --------------------------------------------------------------------------

_RE_AMPERSAND = re.compile(r"\s*&\s*")
_RE_MAS_ENTRE_CIFRAS = re.compile(r"(?<=\d)\s*\+\s*(?=\d)")
_RE_MAS_SUELTO = re.compile(r"(?<!\S)\+(?!\S)")
_RE_MULTIPLICADOR = re.compile(r"(?<!\w)(\d{1,3})\s*[xX×]\s*(\d{1,3})(?!\w)")
# Rangos cortos y ascendentes: así "555-1234" (teléfono) no se lee como rango.
_RE_RANGO = re.compile(r"(?<![\w.,-])(\d{1,3})\s*[-–]\s*(\d{1,3})(?![\w.,-])")

_RE_NUMERO = re.compile(r"(?<![\w.,])(?:" + _NUM + r")(?!\w)")


def _rep_multiplicador(coincidencia):
    izquierda = numero_a_palabras(int(coincidencia.group(1)))
    derecha = numero_a_palabras(int(coincidencia.group(2)))
    if izquierda is None or derecha is None:
        return None
    return izquierda + " por " + derecha


def _rep_rango(coincidencia):
    desde = int(coincidencia.group(1))
    hasta = int(coincidencia.group(2))
    if desde >= hasta:
        return None
    izquierda = numero_a_palabras(desde)
    derecha = numero_a_palabras(hasta)
    if izquierda is None or derecha is None:
        return None
    return izquierda + " a " + derecha


def _rep_numero(coincidencia):
    return _literal_a_palabras(coincidencia.group(0))


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

_ESPACIOS_RAROS = dict.fromkeys(
    [0x00A0, 0x2007, 0x202F, 0x2009, 0x2002, 0x2003], " "
)


def _unificar(texto: str) -> str:
    # NFC deja acentos y símbolos en una sola forma; los espacios "duros" que
    # llegan al pegar desde Word rompen los lookarounds de las reglas.
    texto = unicodedata.normalize("NFC", texto)
    return texto.translate(_ESPACIOS_RAROS)


def _limpiar_espacios(texto: str) -> str:
    texto = re.sub(r"[^\S\n]+", " ", texto)
    texto = re.sub(r" *\n *", "\n", texto)
    texto = re.sub(r"[^\S\n]+([,;:.!?%\)\]])", r"\1", texto)
    return texto.strip()


_DIGITOS_SUELTOS = ("cero", "uno", "dos", "tres", "cuatro",
                    "cinco", "seis", "siete", "ocho", "nueve")

# Un teléfono o un DNI se lee dígito a dígito; leerlos como cardinal daba
# "novecientos ochenta y siete millones seiscientos cincuenta y cuatro mil…"
# para un celular, inservible en un spot.
#
# La longitud sola no basta para distinguirlos: 1000000 también tiene siete
# dígitos y es "un millón". Lo que decide es el contexto, así que solo se
# aplica cuando una palabra de contacto precede a la cifra.
_RE_SERIE_CONTACTO = re.compile(
    # Alternativas de más larga a más corta: con "cel" delante, "celular"
    # coincidiría solo en sus tres primeras letras y la regla entera fallaría.
    r"((?:tel[eé]fonos?|celular(?:es)?|whats?app|cont[aá]ctanos|escr[ií]benos|"
    r"ll[aá]ma(?:nos|rme|r|me)?|anexo|marca|wsp|dni|ruc|cel|tel)\b"
    r"[\s:¡!¿?]*(?:al|a|el)?[\s:]*)"
    # El número puede venir agrupado con espacios, guiones o puntos
    # (062-513200, 987 654 321), pero siempre termina en dígito, así que el
    # punto final de la frase queda fuera.
    r"(\d[\d\s.\-]*\d)",
    re.IGNORECASE,
)


def _rep_serie_contacto(coincidencia):
    prefijo, bruto = coincidencia.group(1), coincidencia.group(2)
    digitos = re.sub(r"\D", "", bruto)
    # Fuera de este rango no es un número de contacto; se deja a las reglas
    # normales para no destrozar una cantidad que siga a la palabra clave.
    if not 6 <= len(digitos) <= 15:
        return None
    return prefijo + " ".join(_DIGITOS_SUELTOS[int(d)] for d in digitos)


def _pipeline(texto: str) -> str:
    texto = _unificar(texto)

    texto = _sub(_RE_SOLES, _rep_soles, texto)
    texto = _sub(_RE_DOLARES, _rep_dolares, texto)
    texto = _sub(_RE_PORCENTAJE, _rep_porcentaje, texto)
    texto = _sub(_RE_FECHA, _rep_fecha, texto)
    texto = _sub(_RE_FECHA_CORTA, _rep_fecha_corta, texto)
    texto = _sub(_RE_HORA, _rep_hora, texto)
    texto = _sub(_RE_GRADOS, _rep_grados, texto)
    texto = _sub(_RE_ORDINAL_SUFIJO, _rep_ordinal_sufijo, texto)
    texto = _RE_NUMERO_ABREV.sub("número ", texto)
    texto = _sub(_RE_ORDINAL_MASC, _rep_ordinal_masc, texto)
    texto = _sub(_RE_ORDINAL_FEM, _rep_ordinal_fem, texto)
    texto = _sub(_RE_ABREVIATURA, _rep_abreviatura, texto)
    texto = _RE_AMPERSAND.sub(" y ", texto)
    texto = _RE_MAS_ENTRE_CIFRAS.sub(" más ", texto)
    texto = _RE_MAS_SUELTO.sub("más", texto)
    texto = _sub(_RE_MULTIPLICADOR, _rep_multiplicador, texto)
    texto = _sub(_RE_RANGO, _rep_rango, texto)
    # Después del rango: "de 8-10 soles" debe leerse "de ocho a diez soles".
    texto = _sub(_RE_MONEDA_PALABRA, _rep_moneda_palabra, texto)
    # Antes de los cardinales: un número de contacto no es una cantidad.
    texto = _sub(_RE_SERIE_CONTACTO, _rep_serie_contacto, texto)
    texto = _sub(_RE_NUMERO, _rep_numero, texto)

    return _limpiar_espacios(texto)


def normalize_spanish(text: str) -> str:
    """Convierte cifras, horas, fechas y abreviaturas a palabras pronunciables.

    Nunca lanza excepción: si algo falla devuelve el texto original, porque un
    problema de normalización jamás debe impedir generar el audio.
    """
    if not isinstance(text, str):
        return ""
    if not text:
        return text
    try:
        return _pipeline(text)
    except Exception:
        return text
