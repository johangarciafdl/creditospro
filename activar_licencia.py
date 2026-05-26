#!/usr/bin/env python3
"""
Script para activar licencia directamente en .env
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LICENSE_KEY = "CPRO-Z0FBQUFBQnFEMkQ0Sk0xV2hUc2RwNnNENFAyRGFydWNwS1hRQ0VYckl3ZmE2SlNKd2R2WmdIZDJVTVF1dWRqcE1CclJXQnFoQjdTdk1hTl9xem9Sd2lrTlBncndPSDliQVpkNGthTVNiTG14VmJhLWZpcTV2dFhEVUxjTWpKQ3lEVUpWS1RQejFQZHlEejBfSy1lZ015NzJRWlJBX3JIS2Z2YUR0X0FXT0JYZ0ktS1AxSzhtTmx5RWdvSnlkZVAxZzNPVUdra1VsdXcyOUkxWEllUGh6QnhRaUlwaERaX2hJNUI4QjVCWVUyRnFUVWpRX3g0LUQwVmRLNDJOeDZtVHFjUUpQT29UeWlvMnNWUVNXVXowME9qTjRKQW5jeEpwakliclp3NmFNb2JJc0dlalpFZWZ2T2ktNjRpTGJWeEJkRVVrLTNHdEh2cWZKcGZ5cU9TOEt5V3cyNVJIWldDOExnPT0="

def activar_licencia():
    """Activa la licencia en .env"""
    env_file = Path(__file__).parent / ".env"
    
    try:
        # Leer contenido actual
        content = env_file.read_text(encoding='utf-8')
        
        # Si ya existe LICENSE_KEY, reemplazar; si no, agregar
        if "LICENSE_KEY=" in content:
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.startswith("LICENSE_KEY="):
                    lines[i] = f"LICENSE_KEY={LICENSE_KEY}"
            content = '\n'.join(lines)
        else:
            content += f"\n\n# Licencia activada\nLICENSE_KEY={LICENSE_KEY}\n"
        
        # Guardar
        env_file.write_text(content, encoding='utf-8')
        
        print("\n" + "="*70)
        print("✅ LICENCIA ACTIVADA EXITOSAMENTE")
        print("="*70)
        print(f"\nMachine ID: 90D10A0E0EED699650502BDB767CF18F")
        print(f"Empresa: ElRuso")
        print(f"\nLicencia guardada en: .env")
        print("\n⚠️  Reinicia el servidor para que surta efecto\n")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    print("\n" + "="*70)
    print("SCRIPT: CreditosPro - Activar Licencia")
    print("="*70)
    activar_licencia()
