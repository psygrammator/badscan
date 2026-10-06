# badscan

Локальный сбор двух списков для оффера CoreWeb:

1. Публичные главные украинских сайтов: CMS, TTFB, HTTPS, viewport, телефон и почта с страницы, оценка `bad_score`.
2. Открытые заявки «сделайте сайт»: Freelancehunt API (твой токен), публичные посты `t.me/s/<channel>`, RSS.

Офферы никуда не отправляются. В Telegram уходит только дайджест тебе, если прописан свой бот.

## Запуск

```powershell
cd E:\VibeCoding\SearchBadSites
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -X utf8 -m badscan init
```

Или без активации venv: `.\badscan.ps1 scan --seeds seeds\demo.txt`

В `config.toml`:

- `pagespeed.api_key` — по желанию, Lighthouse mobile. Без ключа остаётся свой замер.
- `demand.freelancehunt.token` — https://freelancehunt.com/my/api
- `notify.bot_token` и `notify.chat_id` — свой бот, свой чат.

## Команды

```powershell
python -X utf8 -m badscan niches
python -X utf8 -m badscan hunt --niches realty,building --cities Харків,Київ,Одеса,Львів,Дніпро
python -X utf8 -m badscan hunt
python -X utf8 -m badscan scan --seeds seeds\demo.txt
python -X utf8 -m badscan discover --zones kh.ua,od.ua,lviv.ua --limit 20 --scan
python -X utf8 -m badscan discover --source cc --zones kh.ua --limit 20
python -X utf8 -m badscan demand
python -X utf8 -m badscan demand --loop 20
python -X utf8 -m badscan export --what sites --min-score 50 --out data\sites.csv
python -X utf8 -m badscan export --what demand --out data\demand.csv
python -X utf8 -m badscan report --open
```

`bad_score` выше — сайт слабее. В отчёте фильтр по умолчанию от 30. Парковки доменов получают 0 и в оффер не идут.

Повторный `scan` пропускает домен, если его смотрели меньше `rescan_days` (по умолчанию 14). `--force` сканит заново. История точек лежит в `site_scans`.

`hunt` ищет компании по нишам через публичную выдачу и раскладывает их по категориям: недвижимость, стройматериалы, стройкомпании, медицина, авто, юристы, отели, мебель, салоны, логистика, учебные центры. Города по умолчанию: Харків, Київ, Одеса, Львів, Дніпро, Запоріжжя. Каталоги (OLX, Lun, Prom) выкидываются. В `data\sites.csv` попадают все сайты с нишей, слабые сверху внутри категории.

Если выдача отвечает капчей, `hunt` останавливает поиск и берёт `seeds\niches.tsv` (категория, город, url, название через таб). Туда же дописывай свои находки. Повторный `hunt` через час снова пойдёт в выдачу и добавит новые домены.

`discover` по сертификатам [crt.sh](https://crt.sh/) и индексу [Common Crawl](https://index.commoncrawl.org/) нишу не знает. Для оффера по отраслям используй `hunt`.

Между запросами к чужим главной стоит пауза `delay_sec`. Не обнуляй её.
