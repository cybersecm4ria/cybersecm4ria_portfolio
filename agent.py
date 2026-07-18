# RemoteLab - Arquivo de Configuração
# =====================================
# Edite este arquivo para ajustar host, porta e comportamentos.
# Usado pelo Agent e pelo Controller.

[network]
# Endereço IP do Controller (Agent se conecta aqui)
host = 127.0.0.1
# Porta TCP. Use porta > 1024 para evitar necessidade de admin
port = 9999
# Timeout de socket em segundos
socket_timeout = 10

[agent]
# Identificador único deste agente (visível no Controller)
agent_id = AGENT-001
# Intervalo de heartbeat em segundos
heartbeat_interval = 15
# Tempo de espera entre tentativas de reconexão (segundos)
reconnect_delay = 5
# Número máximo de tentativas de reconexão (0 = infinito)
max_reconnect_attempts = 0
# Diretório de logs do agente
log_dir = logs/agent

[controller]
# Número máximo de agentes simultâneos
max_agents = 10
# Diretório de logs do controller
log_dir = logs/controller
# Timeout para aguardar resposta do agente (segundos)
response_timeout = 15

[security]
# AVISO ACADÊMICO: Em produção, implementar TLS e autenticação.
# Token simples para demonstração (não é criptografia real)
auth_token = REMOTELAB-ACADEMIC-2024
