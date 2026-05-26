from sqlalchemy.orm import Session

from app.database import Usuario


class UsuarioRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int, empresa_id: int) -> Usuario | None:
        return self.db.query(Usuario).filter(
            Usuario.id == user_id,
            Usuario.empresa_id == empresa_id,
        ).first()

    def get_by_username(self, username: str, empresa_id: int) -> Usuario | None:
        return self.db.query(Usuario).filter(
            Usuario.empresa_id == empresa_id,
            Usuario.username == username,
        ).first()

    def list_by_empresa(self, empresa_id: int):
        return self.db.query(Usuario).filter(
            Usuario.empresa_id == empresa_id,
        ).order_by(Usuario.creado.desc()).all()

    def add(self, usuario: Usuario) -> Usuario:
        self.db.add(usuario)
        return usuario
