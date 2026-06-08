# 🚀 CreditosPro ElRuso — Configuración Inicial

## PASO 1: Configurar la BD (una sola vez)

En PowerShell, dentro de la carpeta de CreditosPro_v2:

```powershell
cd C:\Users\johan\Downloads\CreditosPro_FINAL\CreditosPro_v2_seguro_base\CreditosPro_v2

python setup_empresa_elruso.py
```

**Esto hace:**
- ✅ Crea/actualiza la empresa **ElRuso**
- ✅ Crea usuario **johan** (admin/owner)
- ✅ Crea usuario **julian** (gerente)
- ✅ Crea usuario **marcos** (cobrador)
- ✅ Desactiva usuarios/empresas antiguas

**Resultado esperado:**
```
✅ SETUP COMPLETADO EXITOSAMENTE

DATOS DE ACCESO PARA TODOS LOS USUARIOS:

📋 ADMIN/OWNER:
   Usuario:     johan
   Contraseña:  XXXXXX
   Rol:         admin (acceso total)

👔 GERENTE:
   Usuario:     julian
   Contraseña:  197991
   Rol:         gerente (todas las funciones)

🚗 COBRADOR:
   Usuario:     marcos
   Contraseña:  Marcos123
   Rol:         cobrador (registrar cobros)
```

---

## PASO 2: Ejecutar el programa

```powershell
python run.py
```

✅ Se abre Chrome automáticamente

**Login con cualquiera de los usuarios:**
- johan / XXXXXX (acceso total)
- julian / 197991 (gerente - todas las funciones)
- marcos / Marcos123 (cobrador - registro de cobros)

---

## PASO 3: Crear acceso directo en escritorio

```powershell
crear_acceso_directo.bat
```

Doble clic en `Iniciar CreditosPro.bat` del escritorio cada vez.

---

## PASO 4: Pasar a otro PC

1. Copia la carpeta completa `CreditosPro_v2_seguro_base\CreditosPro_v2` al otro PC por USB
2. En el otro PC, ejecuta:
   ```powershell
   python setup_empresa_elruso.py
   python run.py
   ```
3. Login con cualquiera de los 3 usuarios

---

## Para Cobradores en Celular

El cobrador abre Chrome en su celular:
1. Va a: `http://IP_DEL_PC_ADMIN:8000` (ejemplo: `http://192.168.1.50:8000`)
2. Chrome sugiere "Agregar a pantalla de inicio"
3. Se instala como app nativa

**Login en celular:** marcos / Marcos123

---

## Cambiar Contraseña de Usuarios

1. Abre el programa con `python run.py`
2. Login con cualquier usuario
3. En el dashboard, busca "Perfil" o "Configuración"
4. Cambia la contraseña

---

## ¿Qué pasa con los datos antiguos?

- La empresa "creditos" se desactiva (no se pierde)
- Solo funciona ElRuso
- Todos los usuarios acceden a ElRuso

---

**Versión:** CreditosPro v2.1  
**Empresa:** ElRuso (ID: 1)  
**Usuarios Admin:** johan / julian / marcos  
**Última actualización:** 25 de mayo de 2026
