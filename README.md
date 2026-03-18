# Faglig Tinder

Denne version kan koere med PostgreSQL, MySQL og SQLite fallback.

## Filer
- `app.py`: Bruger-app til at oprette bruger, udfordringer og stemme
- `overview_app.py`: Oversigt over udfordringer og hvem der har valgt dem
- `db_sqlite.py`: Database-lag og auto-oprettelse af tabeller (PostgreSQL, MySQL eller SQLite fallback)
- `requirements.txt`: Python dependencies

## Database
Tabeller (oprettes automatisk ved opstart):
- `Users(id, navn)`
- `Problem(id, tekst, userId)`
- `Vote(userId, problemId)`

Lokal fallback uden database-secrets:
- `faglig_tinder.db`

## Lokal kørsel
```bash
pip install -r requirements.txt
streamlit run app.py
```

For oversigtssiden:
```bash
streamlit run overview_app.py
```

## Publish (Streamlit Share + PostgreSQL)
1. Push mappen til GitHub.
2. Opret app i Streamlit Share med entrypoint `app.py`.
3. I app settings -> Secrets, indsaet:

```toml
database_url = "postgresql://<user>:<password>@<host>/<db>?sslmode=require&channel_binding=require"
```

4. Deploy/redeploy appen.

Bemaerk:
- `database_url` i secrets bliver brugt foerst.
- Hvis `database_url` mangler, kan appen bruge MySQL via secrets/env:

```toml
DB_ADDRESS = "<mysql-host>"
DB_USER = "<mysql-user>"
DB_PASS = "<mysql-password>"
DB_NAME = "<mysql-database>"
DB_PORT = 3306
```

- Hvis hverken PostgreSQL eller MySQL er konfigureret, bruges lokal SQLite fallback (ikke egnet til delt cloud-data).

For `appkbh.py` kan du bruge en lokal `.streamlit/secrets.toml` med:

```toml
KBH_DB_ADDRESS = "<mysql-host>"
KBH_DB_USER = "<mysql-user>"
KBH_DB_PASS = "<mysql-password>"
KBH_DB_NAME = "<mysql-database>"
KBH_DB_PORT = 3306
```

Filen er ignoreret af git. Se `.streamlit/secrets.toml.example`.
