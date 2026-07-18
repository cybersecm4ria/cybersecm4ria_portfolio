"""
RemoteLab - Agent Principal
============================
Aplicação cliente que:
  1. Conecta ao Controller via TCP
  2. Envia heartbeats periódicos
  3. Recebe comandos e os executa via handlers locais
  4. Reconecta automaticamente em caso de queda

Arquitetura de threads:
  - Thread Principal  : loop de reconexão
  - Thread de Receive : aguarda comandos do Controller
  - Thread de Heartbeat: envia pulso periódico

Uso: python agent.py [--config caminho/remotelab.ini]
"""

import sys
import os
import time
import socket
import threading
import configparser
import argparse
from pathlib import Path

# Adiciona o diretório raiz ao path para importar shared.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.protocol import (
    Message, CommandType, ResponseStatus,
    build_response, build_heartbeat,
    send_message, recv_message
)
from shared.logger import setup_logger
from agent.sysinfo import (
    collect_sysinfo, collect_netstat,
    collect_whoami, collect_env, list_directory
)


# ---------------------------------------------------------------------------
# Dispatcher de Comandos
# ---------------------------------------------------------------------------

def dispatch_command(cmd_msg: Message, logger) -> Message:
    """
    Recebe uma mensagem de comando, executa a ação correspondente
    e retorna a mensagem de resposta.

    Este é o núcleo do agente: cada CommandType tem um handler.
    Adicionar um novo comando = adicionar um elif aqui.
    """
    payload = cmd_msg.payload
    cmd     = payload.get("command", "")
    args    = payload.get("args")
    msg_id  = cmd_msg.msg_id

    logger.info(f"Executando comando: {cmd} | args={args} | id={msg_id}")

    try:
        if cmd == CommandType.PING:
            data = {"pong": True, "time": time.time()}

        elif cmd == CommandType.SYSINFO:
            data = collect_sysinfo()

        elif cmd == CommandType.WHOAMI:
            data = collect_whoami()

        elif cmd == CommandType.GETENV:
            data = collect_env()

        elif cmd == CommandType.NETSTAT:
            data = collect_netstat()

        elif cmd == CommandType.LISTDIR:
            path = args if args else os.path.expanduser("~")
            data = list_directory(path)

        elif cmd == CommandType.DISCONNECT:
            # Sinaliza ao loop principal que deve desconectar
            data = {"message": "Agente encerrando conexão conforme solicitado."}
            resp = build_response(ResponseStatus.OK, data, msg_id)
            return resp  # O caller vai tratar o DISCONNECT depois

        else:
            data = {"error": f"Comando desconhecido: {cmd}"}
            return build_response(ResponseStatus.ERROR, data, msg_id)

        return build_response(ResponseStatus.OK, data, msg_id)

    except Exception as e:
        logger.exception(f"Erro ao executar comando {cmd}: {e}")
        return build_response(
            ResponseStatus.ERROR,
            {"error": str(e), "command": cmd},
            msg_id
        )


# ---------------------------------------------------------------------------
# Classe Principal do Agent
# ---------------------------------------------------------------------------

class RemoteLabAgent:
    """
    Gerencia o ciclo de vida do agente:
    conexão, reconexão, heartbeat e processamento de comandos.
    """

    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.logger = setup_logger(
            "agent",
            log_dir=self.config.get("agent", "log_dir", fallback="logs/agent")
        )

        # Parâmetros de rede
        self.host    = self.config.get("network", "host", fallback="127.0.0.1")
        self.port    = self.config.getint("network", "port", fallback=9999)
        self.timeout = self.config.getint("network", "socket_timeout", fallback=10)

        # Parâmetros do agente
        self.agent_id         = self.config.get("agent", "agent_id", fallback="AGENT-001")
        self.heartbeat_iv     = self.config.getint("agent", "heartbeat_interval", fallback=15)
        self.reconnect_delay  = self.config.getint("agent", "reconnect_delay", fallback=5)
        self.max_reconnects   = self.config.getint("agent", "max_reconnect_attempts", fallback=0)
        self.auth_token       = self.config.get("security", "auth_token", fallback="")

        # Estado interno
        self.sock              = None
        self.running           = False
        self.connected         = False
        self._stop_event       = threading.Event()
        self._lock             = threading.Lock()  # Protege o socket contra race conditions

    def _load_config(self, path: str) -> configparser.ConfigParser:
        cfg = configparser.ConfigParser()
        if os.path.exists(path):
            cfg.read(path, encoding="utf-8")
        else:
            print(f"[AVISO] Config não encontrada: {path}. Usando defaults.")
        return cfg

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------

    def _connect(self) -> bool:
        """Tenta estabelecer conexão TCP com o Controller."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.host, self.port))
            self.connected = True
            self.logger.info(f"Conectado ao Controller em {self.host}:{self.port}")

            # Envia identificação imediata
            hello = Message(
                msg_type="hello",
                payload={"agent_id": self.agent_id, "auth_token": self.auth_token}
            )
            send_message(self.sock, hello)
            return True

        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            self.logger.warning(f"Falha na conexão: {e}")
            self.connected = False
            if self.sock:
                self.sock.close()
                self.sock = None
            return False

    def _disconnect(self):
        """Encerra a conexão de forma limpa."""
        self.connected = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        self.logger.info("Desconectado do Controller.")

    # ------------------------------------------------------------------
    # Thread de Heartbeat
    # ------------------------------------------------------------------

    def _heartbeat_loop(self):
        """
        Envia um heartbeat periodicamente para informar ao Controller
        que o agente está vivo. Roda em thread separada.
        """
        self.logger.debug("Thread de heartbeat iniciada.")
        while not self._stop_event.is_set():
            time.sleep(self.heartbeat_iv)
            if self.connected and self.sock:
                try:
                    with self._lock:
                        send_message(self.sock, build_heartbeat(self.agent_id))
                    self.logger.debug("Heartbeat enviado.")
                except OSError:
                    self.logger.warning("Falha ao enviar heartbeat — conexão perdida.")
                    self.connected = False

    # ------------------------------------------------------------------
    # Thread de Recebimento
    # ------------------------------------------------------------------

    def _receive_loop(self):
        """
        Aguarda mensagens do Controller em loop bloqueante.
        Processa comandos e envia respostas.
        Roda em thread separada.
        """
        self.logger.debug("Thread de recebimento iniciada.")
        while self.connected and not self._stop_event.is_set():
            try:
                msg = recv_message(self.sock)
                if msg is None:
                    self.logger.info("Controller encerrou a conexão.")
                    self.connected = False
                    break

                self.logger.debug(f"Mensagem recebida: type={msg.msg_type}")

                if msg.msg_type == "command":
                    # Processa em thread para não bloquear o receive_loop
                    t = threading.Thread(
                        target=self._handle_command,
                        args=(msg,),
                        daemon=True
                    )
                    t.start()

            except socket.timeout:
                continue  # Timeout normal, aguarda próxima mensagem
            except OSError as e:
                if self.connected:
                    self.logger.error(f"Erro de socket no receive_loop: {e}")
                self.connected = False
                break

    def _handle_command(self, msg: Message):
        """Executa um comando e envia a resposta (chamado em thread)."""
        response = dispatch_command(msg, self.logger)
        try:
            with self._lock:
                send_message(self.sock, response)

            # Se o comando era DISCONNECT, encerra
            if msg.payload.get("command") == CommandType.DISCONNECT:
                self.logger.info("Comando DISCONNECT recebido. Encerrando...")
                self._stop_event.set()
                self.connected = False

        except OSError as e:
            self.logger.error(f"Falha ao enviar resposta: {e}")

    # ------------------------------------------------------------------
    # Loop Principal (com reconexão automática)
    # ------------------------------------------------------------------

    def run(self):
        """
        Ponto de entrada principal do agente.
        Gerencia reconexão automática e threads de suporte.
        """
        self.running = True
        attempts = 0

        self.logger.info(f"RemoteLab Agent '{self.agent_id}' iniciando...")
        self.logger.info(f"Alvo: {self.host}:{self.port}")

        # Inicia thread de heartbeat (fica ativa durante toda execução)
        hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        hb_thread.start()

        while not self._stop_event.is_set():
            if self.max_reconnects > 0 and attempts >= self.max_reconnects:
                self.logger.error("Número máximo de tentativas atingido. Encerrando.")
                break

            if not self._connect():
                attempts += 1
                wait = self.reconnect_delay
                self.logger.info(f"Tentativa {attempts}. Reconectando em {wait}s...")
                time.sleep(wait)
                continue

            attempts = 0  # Reset ao conectar com sucesso

            # Inicia thread de recebimento
            rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
            rx_thread.start()
            rx_thread.join()  # Bloqueia até desconectar

            # Se não foi sinalizado para parar, tenta reconectar
            if not self._stop_event.is_set():
                self.logger.warning(f"Conexão perdida. Reconectando em {self.reconnect_delay}s...")
                self._disconnect()
                time.sleep(self.reconnect_delay)

        self._disconnect()
        self.logger.info("Agent encerrado.")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="RemoteLab Agent")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "..", "config", "remotelab.ini"),
        help="Caminho para o arquivo de configuração INI"
    )
    args = parser.parse_args()

    agent = RemoteLabAgent(config_path=args.config)
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n[Agent] Interrompido pelo usuário.")


if __name__ == "__main__":
    main()
