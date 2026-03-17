# Faglig Tinder

Denne version kan koere med Neon PostgreSQL (anbefalet til Streamlit Share) og har SQLite som lokal fallback.

## Filer
- `app.py`: Bruger-app til at oprette bruger, udfordringer og stemme
- `overview_app.py`: Oversigt over udfordringer og hvem der har valgt dem
- `db_sqlite.py`: Database-lag og auto-oprettelse af tabeller (PostgreSQL eller SQLite fallback)
- `requirements.txt`: Python dependencies

## Database
Tabeller (oprettes automatisk ved opstart):
- `Users(id, navn)`
- `Problem(id, tekst, userId)`
- `Vote(userId, problemId)`

Lokal fallback uden `database_url`:
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

## Publish (Streamlit Share + Neon)
1. Push mappen til GitHub.
2. Opret app i Streamlit Share med entrypoint `app.py`.
3. I app settings -> Secrets, indsaet:

```toml
database_url = "postgresql://<user>:<password>@<host>/<db>?sslmode=require&channel_binding=require"
```

4. Deploy/redeploy appen.

Bemaerk:
- `database_url` i secrets bliver brugt foerst.
- Hvis `database_url` mangler, bruges lokal SQLite fallback (ikke egnet til delt cloud-data).
