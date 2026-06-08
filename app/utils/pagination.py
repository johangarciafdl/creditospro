"""
Paginacion para endpoints de listado.

Uso en un router:
    from app.utils.pagination import Paginacion, paginar_query

    @router.get("/clientes")
    async def listar_clientes(request: Request, page: int = 1, page_size: int = 25, ...):
        ...
        q = db.query(Cliente).filter(...)
        resultado = paginar_query(q, page, page_size)
        return JSONResponse({
            "items": resultado["items"],
            "total": resultado["total"],
            "page": resultado["page"],
            "page_size": resultado["page_size"],
            "pages": resultado["pages"],
        })

El parametro `max_page_size` previene que un cliente pida 1M de filas.
"""
from typing import Any
from sqlalchemy.orm import Query

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


class Paginacion:
    """Validador de parametros de paginacion."""

    def __init__(self, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE,
                 max_page_size: int = MAX_PAGE_SIZE):
        self.page = max(1, int(page or 1))
        self.page_size = max(1, min(int(page_size or DEFAULT_PAGE_SIZE), max_page_size))
        self.offset = (self.page - 1) * self.page_size
        self.limit = self.page_size

    def __repr__(self):
        return f"Paginacion(page={self.page}, page_size={self.page_size})"


def paginar_query(query: Query, paginacion: Paginacion | None = None,
                  page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
    """Aplica LIMIT/OFFSET a una query y devuelve items + metadata."""
    pag = paginacion or Paginacion(page, page_size)
    total = query.count()
    items = query.offset(pag.offset).limit(pag.limit).all()
    pages = (total + pag.page_size - 1) // pag.page_size if total else 0
    return {
        "items": items,
        "total": total,
        "page": pag.page,
        "page_size": pag.page_size,
        "pages": pages,
        "has_next": pag.page < pages,
        "has_prev": pag.page > 1,
    }
