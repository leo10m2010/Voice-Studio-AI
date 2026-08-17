from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from text_normalize import normalize_spanish, numero_a_palabras


class CardinalTests(unittest.TestCase):
    def test_cifras_basicas(self):
        casos = {
            "0": "cero",
            "1": "uno",
            "7": "siete",
            "15": "quince",
            "16": "dieciséis",
            "20": "veinte",
            "21": "veintiuno",
            "22": "veintidós",
            "26": "veintiséis",
            "30": "treinta",
            "31": "treinta y uno",
            "45": "cuarenta y cinco",
            "99": "noventa y nueve",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalize_spanish(entrada), esperado)

    def test_centenas_irregulares(self):
        casos = {
            "100": "cien",
            "101": "ciento uno",
            "150": "ciento cincuenta",
            "200": "doscientos",
            "500": "quinientos",
            "700": "setecientos",
            "900": "novecientos",
            "999": "novecientos noventa y nueve",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalize_spanish(entrada), esperado)

    def test_miles_y_millones(self):
        casos = {
            "1000": "mil",
            "1250": "mil doscientos cincuenta",
            "2000": "dos mil",
            "21000": "veintiún mil",
            "31000": "treinta y un mil",
            "100000": "cien mil",
            "1000000": "un millón",
            "2000000": "dos millones",
            "21000000": "veintiún millones",
            "999999999": (
                "novecientos noventa y nueve millones "
                "novecientos noventa y nueve mil "
                "novecientos noventa y nueve"
            ),
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalize_spanish(entrada), esperado)

    def test_separadores_de_miles(self):
        self.assertEqual(normalize_spanish("1.250"), "mil doscientos cincuenta")
        self.assertEqual(normalize_spanish("1,250"), "mil doscientos cincuenta")
        self.assertEqual(normalize_spanish("1.000.000"), "un millón")
        self.assertEqual(normalize_spanish("1,000,000"), "un millón")

    def test_fuera_de_rango_queda_intacto(self):
        self.assertEqual(normalize_spanish("1234567890"), "1234567890")
        self.assertIsNone(numero_a_palabras(1_000_000_000))
        self.assertIsNone(numero_a_palabras(-3))

    def test_apocope_y_femenino_en_el_ayudante(self):
        self.assertEqual(numero_a_palabras(21, apocope=True), "veintiún")
        self.assertEqual(numero_a_palabras(21, femenino=True), "veintiuna")
        self.assertEqual(numero_a_palabras(1, femenino=True), "una")
        self.assertEqual(numero_a_palabras(101, apocope=True), "ciento un")

    def test_codigos_con_ceros_a_la_izquierda(self):
        self.assertEqual(normalize_spanish("007"), "cero cero siete")
        self.assertEqual(normalize_spanish("08 de agosto"), "ocho de agosto")


class DecimalTests(unittest.TestCase):
    def test_coma_y_punto(self):
        self.assertEqual(normalize_spanish("25.50"), "veinticinco con cincuenta")
        self.assertEqual(normalize_spanish("3,5"), "tres con cinco")
        self.assertEqual(normalize_spanish("0.75"), "cero con setenta y cinco")

    def test_decimales_nulos_se_omiten(self):
        self.assertEqual(normalize_spanish("25.00"), "veinticinco")

    def test_decimal_con_cero_a_la_izquierda(self):
        self.assertEqual(normalize_spanish("25.05"), "veinticinco con cero cinco")


class MonedaTests(unittest.TestCase):
    def test_soles_con_simbolo(self):
        casos = {
            "S/ 25.50": "veinticinco soles con cincuenta céntimos",
            "S/25.50": "veinticinco soles con cincuenta céntimos",
            "S/. 25.50": "veinticinco soles con cincuenta céntimos",
            "S/ 1": "un sol",
            "S/ 21": "veintiún soles",
            "S/ 100.00": "cien soles",
            "S/ 1,250.50": "mil doscientos cincuenta soles con cincuenta céntimos",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalize_spanish(entrada), esperado)

    def test_solo_centimos(self):
        self.assertEqual(normalize_spanish("S/ 0.50"), "cincuenta céntimos")
        self.assertEqual(normalize_spanish("S/ 0.01"), "un céntimo")

    def test_dolares(self):
        self.assertEqual(normalize_spanish("$ 20"), "veinte dólares")
        self.assertEqual(normalize_spanish("$1"), "un dólar")
        self.assertEqual(normalize_spanish("US$ 20"), "veinte dólares")

    def test_moneda_escrita_con_letras_lleva_apocope(self):
        self.assertEqual(normalize_spanish("21 soles"), "veintiún soles")
        self.assertEqual(normalize_spanish("31 soles"), "treinta y un soles")
        self.assertEqual(normalize_spanish("25 soles"), "veinticinco soles")
        self.assertEqual(normalize_spanish("20 dólares"), "veinte dólares")


class HoraTests(unittest.TestCase):
    def test_con_meridiano(self):
        casos = {
            "3:30 pm": "tres y media de la tarde",
            "9:00 am": "nueve de la mañana",
            "1:15 pm": "una y cuarto de la tarde",
            "8:00 pm": "ocho de la noche",
            "2:20 am": "dos y veinte de la madrugada",
            "12:00 pm": "doce del mediodía",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalize_spanish(entrada), esperado)

    def test_meridiano_con_puntos_conserva_el_punto_final(self):
        self.assertEqual(normalize_spanish("9:00 a.m."), "nueve de la mañana.")

    def test_formato_24_horas_deduce_la_franja(self):
        self.assertEqual(
            normalize_spanish("14:45"), "dos y cuarenta y cinco de la tarde"
        )
        self.assertEqual(normalize_spanish("20:00"), "ocho de la noche")

    def test_sin_meridiano_no_inventa_franja(self):
        # "8:30" tanto puede ser mañana como noche: mejor no adivinar.
        self.assertEqual(normalize_spanish("8:30"), "ocho y media")


class FechaTests(unittest.TestCase):
    def test_fecha_completa(self):
        self.assertEqual(
            normalize_spanish("15/08/2026"),
            "quince de agosto de dos mil veintiséis",
        )
        self.assertEqual(
            normalize_spanish("15-08-2026"),
            "quince de agosto de dos mil veintiséis",
        )

    def test_dia_uno_es_primero(self):
        self.assertEqual(
            normalize_spanish("1/01/2026"),
            "primero de enero de dos mil veintiséis",
        )

    def test_fecha_sin_anio(self):
        self.assertEqual(normalize_spanish("15/08"), "quince de agosto")

    def test_fecha_imposible_no_se_interpreta_como_fecha(self):
        resultado = normalize_spanish("32/13/2026")
        self.assertNotIn("de agosto", resultado)
        self.assertIn("/", resultado)


class PorcentajeTests(unittest.TestCase):
    def test_porcentajes(self):
        self.assertEqual(normalize_spanish("50%"), "cincuenta por ciento")
        self.assertEqual(normalize_spanish("100%"), "cien por ciento")
        self.assertEqual(normalize_spanish("2.5%"), "dos con cinco por ciento")
        self.assertEqual(normalize_spanish("50 %"), "cincuenta por ciento")


class OrdinalTests(unittest.TestCase):
    def test_indicador_ordinal(self):
        self.assertEqual(normalize_spanish("1°"), "primero")
        self.assertEqual(normalize_spanish("2°"), "segundo")
        self.assertEqual(normalize_spanish("3°"), "tercero")

    def test_sufijos_escritos(self):
        casos = {
            "1er": "primer",
            "1ra": "primera",
            "2do": "segundo",
            "2da": "segunda",
            "3er": "tercer",
            "8vo": "octavo",
            "10ma": "décima",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalize_spanish(entrada), esperado)

    def test_ordinal_dentro_de_una_frase(self):
        self.assertEqual(
            normalize_spanish("El 1er piso y el 2do piso"),
            "El primer piso y el segundo piso",
        )


class AbreviaturaTests(unittest.TestCase):
    def test_abreviaturas_comunes(self):
        casos = {
            "Av. Grau 1250": "avenida Grau mil doscientos cincuenta",
            "Jr. Lima": "jirón Lima",
            "Dr. Pérez": "doctor Pérez",
            "Dra. Rojas": "doctora Rojas",
            "Sr. Torres": "señor Torres",
            "Sra. Vega": "señora Vega",
            "N° 45": "número cuarenta y cinco",
            "Nro. 45": "número cuarenta y cinco",
            "etc.": "etcétera",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(normalize_spanish(entrada), esperado)

    def test_abreviatura_pegada_a_la_palabra_siguiente(self):
        self.assertEqual(normalize_spanish("Dr.Pérez"), "doctor Pérez")


class SimboloTests(unittest.TestCase):
    def test_ampersand_y_mas(self):
        self.assertEqual(normalize_spanish("Ron & Cola"), "Ron y Cola")
        self.assertEqual(normalize_spanish("2 + 2"), "dos más dos")
        self.assertEqual(normalize_spanish("2+2"), "dos más dos")

    def test_grados(self):
        self.assertEqual(normalize_spanish("25 °C"), "veinticinco grados")
        self.assertEqual(normalize_spanish("25°C"), "veinticinco grados")
        self.assertEqual(normalize_spanish("1 °C"), "un grado")


class RangoYMultiplicadorTests(unittest.TestCase):
    def test_multiplicador(self):
        self.assertEqual(normalize_spanish("2x1"), "dos por uno")
        self.assertEqual(normalize_spanish("2 x 1"), "dos por uno")
        self.assertEqual(normalize_spanish("3x2"), "tres por dos")

    def test_rango(self):
        self.assertEqual(normalize_spanish("8-10"), "ocho a diez")
        self.assertEqual(
            normalize_spanish("de 8-10 soles"), "de ocho a diez soles"
        )

    def test_telefono_no_se_lee_como_rango(self):
        resultado = normalize_spanish("555-1234")
        self.assertNotIn(" a ", resultado)
        self.assertIn("-", resultado)


class TextoCompletoTests(unittest.TestCase):
    def test_spot_publicitario(self):
        entrada = (
            "¡Solo hoy! S/ 9.90 en pollo a la brasa, 2x1 hasta el 15/08/2026 "
            "a las 6:30 pm en Av. Arequipa 1250. Dr. Rojas & Asociados, 50% "
            "de descuento, etc."
        )
        esperado = (
            "¡Solo hoy! nueve soles con noventa céntimos en pollo a la brasa, "
            "dos por uno hasta el quince de agosto de dos mil veintiséis "
            "a las seis y media de la tarde en avenida Arequipa mil doscientos "
            "cincuenta. doctor Rojas y Asociados, cincuenta por ciento "
            "de descuento, etcétera"
        )
        self.assertEqual(normalize_spanish(entrada), esperado)

    def test_texto_sin_cifras_queda_intacto(self):
        entrada = "¿Quieres ganar? ¡Ven a la tienda y llévate tu premio!"
        self.assertEqual(normalize_spanish(entrada), entrada)

    def test_conserva_mayusculas_y_signos(self):
        entrada = "PROMOCIÓN: ¿50% DE DESCUENTO?"
        self.assertEqual(
            normalize_spanish(entrada),
            "PROMOCIÓN: ¿cincuenta por ciento DE DESCUENTO?",
        )

    def test_conserva_los_saltos_de_linea(self):
        self.assertEqual(
            normalize_spanish("Línea 1\nLínea 2"),
            "Línea uno\nLínea dos",
        )


class IdempotenciaTests(unittest.TestCase):
    def test_normalizar_dos_veces_da_lo_mismo(self):
        entradas = [
            "S/ 25.50 el 15/08/2026 a las 3:30 pm",
            "2x1 con 50% de descuento en Av. Grau 1250",
            "N° 45, Dr. Pérez, 8-10 soles, 25 °C, etc.",
            "1er piso, 2da puerta, US$ 20, Ron & Cola",
            "Sin cifras de ningún tipo.",
        ]
        for entrada in entradas:
            with self.subTest(entrada=entrada):
                una = normalize_spanish(entrada)
                dos = normalize_spanish(una)
                self.assertEqual(una, dos)


class EntradasRarasTests(unittest.TestCase):
    def test_entradas_degeneradas_no_revientan(self):
        entradas = [
            "", "   ", "\n", "!!!", "¿¡?", "%%%", "///", "&&&", "---",
            "S/", "$", "°", "::::", "1:99", "99:99", "0/0/0", ".", ",",
            "1.2.3.4", "v1.2.3", "12:30:45", "+", "x", "-",
        ]
        for entrada in entradas:
            with self.subTest(entrada=entrada):
                resultado = normalize_spanish(entrada)
                self.assertIsInstance(resultado, str)

    def test_entrada_que_no_es_texto(self):
        self.assertEqual(normalize_spanish(None), "")
        self.assertEqual(normalize_spanish(1250), "")

    def test_cadena_vacia(self):
        self.assertEqual(normalize_spanish(""), "")


if __name__ == "__main__":
    unittest.main()


class SeriesDeDigitosTest(unittest.TestCase):
    """
    Teléfonos, DNI y números de cuenta. Leerlos como cardinal producía
    "novecientos ochenta y siete millones…" para un celular, inservible en un
    spot de radio.
    """

    def test_celular_peruano_se_lee_digito_a_digito(self):
        self.assertEqual(
            normalize_spanish("Llama al 987654321"),
            "Llama al nueve ocho siete seis cinco cuatro tres dos uno",
        )

    def test_dni_de_ocho_digitos(self):
        self.assertIn("cuatro cuatro", normalize_spanish("DNI 44556677"))

    def test_cantidades_normales_siguen_siendo_cardinales(self):
        self.assertIn("mil doscientos cincuenta", normalize_spanish("Av. Grau 1250"))
        self.assertIn("dos mil veintiséis", normalize_spanish("año 2026"))

    def test_precio_de_seis_digitos_sigue_siendo_cantidad(self):
        self.assertIn("cien mil", normalize_spanish("premio de 100000"))

    def test_una_cifra_grande_sin_contexto_sigue_siendo_cantidad(self):
        # La longitud sola no distingue: 1000000 también tiene siete dígitos.
        self.assertEqual(normalize_spanish("1000000"), "un millón")
        self.assertIn("millones", normalize_spanish("ganó 2000000 de soles"))

    def test_es_idempotente(self):
        una = normalize_spanish("Llama al 987654321")
        self.assertEqual(normalize_spanish(una), una)

    def test_celular_con_grupos_y_dos_puntos(self):
        self.assertEqual(
            normalize_spanish("Celular: 987 654 321"),
            "Celular: nueve ocho siete seis cinco cuatro tres dos uno",
        )

    def test_telefono_con_guion_y_punto_final(self):
        salida = normalize_spanish("Teléfono 062-513200.")
        self.assertIn("cero seis dos cinco uno tres dos cero cero", salida)
        self.assertTrue(salida.endswith("."))

    def test_palabra_clave_seguida_de_cantidad_no_se_deletrea(self):
        self.assertIn("quinientos soles", normalize_spanish("Llama y gana 500 soles"))
