# Навантажувальний тест

`radar_load.py` — генератор, який поводиться як реальний фронт: кожен
віртуальний користувач робить те, що робить `bootstrap.ts` на завантаженні
сторінки (3 статичні запити + 10 запитів `hydrate()`), відкриває WebSocket і
тримає його. Три сценарії: `boot` (натовп відкриває мапу), `storm` (усі вже
підключені, сервер рестартує — всі перепідключаються за ~1 с; `--storm-mode`
`hydrate` = старий клієнт із 10 запитами, `delta` = `/sync` з позицією,
`full` = `/sync` з чужим epoch, тобто після справжнього деплою), `hold` (тільки сокети — вимірює розкид fan-out'у одного кадру між першим і
останнім клієнтом).

**Ніколи не спрямовувати на прод.** Для бекенду це нічим не відрізняється від
реального натовпу під час тривоги.

## Локально (ізольований сервер на копії БД)

```bash
cd backend
./loadtest/run_local.sh start        # копія kyiv_radar.db → scratch, uvicorn :8199, без Telegram/LLM
.venv/bin/python -m loadtest.radar_load --users 100 --ramp 10 --hold 15 --server-pid "$(cat /tmp/radar-lt/server.pid)"
.venv/bin/python -m loadtest.radar_load --scenario storm --users 300
.venv/bin/python -m loadtest.radar_load --scenario hold --users 1000 --ramp 20 --hold 40
./loadtest/run_local.sh stop
```

`run_local.sh start pg` піднімає Postgres у Docker (`postgres:16-alpine`,
порт 5499), наповнює його швидким replay 871 реальних повідомлень і стартує
сервер на ньому — це та БД, що на проді, і саме її числа варто цитувати
(SQLite на локальній машині повільніший у 3–4 рази і не показовий).

## Проти staging на Railway

Railway environments → «New environment» (duplicate production) → у ньому
**обовʼязково** `TELEGRAM_ENABLED=false` (одна Telegram-сесія — один процес),
`SIMULATOR_ENABLED=true`, порожні `ANTHROPIC_API_KEY`/`SENTRY_DSN`, окремий
`LOGFIRE_TOKEN` (або порожній). Postgres — окремий сервіс у тому ж environment,
з копією прод-даних (`pg_dump | psql`) або порожній + replay.

```bash
.venv/bin/python -m loadtest.radar_load --base https://<staging>.up.railway.app \
    --ws wss://<staging>.up.railway.app/ws/threats --users 300 --ramp 20 --hold 60 --out staging_300.json
```

Без `--server-pid` (процес не наш) — CPU/RAM дивитись у Railway Metrics і в
Logfire (`radar.ws.clients`, `radar.ws.broadcast_seconds`, латентність
FastAPI-спанів).

## Що вважати результатом

- `boot p95` — скільки чекає користувач, поки мапа стане живою. Поріг: **< 3 с**.
- `!200` і `errors` — має бути нуль. `ReadTimeout` означає, що черга на пул БД
  або event loop перевищила 30 с.
- `ws failed` — нуль; `connect_p95` < 1 с.
- `fan-out spread p95` — на скільки пізніше останній клієнт бачить ціль, ніж
  перший. Поріг: **< 500 мс** (карта оновлюється «одночасно» для всіх).

Зафіксовані числа і висновки — `.claude/plans/load-and-scaling.md`.
