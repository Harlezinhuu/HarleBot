# Harle Bot

Bot de Discord completo, feito em Python com [discord.py](https://discordpy.readthedocs.io/).
Moderação, registros e (em breve) jogos e música, tudo com comandos de barra (`/`) em português.

Feito por **Harle** · [harlezinhuu.github.io](https://harlezinhuu.github.io)

## O que ele faz

### Moderação
| Comando | O que faz |
|---|---|
| `/banir` | Bane alguém, até quem já saiu do servidor. Pode apagar as mensagens recentes da pessoa. |
| `/desbanir` | Tira o banimento pelo ID. |
| `/expulsar` | Expulsa alguém (pode voltar com convite). |
| `/silenciar` | Castigo por tempo: `10m`, `1h`, `2d`, `1h30m`... até 28 dias. |
| `/dessilenciar` | Tira o castigo antes da hora. |
| `/limpar` | Apaga de 1 a 100 mensagens, de todo mundo ou só de uma pessoa. |
| `/avisar` | Dá um aviso que fica salvo no histórico. |
| `/avisos` | Mostra os avisos de alguém. |
| `/remover-aviso` | Apaga um aviso pelo ID. |
| `/limpar-avisos` | Apaga todos os avisos de alguém. |
| `/trancar` e `/destrancar` | Fecha e abre o canal para mensagens. |
| `/modo-lento` | Intervalo entre mensagens no canal. |

Toda punição vira um **caso numerado** (#1, #2...), a pessoa recebe uma mensagem privada
explicando o motivo e o bot não deixa ninguém punir alguém com cargo igual ou maior que o dele.

### Música
Toca músicas do **YouTube** e do **SoundCloud** no canal de voz, por nome ou link (playlists também).

| Comando | O que faz |
|---|---|
| `/tocar` | Toca ou coloca na fila (dá para escolher onde procurar). |
| `/pular`, `/pausar`, `/continuar`, `/parar` | Controles básicos (`/parar` limpa a fila e sai). |
| `/tocando` | Música atual com barra de progresso. |
| `/fila`, `/remover`, `/embaralhar` | Gerencia a fila. |
| `/loop` | Repete a música ou a fila inteira. |
| `/volume` | De 0 a 150%. |

- Se o YouTube bloquear uma música (comum em servidores na nuvem), o bot procura a mesma no SoundCloud sozinho.
- Sai do canal depois de 3 minutos sem música ou 1 minuto sozinho.
- O FFmpeg e o motor de JavaScript do YouTube vêm pelo `pip` (`imageio-ffmpeg` e `deno`), sem instalar nada à parte.

### Jogos
| Comando | O que faz |
|---|---|
| `/quiz` | Pergunta com 4 opções. Quem acertar primeiro ganha moedas (cada pessoa tem uma chance). |
| `/forca` | Forca em grupo: todo mundo do canal pode chutar letras ou a palavra. |
| `/velha` | Jogo da velha contra alguém (a pessoa recebe um convite para aceitar) ou contra o bot, nas dificuldades fácil, médio e impossível. |
| `/ppt` | Pedra, papel e tesoura contra o bot, com aposta opcional. |
| `/batalha` | Batalha 1x1 por turnos (atacar, especial, defender e curar), com convite e aposta opcional. Quem demorar mais de 60s na vez perde. |

### Cassino
| Comando | O que faz |
|---|---|
| `/blackjack` | 21 contra a mesa: pedir carta, parar ou dobrar. Blackjack de cara paga 3 para 2. |
| `/minas` | Campo minado: cada casa aberta aumenta o multiplicador. Saque antes de achar uma bomba (3, 5 ou 8 bombas). |

### Economia (Harlecoins 🪙)
| Comando | O que faz |
|---|---|
| `/daily` | Moedas do dia. Voltando todo dia, a sequência dá bônus. |
| `/trabalhar` | Ganha moedas uma vez por hora. |
| `/saldo` | Mostra a carteira. |
| `/pagar` | Manda moedas para outra pessoa. |
| `/apostar` | Cara ou coroa: acertou, dobra. |
| `/ranking-moedas` | Quem tem mais moedas no servidor. |
| 🔒 `/loja-adicionar`, `/loja-remover`, `/dar-moedas` | Para a administração gerenciar a loja e as moedas. |

### Loja e perfil
Itens comprados com Harlecoins para personalizar o perfil, no estilo da Loritta.

| Comando | O que faz |
|---|---|
| `/loja` | Abre a loja com abas: temas, insígnias, títulos, boosts e cargos do servidor. |
| `/comprar` | Compra um item (é só começar a digitar o nome ou a categoria). |
| `/inventario` | Seus itens e boosts ativos. |
| `/usar` | Equipa um tema ou título, ou ativa um boost. |
| `/perfil` | Perfil com tema, título, "sobre mim", insígnias, nível e moedas. |
| `/sobremim` | Escreve o texto do seu perfil. |

- **Temas** mudam a cor e o emoji do perfil (Neon, Sakura, Galáxia, Ouro...).
- **Insígnias** aparecem todas no perfil (🐉, 👑, 💎...).
- **Títulos** aparecem embaixo do nome ("A Lenda", "Lenda do Cassino"...).
- **Boosts**: XP em dobro e salário em dobro por 1 hora, e daily em dobro.

Para criar itens novos, é só editar `conteudo/itens.py`.

### Níveis
Cada mensagem no chat dá XP (no máximo uma vez por minuto, para não valer spam).
Ao subir de nível, a pessoa ganha moedas e, se configurado, um cargo.

| Comando | O que faz |
|---|---|
| `/nivel` | Nível, XP e posição no ranking. |
| `/ranking-xp` | Quem mais conversa no servidor. |
| `/recompensas` | Cargos que se ganha por nível. |
| 🔒 `/recompensa-adicionar`, `/recompensa-remover` | Configura os cargos por nível. |
| 🔒 `/config-niveis` | Liga/desliga o aviso de subir de nível e escolhe o canal. |

### Status
O perfil do bot fica trocando de status a cada 45 segundos (lista em `cogs/status.py`, fácil de editar).

### Registros
Com `/config-logs #canal`, o bot anota nesse canal: punições, limpezas, mensagens apagadas
e editadas, e quem entra e sai do servidor.

### Geral
`/ajuda` lista todos os comandos e `/ping` mostra se o bot está respondendo.

## Como colocar para rodar

### 1. Crie o bot no Discord
1. Entre no [Discord Developer Portal](https://discord.com/developers/applications) e clique em **New Application**.
2. Na aba **Bot**, clique em **Reset Token** e copie o token. **Não mostre para ninguém.**
3. Ainda na aba **Bot**, ligue **Server Members Intent** e **Message Content Intent**.
4. Na aba **OAuth2 → URL Generator**, marque `bot` e `applications.commands`. Nas permissões, marque:
   Banir membros, Expulsar membros, Castigar membros, Gerenciar mensagens, Gerenciar canais,
   Gerenciar cargos, Ver canais, Enviar mensagens, Inserir links e Ler histórico de mensagens.
5. Abra o link gerado e adicione o bot no seu servidor.
6. Em **Configurações do servidor → Cargos**, arraste o cargo do bot para cima dos cargos que ele vai moderar.

### 2. Rode no seu PC
Precisa de **Python 3.10 ou mais novo**.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

Copie o `.env.example` para `.env` e cole o token em `DISCORD_TOKEN`.

> **Dica:** coloque o ID do seu servidor em `GUILD_ID` enquanto estiver testando.
> Assim os comandos aparecem na hora, em vez de demorar alguns minutos.
> (Para pegar o ID: Configurações → Avançado → Modo desenvolvedor, depois clique com o botão direito no servidor → Copiar ID.)

```bash
python bot.py
```

Pronto! No servidor, use `/config-logs` para escolher o canal de registros.

### 3. Ou hospede na Square Cloud (24h, sem deixar o PC ligado)
O projeto já vem com o `squarecloud.app` configurado (768 MB de RAM e reinício automático).

1. Compacte os arquivos do projeto em um `.zip`, com o `squarecloud.app` **na raiz** do zip (sem a pasta `.env`).
2. No painel da [Square Cloud](https://squarecloud.app), clique em **Upload** e envie o zip.
3. Nas **variáveis de ambiente** da aplicação, adicione `DISCORD_TOKEN` com o token do bot.
4. Inicie a aplicação e acompanhe pelo console do painel.

### Testes
```bash
pip install pytest
pytest
```

## Estrutura

```
bot.py            # liga o bot e carrega os módulos
cogs/             # cada arquivo é um módulo (moderação, registros...)
core/db.py        # banco de dados SQLite (avisos, casos, moedas, XP, configurações)
conteudo/         # perguntas do quiz e palavras da forca (fácil de adicionar mais)
utils/            # cores, moeda, regras dos jogos e contas de nível
tests/            # testes automáticos
```

Para adicionar um módulo novo, crie um arquivo em `cogs/` e coloque o nome dele na lista `COGS` do `bot.py`.

## Próximas etapas
- [x] Etapa 1: base, moderação e registros
- [x] Etapa 2: jogos (quiz, forca, velha, ppt), economia com moedas, níveis por XP e status aleatórios
- [x] Etapa 3: música (SoundCloud e YouTube)
- [ ] Hospedagem 24h na nuvem

## Licença
[MIT](LICENSE) © 2026 Ahmad (Harle). Pode usar, modificar e compartilhar, desde que mantenha
o aviso de copyright e a licença junto com o código.

## Observações
- O registro de **mensagens apagadas** só funciona para mensagens enviadas depois que o bot ligou
  (o Discord não manda o conteúdo de mensagens antigas).
- O Discord não deixa silenciar administradores, e o máximo de castigo é 28 dias.
