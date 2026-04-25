# -*- coding: utf-8 -*-
"""
Usuarios router — El admin gestiona cuentas de cobradores
"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, Usuario, Zona
from app.auth import require_login, get_current_empresa, hash_password, require_admin

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def listar_usuarios(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
    empresa_id: int = Depends(get_current_empresa),
):
    usuarios = db.query(Usuario).filter(
        Usuario.empresa_id == empresa_id,
        Usuario.activo == True
    ).all()
    zonas = db.query(Zona).filter(Zona.empresa_id == empresa_id, Zona.activa == True).all()

    return templates.TemplateResponse("usuarios.html", {
        "request": request,
        "usuarios": usuarios,
        "zonas": zonas,
        "current_user": current_user,
        "page": "usuarios"
    })


@router.post("/nuevo")
async def crear_usuario(
    username: str = Form(...),
    nombre_completo: str = Form(...),
    password: str = Form(...),
    rol: str = Form("cobrador"),
    zona_id: int = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
    empresa_id: int = Depends(get_current_empresa),
):
    if len(password) < 6:
        return JSONResponse({"error": "La contraseña debe tener al menos 6 caracteres"}, status_code=400)

    username = username.strip().lower()
    if db.query(Usuario).filter(Usuario.username == username).first():
        return JSONResponse({"error": f"El usuario '{username}' ya existe"}, status_code=400)

    usuario = Usuario(
        empresa_id=empresa_id,
        username=username,
        nombre_completo=nombre_completo.strip(),
        password_hash=hash_password(password),
        rol=rol,
        zona_id=zona_id or None,
    )
    db.add(usuario)
    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Usuario creado exitosamente"})


@router.post("/{usuario_id}/editar")
async def editar_usuario(
    usuario_id: int,
    nombre_completo: str = Form(...),
    rol: str = Form("cobrador"),
    zona_id: int = Form(None),
    nueva_password: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
    empresa_id: int = Depends(get_current_empresa),
):
    usuario = db.query(Usuario).filter(
        Usuario.id == usuario_id,
        Usuario.empresa_id == empresa_id
    ).first()
    if not usuario:
        return JSONResponse({"error": "Usuario no encontrado"}, status_code=404)

    usuario.nombre_completo = nombre_completo.strip()
    usuario.rol = rol
    usuario.zona_id = zona_id or None

    if nueva_password and len(nueva_password) >= 6:
        usuario.password_hash = hash_password(nueva_password)

    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Usuario actualizado"})


@router.delete("/{usuario_id}")
async def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
    empresa_id: int = Depends(get_current_empresa),
):
    usuario = db.query(Usuario).filter(
        Usuario.id == usuario_id,
        Usuario.empresa_id == empresa_id
    ).first()
    if not usuario:
        return JSONResponse({"error": "No encontrado"}, status_code=404)
    if usuario.id == current_user.id:
        return JSONResponse({"error": "No puedes eliminarte a ti mismo"}, status_code=400)

    usuario.activo = False
    db.commit()
    return JSONResponse({"ok": True})
