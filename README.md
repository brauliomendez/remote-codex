# Telegram Codex Bridge

Bot de Telegram en Python que reenvia cada mensaje de texto directamente a Codex CLI.

No usa `openai-agents`, no expone Codex por MCP y no mantiene una memoria paralela en el bot. La continuidad de la conversacion la lleva Codex: cada chat de Telegram queda enlazado a un `thread_id` de Codex y el siguiente mensaje hace `codex exec resume`.

## Que hace

- Reenvia mensajes de Telegram a `codex exec`
- Reanuda la misma conversacion de Codex por chat de Telegram
- Guarda por chat el `thread_id` y el `workdir` en SQLite
- Permite cambiar el directorio de trabajo con `/path`
- Permite cortar la conversacion actual con `/new` o `/reset`
- Lista sesiones recientes con `/sessions`
- Permite retomar una sesion anterior con `/resume`

## Comandos

- `/start`: muestra ayuda rapida y el estado actual
- `/path`: muestra el directorio de trabajo actual
- `/path <ruta>`: cambia el directorio de trabajo para ese chat y abre una sesion nueva
- `/status`: muestra `workdir`, `thread_id`, modelo y sandbox
- `/sessions`: lista sesiones recientes guardadas para ese chat
- `/resume <numero|thread_id>`: retoma una sesion anterior y restaura su `workdir`
- `/new`: desvincula el `thread_id` actual, pero mantiene el historial para `/resume`
- `/reset`: desvincula el `thread_id` actual y borra el historial guardado por el bot para ese chat

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m telegram_openai_bot --check-config
python -m telegram_openai_bot
```

## Requisitos

- Python 3.12
- `python-telegram-bot`
- `python-dotenv`
- `codex` instalado y autenticado en la maquina

Comprobacion minima:

```bash
codex --version
codex exec --help
```

## Configuracion

Variables en `.env`:

- `TELEGRAM_BOT_TOKEN`: token del bot de Telegram
- `CODEX_COMMAND`: binario a ejecutar, por defecto `codex`
- `CODEX_BASE_ARGS`: argumentos base opcionales antes de `exec`
- `CODEX_DEFAULT_WORKDIR`: directorio inicial por defecto para chats nuevos
- `CODEX_ALLOWED_ROOTS`: lista de roots permitidos separada por `:`. Si esta vacia, cualquier directorio existente es valido
- `CODEX_MODEL`: modelo opcional para pasar a Codex
- `CODEX_SANDBOX`: sandbox de Codex, por defecto `workspace-write`
- `CODEX_SKIP_GIT_REPO_CHECK`: por defecto `true`
- `CODEX_ENABLE_WEB_SEARCH`: activa `--search` en Codex
- `STATE_DB_PATH`: ruta de la base SQLite del bot
- `TELEGRAM_SUMMARY_WORD_LIMIT`: si una respuesta supera este numero de palabras, el bot pide a Codex un resumen breve antes de reenviarla

## Como funciona la continuidad

1. el primer mensaje de un chat ejecuta `codex exec`
2. Codex devuelve un `thread_id`
3. el bot guarda ese `thread_id`
4. el siguiente mensaje usa `codex exec resume <thread_id>`

Si cambias el path con `/path`, el bot corta la sesion actual para no mezclar contexto de Codex entre repositorios distintos.
Las sesiones anteriores siguen guardadas en el historial del chat y pueden recuperarse con `/sessions` y `/resume`.

## Archivos de estado

- SQLite del bot: `data/telegram_codex_state.sqlite3`
- Sesiones internas de Codex: las gestiona el propio CLI en `~/.codex/`

## Validacion local

```bash
python -m telegram_openai_bot --check-config
python -m compileall telegram_openai_bot
```

La validacion end to end requiere credenciales reales de Telegram y una instalacion funcional de Codex CLI.

## Servicio systemd

```bash
sudo cp deploy/systemd/telegram-openai-bot.service /etc/systemd/system/telegram-openai-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-openai-bot
sudo systemctl status telegram-openai-bot
```

Logs:

```bash
journalctl -u telegram-openai-bot -f
```
