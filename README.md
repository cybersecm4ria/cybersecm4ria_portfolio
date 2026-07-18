## Sobre o projeto

O RemoteLab (Simulador de RAT - Remote Access Trojan) é um projeto de offsec que fiz pra aprender, na prática, como duas máquinas conversam entre si pela rede. Em termos simples: um programa (o **Agent**) roda numa máquina e se conecta a outro programa (o **Controller**), que roda em outra máquina. Uma vez conectados, o Controller consegue pedir informações e o Agent responde — tipo uma central que monitora um posto remoto e recebe atualizações de status dele.

Não é um projeto de especialista, é um projeto de estudo: desenvolvi com apoio de ferramentas de IA ao longo do processo, o que me ajudou a acelerar a implementação, mas entendo e consigo explicar cada decisão de arquitetura e o funcionamento completo do sistema.

Duas coisas guiaram todo o design, mesmo sendo um projeto de aprendizado:
- **Nenhum comando é executado direto no sistema operacional** — tudo passa por bibliotecas Python seguras, não por atalhos que poderiam ser perigosos.
- **Dados sensíveis nunca trafegam sem filtro** — se alguma informação coletada tiver palavras como "senha", "token" ou "chave" no nome, ela é automaticamente escondida antes de sair da máquina.

> **Aviso importante:** este projeto foi feito e testado apenas em máquinas virtuais isoladas, sem acesso à internet ou a redes reais, como parte de uma disciplina da faculdade. Ele nunca deve ser usado para monitorar qualquer computador sem autorização — isso é crime no Brasil, previsto na Lei 12.737/2012.

---

## Como funciona, de forma simples

Pensa assim: o **Agent** é como uma pessoa que liga pra uma central de operações assim que chega ao trabalho, avisa "cheguei, aqui está minha identificação" e fica esperando instruções. De tempos em tempos, ela manda um sinal de "ainda estou aqui" (isso se chama **heartbeat**, ou batimento cardíaco, porque é literalmente um pulso de vida). Quando a central manda uma tarefa, ela executa e responde com o resultado.

O **Controller** é essa central: ele fica esperando novas ligações, confere a identificação de quem liga, e organiza o que cada "funcionário" (Agent) está fazendo.

A comunicação entre os dois acontece por uma tecnologia chamada **socket TCP** — é basicamente o telefone que os dois programas usam pra conversar pela rede, garantindo que as mensagens cheguem completas e na ordem certa.

---

## Arquitetura do código

```
remotelab/
├── agent/
│   ├── agent.py              # O programa que roda na máquina monitorada
│   └── sysinfo.py            # Reúne informações do sistema (CPU, memória, etc.)
├── controller/
│   ├── controller.py         # O painel de controle (o que o operador usa)
│   └── session_manager.py    # Recebe conexões e organiza cada Agent conectado
├── shared/
│   ├── protocol.py           # As "regras da conversa" entre Agent e Controller
│   └── logger.py             # Registra tudo que acontece, pra consulta depois
├── config/
│   └── remotelab.ini         # Arquivo onde se ajustam endereço, porta, etc.
├── logs/                      # Onde ficam os registros gerados durante o uso
└── requirements.txt           # Lista de bibliotecas Python necessárias
```

Uma decisão interessante do projeto: é o Agent quem liga para o Controller, e não o contrário. Parece estranho à primeira vista, mas é assim que sistemas de monitoramento reais costumam funcionar — evita que a máquina monitorada precise ficar com uma "porta aberta" esperando ligação, o que seria um risco de segurança maior.

---

## Como as máquinas trocam mensagens

Toda mensagem trocada é um pacote de texto organizado (no formato **JSON**, bem parecido com o preenchimento de um formulário padronizado). Cada mensagem tem um tipo:

| Tipo de mensagem | Quem manda | O que significa |
|---|---|---|
| `hello` | Agent → Controller | "Cheguei, aqui está minha identificação" |
| `command` | Controller → Agent | "Preciso que você faça isso" |
| `response` | Agent → Controller | "Aqui está o resultado" |
| `heartbeat` | Agent → Controller | "Ainda estou aqui, tudo funcionando" |

**Sequência de uma conversa típica:**

```
Agent                                Controller
  |---- conecta ------------------------>|
  |---- "cheguei, aqui esta o token" ---->|   (confere a identificacao)
  |<--- "me diz seu status" -------------|
  |---- "esta tudo ok" ------------------>|
  |                                       |
  |   (a cada 15 segundos)                |
  |---- "ainda estou aqui" -------------->|
  |                                       |
  |<--- "encerrar conexao" --------------|
  |---- "ok, encerrando" ----------------->|
```

Cada mensagem tem um código único (`msg_id`), que funciona como o número de um pedido de delivery: garante que a resposta que chega é exatamente a resposta daquele pedido específico, mesmo com várias conversas acontecendo ao mesmo tempo.

---
**`shared/protocol.py`** — define o "vocabulário" que Agent e Controller usam pra se entenderem: quais tipos de mensagem existem e como elas são organizadas.

**`shared/logger.py`** — registra tudo o que acontece em arquivos de log, guardando as últimas execuções sem deixar o arquivo crescer pra sempre.

**`agent/sysinfo.py`** — coleta informações básicas da máquina (sistema operacional, uso de memória, conexões de rede ativas), sempre usando bibliotecas Python seguras, nunca abrindo um terminal por trás.

**`agent/agent.py`** — o "cérebro" do Agent. Cuida da conexão, tenta reconectar automaticamente se cair, e executa os comandos recebidos.

**`controller/session_manager.py`** — organiza todas as conexões recebidas, sabendo qual resposta pertence a qual pedido.

**`controller/controller.py`** — a tela de menu que um operador usaria pra ver quem está conectado e escolher o que pedir pra cada Agent.

---

## Como rodar (Windows)

**Pré-requisitos:** Python 3.10 ou mais recente, e o `pip` (gerenciador de pacotes do Python) atualizado.

**1. Instalar as dependências:**
```cmd
cd remotelab
pip install -r requirements.txt
```

**2. Ajustar a configuração** em `config/remotelab.ini` — informar o endereço IP e a porta que o Controller vai usar.

**3. Rodar:**

Numa janela de terminal, inicia o Controller primeiro:
```cmd
python -m controller.controller
```

Em outra janela (ou outra máquina virtual), inicia o Agent:
```cmd
python -m agent.agent
```

---

## O que esse projeto me ensinou

- Como duas máquinas conseguem manter uma conexão de rede confiável e se reconectar sozinhas se a conexão cair
- Como organizar um programa pra fazer várias coisas ao mesmo tempo sem uma atrapalhar a outra (isso se chama **threading**)
- Como pensar em segurança desde o início — o que pode ser coletado, o que precisa ser escondido, e o que nunca deve ser feito de forma insegura
- Como documentar um projeto técnico de um jeito que outra pessoa consiga entender e continuar

---

## Limites conhecidos (e por que estão aqui)

Todo projeto de aprendizado tem limitações, e prefiro deixar isso claro em vez de esconder:

- **Sem criptografia real na comunicação** — os dados trafegam sem estar embaralhados. Num sistema de produção, isso seria resolvido com TLS.
- **Autenticação simples** — usa uma senha fixa de acesso, não um sistema de segurança robusto.
- **Sem compactação de dados** — mensagens grandes são enviadas do jeito que são, sem otimização.

Documentar essas limitações também faz parte de entender o projeto por completo.

---

## Sobre mim

Sou a Maria Clara, estudante de Defesa Cibernética na FIAP, com foco em Blue Team — SOC, monitoramento e detecção de ameaças. Fiz o RemoteLab numa disciplina de Análise de malware, e ele virou uma forma de entender, na prática, um simulador de remote access trojan, usado em reconhecimento do alvo.

[LinkedIn](https://www.linkedin.com/in/maria-clara-costa-515542255)
