"""
RemoteLab - Módulo de Protocolo Compartilhado
==============================================
Define o protocolo de comunicação entre Agent e Controller.
Ambas as aplicações importam este módulo para garantir
compatibilidade de mensagens.

Protocolo: JSON delimitado por newline (\n) sobre TCP.
Cada mensagem é um objeto JSON em uma única linha.

Uso acadêmico/educacional - Ambiente de laboratório controlado.
"""

import json
import socket
import time
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional, Any


# ---------------------------------------------------------------------------
# Tipos de Comando (Controller -> Agent)
# ---------------------------------------------------------------------------
class CommandType(str, Enum):
    """Comandos que o Controller pode enviar ao Agent."""
    SYSINFO    = "sysinfo"     # Solicita informações do sistema
    PING       = "ping"        # Verifica se o agente está vivo
    LISTDIR    = "listdir"     # Lista diretório (caminho como argumento)
    GETENV     = "getenv"      # Retorna variáveis de ambiente
    WHOAMI     = "whoami"      # Usuário atual
    NETSTAT    = "netstat"     # Conexões de rede ativas
    DISCONNECT = "disconnect"  # Solicita desconexão limpa
    # Extensível: adicione novos comandos aqui


# ---------------------------------------------------------------------------
# Tipos de Resposta (Agent -> Controller)
# ---------------------------------------------------------------------------
class ResponseStatus(str, Enum):
    """Status de uma resposta do Agent."""
    OK    = "ok"     # Comando executado com sucesso
    ERROR = "error"  # Falha na execução
    INFO  = "info"   # Mensagem informativa (ex: heartbeat)


# ---------------------------------------------------------------------------
# Estruturas de Mensagem
# ---------------------------------------------------------------------------
@dataclass
class Message:
    """
    Estrutura base de toda mensagem trocada no protocolo.

    Campos:
        msg_type  : "command" ou "response" ou "heartbeat"
        payload   : dados da mensagem (dict arbitrário)
        timestamp : unix timestamp de criação
        msg_id    : identificador único (para correlacionar req/resp)
    """
    msg_type  : str
    payload   : dict
    timestamp : float = None
    msg_id    : str   = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.msg_id is None:
            import uuid
            self.msg_id = str(uuid.uuid4())[:8]

    def to_json(self) -> str:
        """Serializa para JSON + newline (delimitador de mensagem)."""
        return json.dumps(asdict(self)) + "\n"

    @classmethod
    def from_json(cls, raw: str) -> "Message":
        """Desserializa de string JSON."""
        data = json.loads(raw.strip())
        return cls(**data)


def build_command(cmd_type: CommandType, args: Optional[Any] = None) -> Message:
    """Constrói uma mensagem de comando."""
    return Message(
        msg_type="command",
        payload={"command": cmd_type.value, "args": args}
    )


def build_response(status: ResponseStatus, data: Any, msg_id: str = None) -> Message:
    """Constrói uma mensagem de resposta."""
    return Message(
        msg_type="response",
        payload={"status": status.value, "data": data},
        msg_id=msg_id
    )


def build_heartbeat(agent_id: str) -> Message:
    """Constrói uma mensagem de heartbeat (sinal de vida)."""
    return Message(
        msg_type="heartbeat",
        payload={"agent_id": agent_id, "uptime": time.time()}
    )


# ---------------------------------------------------------------------------
# Utilitários de Socket
# ---------------------------------------------------------------------------
BUFFER_SIZE   = 4096
MESSAGE_SEP   = b"\n"


def send_message(sock: socket.socket, msg: Message) -> None:
    """
    Envia uma mensagem pelo socket.
    Usa newline como delimitador — simples e eficaz para JSON de linha única.
    """
    data = msg.to_json().encode("utf-8")
    sock.sendall(data)


def recv_message(sock: socket.socket) -> Optional[Message]:
    """
    Recebe uma mensagem do socket.
    Lê até encontrar o delimitador newline.
    Retorna None se a conexão foi encerrada.
    """
    buffer = b""
    while True:
        chunk = sock.recv(BUFFER_SIZE)
        if not chunk:
            return None  # Conexão encerrada pelo par
        buffer += chunk
        if MESSAGE_SEP in buffer:
            line, _ = buffer.split(MESSAGE_SEP, 1)
            return Message.from_json(line.decode("utf-8"))
