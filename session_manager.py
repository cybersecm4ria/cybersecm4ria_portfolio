"""
RemoteLab Agent - Módulo de Coleta de Informações do Sistema
=============================================================
Coleta informações básicas usando bibliotecas padrão do Python.
Não executa comandos de shell externos — tudo via API Python.

Isso é importante: usar subprocess/shell seria mais simples, mas
ensina práticas inseguras. A abordagem via API é o caminho correto.
"""

import os
import sys
import platform
import socket
import time
import psutil  # pip install psutil
from pathlib import Path
from typing import Any


def collect_sysinfo() -> dict:
    """
    Coleta informações abrangentes do sistema operacional.

    Returns:
        Dicionário com seções: os, cpu, memory, disk, network
    """
    info = {}

    # --- Sistema Operacional ---
    info["os"] = {
        "system"    : platform.system(),
        "release"   : platform.release(),
        "version"   : platform.version(),
        "machine"   : platform.machine(),
        "processor" : platform.processor(),
        "hostname"  : socket.gethostname(),
        "python"    : sys.version,
        "boot_time" : time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(psutil.boot_time())
        ),
    }

    # --- CPU ---
    cpu_freq = psutil.cpu_freq()
    info["cpu"] = {
        "physical_cores" : psutil.cpu_count(logical=False),
        "logical_cores"  : psutil.cpu_count(logical=True),
        "usage_percent"  : psutil.cpu_percent(interval=0.5),
        "freq_mhz"       : round(cpu_freq.current, 1) if cpu_freq else "N/A",
    }

    # --- Memória ---
    mem = psutil.virtual_memory()
    info["memory"] = {
        "total_gb"  : round(mem.total / (1024 ** 3), 2),
        "used_gb"   : round(mem.used / (1024 ** 3), 2),
        "free_gb"   : round(mem.available / (1024 ** 3), 2),
        "percent"   : mem.percent,
    }

    # --- Disco (drives principais) ---
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device"    : part.device,
                "mountpoint": part.mountpoint,
                "fstype"    : part.fstype,
                "total_gb"  : round(usage.total / (1024 ** 3), 2),
                "used_gb"   : round(usage.used / (1024 ** 3), 2),
                "percent"   : usage.percent,
            })
        except PermissionError:
            pass  # Drives sem permissão de leitura (ex: CD-ROM vazio)
    info["disk"] = disks

    # --- Rede (interfaces ativas) ---
    interfaces = []
    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:  # IPv4 apenas
                interfaces.append({
                    "interface": iface,
                    "ip"       : addr.address,
                    "netmask"  : addr.netmask,
                })
    info["network"] = interfaces

    return info


def collect_netstat() -> list:
    """
    Retorna conexões de rede ativas (equivalente ao netstat).

    Returns:
        Lista de conexões com status, endereços local/remoto e PID.
    """
    connections = []
    for conn in psutil.net_connections(kind="inet"):
        connections.append({
            "proto"  : "TCP" if conn.type == 1 else "UDP",
            "local"  : f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "-",
            "remote" : f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "-",
            "status" : conn.status,
            "pid"    : conn.pid,
        })
    return connections


def collect_whoami() -> dict:
    """Retorna informações do usuário atual."""
    return {
        "username": os.environ.get("USERNAME") or os.environ.get("USER") or "unknown",
        "home"    : str(Path.home()),
        "cwd"     : os.getcwd(),
    }


def collect_env() -> dict:
    """
    Retorna variáveis de ambiente (filtrando senhas óbvias).
    Em laboratório isso é educacional; em produção, nunca exponha env vars.
    """
    sensitive_keys = {"PASSWORD", "SECRET", "TOKEN", "KEY", "PASS"}
    filtered = {}
    for k, v in os.environ.items():
        if any(s in k.upper() for s in sensitive_keys):
            filtered[k] = "*** REDACTED ***"
        else:
            filtered[k] = v
    return filtered


def list_directory(path: str) -> Any:
    """
    Lista conteúdo de um diretório.

    Args:
        path: caminho do diretório (str)

    Returns:
        Lista de entradas ou string de erro.
    """
    try:
        entries = []
        for entry in Path(path).iterdir():
            try:
                stat = entry.stat()
                entries.append({
                    "name"     : entry.name,
                    "type"     : "dir" if entry.is_dir() else "file",
                    "size_kb"  : round(stat.st_size / 1024, 2),
                    "modified" : time.strftime(
                        "%Y-%m-%d %H:%M:%S",
                        time.localtime(stat.st_mtime)
                    ),
                })
            except (PermissionError, OSError):
                entries.append({"name": entry.name, "type": "?", "error": "permission denied"})
        return sorted(entries, key=lambda x: (x["type"] != "dir", x["name"].lower()))
    except Exception as e:
        return {"error": str(e)}
