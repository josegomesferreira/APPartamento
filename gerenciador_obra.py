import json # Adicione este import no topo do arquivo

@st.cache_resource
def get_google_services():
    """Autentica via Secrets (para nuvem) ou arquivo local (para desenvolvimento)."""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Tenta ler do Streamlit Secrets (Nuvem)
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        # Fallback para o arquivo local (seu ambiente atual)
        creds = Credentials.from_service_account_file(CLIENT_SECRETS_FILE, scopes=scopes)
            
    gc = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return gc, drive_service
