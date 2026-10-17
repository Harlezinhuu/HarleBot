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

### Testes
```bash
pip install pytest
pytest
```

## Estrutura

```
bot.py            # liga o bot e carrega os módulos
cogs/             # cada arquivo é um módulo (moderação, registros...)
core/db.py        # banco de dados SQLite (avisos, casos, configurações)
utils/            # cores, mensagens e conversor de tempo
tests/            # testes automáticos
```

Para adicionar um módulo novo, crie um arquivo em `cogs/` e coloque o nome dele na lista `COGS` do `bot.py`.

## Próximas etapas
- [x] Etapa 1: base, moderação e registros
- [ ] Etapa 2: jogos (quiz, economia com moedas, jogos rápidos e níveis por XP)
- [ ] Etapa 3: música (SoundCloud e YouTube)
- [ ] Hospedagem 24h na nuvem

## Licença
[MIT](LICENSE) © 2026 Ahmad (Harle). Pode usar, modificar e compartilhar, desde que mantenha
o aviso de copyright e a licença junto com o código.

## Observações
- O registro de **mensagens apagadas** só funciona para mensagens enviadas depois que o bot ligou
  (o Discord não manda o conteúdo de mensagens antigas).
- O Discord não deixa silenciar administradores, e o máximo de castigo é 28 dias.
