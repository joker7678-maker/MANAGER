# Radio Manager Pro – Protezione Civile Thiene

Console operativa per gestione squadre, comunicazioni, modulo da campo e reportistica.

## Funzioni principali
- Gestione squadre
- Modulo da campo (mobile-friendly)
- Registro interventi con filtro squadra
- Mappa interattiva
- Stato rete / connettività
- Report HTML (velocizzato con cache)

## Avvio locale
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Note
- Per evitare di pubblicare dati reali, i file locali (es. `data.json`, `outbox_pending.json`) sono esclusi da Git tramite `.gitignore`.
- Se usi Streamlit Cloud, configura eventuali segreti in `.streamlit/secrets.toml` (non va mai committato).
