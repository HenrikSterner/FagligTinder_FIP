# Faglig Tinder (SQLite)

Denne version bruger SQLite i stedet for MySQL.

## Filer
- `app.py`: Bruger-app til at oprette bruger, udfordringer og stemme
- `overview_app.py`: Oversigt over udfordringer og hvem der har valgt dem
- `db_sqlite.py`: Database-lag og auto-oprettelse af tabeller
- `requirements.txt`: Python dependencies

## Database
- Standard fil: `faglig_tinder.db` (oprettes automatisk ved opstart)
- Tabeller:
  - `Users(id, navn)`
  - `Problem(id, tekst, userId)`
  - `Vote(userId, problemId)`

## Lokal kørsel
```bash
pip install -r requirements.txt
streamlit run app.py
```

For oversigtssiden:
```bash
streamlit run overview_app.py
```

## Publish (Streamlit Cloud)
1. Push mappen til GitHub.
2. Opret en app med entrypoint `app.py`.
3. Brug `requirements.txt` automatisk.

Valgfrit: Du kan sætte `sqlite_db_path` i `st.secrets` for at vælge en anden database-sti.

Bemærk: På nogle hosting-platforme er filsystemet midlertidigt, så SQLite-data kan blive nulstillet ved redeploy/restart.
