import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from fastapi import Cookie, Depends, HTTPException

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from db import _req_supabase, usar_supabase

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_AUTH_KEY = (
    os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
)
COOKIE_NAME = "autopark_session"

PERMISSOES_PADRAO = {
    "admin": {
        "overview": True,
        "vehicles": True,
        "camera": True,
        "spots": True,
        "tickets": True,
        "payments": True,
        "reports": True,
        "settings": True,
    },
    "funcionario": {
        "overview": True,
        "vehicles": True,
        "camera": True,
        "spots": True,
        "tickets": True,
        "payments": True,
        "reports": False,
        "settings": False,
    },
}


def _req_auth(metodo: str, caminho: str, payload: dict | None = None, token: str | None = None) -> dict:
    if not usar_supabase() or not SUPABASE_AUTH_KEY:
        raise HTTPException(status_code=503, detail="Supabase Auth não configurado no backend.")

    url = f"{SUPABASE_URL}/auth/v1/{caminho}"
    headers = {
        "apikey": SUPABASE_AUTH_KEY,
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    dados = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=dados, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            corpo = resp.read().decode("utf-8")
            return json.loads(corpo) if corpo else {}
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", errors="ignore")
        try:
            msg = json.loads(detalhe).get("error_description") or json.loads(detalhe).get("msg") or detalhe
        except ValueError:
            msg = detalhe
        raise HTTPException(status_code=401 if e.code in (400, 401) else e.code, detail=msg) from e


def autenticar_supabase(email: str, password: str) -> dict:
    sessao = _req_auth("POST", "token?grant_type=password", {"email": email, "password": password})
    access_token = sessao.get("access_token")
    user_data = sessao.get("user") or {}
    if not access_token or not user_data.get("id"):
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")

    perfil = buscar_ou_criar_perfil(user_data["id"], user_data.get("email", email))
    if not perfil.get("ativo", True):
        raise HTTPException(status_code=403, detail="Usuário desativado pelo administrador.")

    return {"access_token": access_token, "usuario": perfil}


def encerrar_sessao_supabase(token: str | None):
    if not token:
        return
    try:
        _req_auth("POST", "logout", token=token)
    except HTTPException:
        pass


def buscar_ou_criar_perfil(user_id: str, email: str) -> dict:
    rows = _req_supabase("GET", f"perfis_usuarios?id=eq.{user_id}&select=*")
    if rows:
        return rows[0]

    nome_padrao = email.split("@")[0] if "@" in email else email
    criado = _req_supabase(
        "POST",
        "perfis_usuarios",
        {
            "id": user_id,
            "email": email,
            "nome": nome_padrao,
            "papel": "funcionario",
            "ativo": True,
            "permissoes": PERMISSOES_PADRAO["funcionario"],
        },
    )
    return criado[0]


def obter_usuario_atual(autopark_session: str | None = Cookie(default=None)) -> dict:
    if not autopark_session:
        raise HTTPException(status_code=401, detail="Sessão não autenticada.")

    user_data = _req_auth("GET", "user", token=autopark_session)
    user_id = user_data.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    perfil = buscar_ou_criar_perfil(user_id, user_data.get("email", ""))
    if not perfil.get("ativo", True):
        raise HTTPException(status_code=403, detail="Usuário desativado.")
    return perfil


def exigir_permissao(modulo: str):
    def _verificar(usuario: dict = Depends(obter_usuario_atual)) -> dict:
        if usuario.get("papel") == "admin":
            return usuario
        permissoes = usuario.get("permissoes") or {}
        if not permissoes.get(modulo, False):
            raise HTTPException(status_code=403, detail=f"Sem permissão para acessar o módulo '{modulo}'.")
        return usuario
    return _verificar


def exigir_admin(usuario: dict = Depends(obter_usuario_atual)) -> dict:
    if usuario.get("papel") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")
    return usuario


def listar_perfis() -> list[dict]:
    return _req_supabase("GET", "perfis_usuarios?select=id,email,nome,papel,ativo,permissoes&order=criado_em.asc")


def atualizar_perfil(user_id: str, papel: str, ativo: bool, permissoes: dict) -> dict:
    if papel not in ("admin", "funcionario"):
        raise HTTPException(status_code=400, detail="Papel inválido.")
    atualizado = _req_supabase(
        "PATCH",
        f"perfis_usuarios?id=eq.{user_id}",
        {"papel": papel, "ativo": ativo, "permissoes": permissoes},
    )
    if not atualizado:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return atualizado[0]
