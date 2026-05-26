"""Simulaciones financieras deterministicas para CreditosPro.

Ejecutar:
    python simulacion_financiera.py
"""
import datetime
import os
import random
import sys
from decimal import Decimal


os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "simulation-secret-key")
os.environ.setdefault("SESSION_SECRET_KEY", "simulation-session-secret-key")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("AUTO_CREATE_TABLES", "0")

from app.services.prestamo_service import calcular_cuotas  # noqa: E402


def simular_prestamos(iteraciones: int = 5000) -> list[str]:
    rng = random.Random(20260524)
    fecha = datetime.date(2026, 1, 1)
    errores = []

    for i in range(iteraciones):
        capital = rng.randint(50_000, 50_000_000)
        tasa = Decimal(rng.randint(0, 8000)) / Decimal("100")
        cuotas = rng.randint(1, 365)
        plazo = rng.randint(1, 90)

        resultado = calcular_cuotas(capital, tasa, cuotas, fecha, plazo)
        total_cuotas = sum(c["valor"] for c in resultado["cuotas"])

        if total_cuotas != resultado["total_pagar"]:
            errores.append(
                f"#{i}: suma cuotas {total_cuotas} != total {resultado['total_pagar']} "
                f"(capital={capital}, tasa={tasa}, cuotas={cuotas}, plazo={plazo})"
            )
        if len(resultado["cuotas"]) != cuotas:
            errores.append(f"#{i}: cantidad de cuotas incorrecta")
        if any(c["valor"] <= Decimal("0.00") for c in resultado["cuotas"]):
            errores.append(f"#{i}: cuota con valor no positivo")

    return errores


def main() -> int:
    iteraciones = int(os.getenv("SIMULACIONES", "5000"))
    errores = simular_prestamos(iteraciones)
    if errores:
        print(f"Simulacion financiera: FALLARON {len(errores)} casos de {iteraciones}")
        for error in errores[:20]:
            print(f"- {error}")
        if len(errores) > 20:
            print(f"... {len(errores) - 20} errores mas")
        return 1

    print(f"Simulacion financiera OK: {iteraciones} prestamos simulados sin descuadres.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
