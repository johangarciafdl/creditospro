"""CreditosPro v2.0 - Router de Autenticación"""
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import datetime

from app.database import get_db, Usuario, Zona
from app.auth import (authenticate_user, create_access_token, hash_password,
                      require_login, require_admin, get_current_user)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login")
async def login_page(request: Request, next: str = "/", error: str = ""):
    return templates.TemplateResponse("login.html", {
        "request": request, "next": next, "error": error,
    })


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...), password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db)
):
    user = authenticate_user(username.strip(), password, db)
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request, "next": next,
            "error": "Usuario o contraseña incorrectos",
            "username": username,
        }, status_code=401)

    user.ultimo_login = datetime.datetime.now()
    db.commit()

    token = create_access_token({"sub": user.username, "rol": user.rol})
    response = RedirectResponse(url=next or "/dashboard", status_code=303)
    response.set_cookie(
        key="access_token", value=f"Bearer {token}",
        httponly=True, max_age=60 * 60 * 8, samesite="lax",
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie("access_token")
    return response


@router.get("/usuarios")
async def listar_usuarios(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    usuarios = db.query(Usuario).order_by(Usuario.creado.desc()).all()
    zonas = db.query(Zona).all()
    return templates.TemplateResponse("usuarios.html", {
        "request": request, "page": "usuarios",
        "usuarios": usuarios, "zonas": zonas,
        "current_user": current_user,
    })


@router.post("/usuarios/nuevo")
async def crear_usuario(
    username: str = Form(...), nombre_completo: str = Form(...),
    email: str = Form(""), password: str = Form(...),
    rol: str = Form("cobrador"), zona_id: int = Form(None),
    db: Session = Depends(get_db), current_user: Usuario = Depends(require_admin)
):
    if len(password) < 6:
        return JSONResponse({"error": "La contraseña debe tener al menos 6 caracteres"}, status_code=400)
    if db.query(Usuario).filter(Usuario.username == username.strip().lower()).first():
        return JSONResponse({"error": f"El usuario '{username}' ya existe"}, status_code=400)

    initials = "".join(w[0].upper() for w in nombre_completo.split()[:2])
    user = Usuario(
        username=username.strip().lower(),
        nombre_completo=nombre_completo,
        email=email or None,
        password_hash=hash_password(password),
        rol=rol,
        zona_id=zona_id or None,
        avatar_initials=initials,
    )
    db.add(user)
    db.commit()
    return JSONResponse({"ok": True, "mensaje": f"Usuario '{username}' creado exitosamente"})


@router.post("/usuarios/{user_id}/editar")
async def editar_usuario(
    user_id: int,
    nombre_completo: str = Form(...), email: str = Form(""),
    rol: str = Form("cobrador"), zona_id: int = Form(None),
    nueva_password: str = Form(""), activo: str = Form("on"),
    db: Session = Depends(get_db), current_user: Usuario = Depends(require_admin)
):
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404)
    if user_id == current_user.id and rol != current_user.rol:
        return JSONResponse({"error": "No puedes cambiar tu propio rol"}, status_code=400)

    user.nombre_completo = nombre_completo
    user.email = email or None
    user.rol = rol
    user.zona_id = zona_id or None
    user.activo = (activo == "on")
    if nueva_password and len(nueva_password) >= 6:
        user.password_hash = hash_password(nueva_password)
    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Usuario actualizado correctamente"})


@router.delete("/usuarios/{user_id}")
async def eliminar_usuario(user_id: int, db: Session = Depends(get_db), current_user: Usuario = Depends(require_admin)):
    if user_id == current_user.id:
        return JSONResponse({"error": "No puedes desactivar tu propia cuenta"}, status_code=400)
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404)
    user.activo = False
    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Usuario desactivado"})


@router.get("/perfil")
async def perfil(request: Request, db: Session = Depends(get_db), current_user: Usuario = Depends(require_login)):
    return templates.TemplateResponse("perfil.html", {
        "request": request, "page": "perfil", "current_user": current_user,
    })


@router.post("/perfil/cambiar-password")
async def cambiar_password(
    password_actual: str = Form(...), password_nuevo: str = Form(...),
    db: Session = Depends(get_db), current_user: Usuario = Depends(require_login)
):
    from app.auth import verify_password
    if not verify_password(password_actual, current_user.password_hash):
        return JSONResponse({"error": "Contraseña actual incorrecta"}, status_code=400)
    if len(password_nuevo) < 6:
        return JSONResponse({"error": "La nueva contraseña debe tener al menos 6 caracteres"}, status_code=400)
    current_user.password_hash = hash_password(password_nuevo)
    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Contraseña cambiada exitosamente"})


@router.get("/debug-hash")
async def debug_hash(password: str = "admin123"):
    """Endpoint temporal para generar hash en el servidor"""
    import bcrypt
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    verificado = bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    return {
        "password": password,
        "hash": hashed,
        "verificacion_ok": verificado
    }
