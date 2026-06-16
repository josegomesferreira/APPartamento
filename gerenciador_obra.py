import streamlit as st
import pandas as pd
import gspread
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import io
import os
import time
from datetime import datetime

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Gestor de Obra Inteligente",
    page_icon="🚧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CONFIGURAÇÃO DE CAMINHOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

# Link da sua planilha e Pasta de Anexos
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1EQaZqr1Mn4OcP0Y55S5VxwmZPnZfTeMyKCJmq2BPS3o/edit"
ANEXOS_FOLDER_ID = "14leb6weZguOux5HMcaovmonLNN3kw2_M"

@st.cache_resource
def get_google_services():
    """Autentica via OAuth2 (híbrido: local ou nuvem via Secrets)."""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Se estiver na Nuvem (Streamlit Cloud), usa o Secrets
    if "oauth" in st.secrets:
        creds = Credentials(
            None,
            refresh_token=st.secrets["oauth"]["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=st.secrets["oauth"]["client_id"],
            client_secret=st.secrets["oauth"]["client_secret"],
            scopes=scopes
        )
    else:
        # Modo Local (usa o token.json que você já criou)
        if not os.path.exists(TOKEN_FILE):
            st.error("❌ Token local não encontrado!")
            st.stop()
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes)
            
    gc = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return gc, drive_service

gc, drive_service = get_google_services()

def get_or_create_sheet_data():
    """Conecta à Planilha Google."""
    try:
        sh = gc.open_by_url(SPREADSHEET_URL)
        return sh.get_worksheet(0)
    except Exception as e:
        st.error(f"Erro ao conectar na Planilha: {e}")
        st.stop()

worksheet = get_or_create_sheet_data()

def load_cloud_data():
    """Lê dados da Planilha."""
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty:
        df['id'] = df['id'].astype(str)
        df['valor_estimado'] = pd.to_numeric(df['valor_estimado'], errors='coerce').fillna(0.0)
        df['valor_real'] = pd.to_numeric(df['valor_real'], errors='coerce').fillna(0.0)
        df['qtd_parcelas'] = pd.to_numeric(df['qtd_parcelas'], errors='coerce').fillna(1).astype(int)
    return df

def get_drive_files_inventory():
    try:
        query = f"'{ANEXOS_FOLDER_ID}' in parents and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name, webViewLink)").execute()
        return results.get('files', [])
    except: return []

def upload_file_to_drive(file_object, file_name):
    file_metadata = {'name': file_name, 'parents': [ANEXOS_FOLDER_ID]}
    media = MediaIoBaseUpload(io.BytesIO(file_object.read()), mimetype=file_object.type, resumable=True)
    uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    return uploaded_file.get('webViewLink')

def delete_file_from_drive(file_id):
    try:
        drive_service.files().delete(fileId=file_id).execute()
        return True
    except: return False

# --- DOMÍNIOS ---
FASES = ["1. Infraestrutura Bruta", "2. Gesso e Drywall", "3. Revestimentos e Pisos", "4. Marcenaria e Pedras", "5. Pintura e Acabamento", "6. Iluminação e Elétrica Fina"]
COMODOS = ["Geral / Todos", "Sala de Estar", "Cozinha", "Suíte Principal", "Quarto 2", "Banheiro Social", "Varanda Gourmet"]
STATUS_OPCOES = ["Não Iniciado", "Em Orçamento", "Orçamento Selecionado", "Contratado / Comprado", "Em Execução / Entrega", "Concluído & Pago"]
CATEGORIAS = ["Material", "Serviço", "Material/Serviço"]
MEIOS_PAGAMENTO = ["Pix", "Cartão de Crédito", "Boleto"]
CONDICOES_PAGAMENTO = ["À vista", "Parcelado"]

# --- INTERFACE ---
st.markdown('<h2 style="color:#1E3A8A;">🚧 Gestor de Obra & Suprimentos Cloud</h2>', unsafe_allow_html=True)

# Lógica de Dados
lista_arquivos_drive = get_drive_files_inventory()
df_original = load_cloud_data()
arquivos_contagem = {}
for f in lista_arquivos_drive:
    name_str = f.get('name', '')
    if name_str.startswith("ID_"):
        parts = name_str.split("_")
        if len(parts) > 1:
            arquivos_contagem[parts[1]] = arquivos_contagem.get(parts[1], 0) + 1
            
            
# Sidebar
st.sidebar.header("🔍 Filtros de Visualização")
filtro_fase = st.sidebar.multiselect("Filtrar por Fase da Obra", FASES, default=[])
filtro_comodo = st.sidebar.multiselect("Filtrar por Cômodo", COMODOS, default=[])

# Carrega inventário do Drive e base do Sheets
lista_arquivos_drive = get_drive_files_inventory()
df_original = load_cloud_data()

# Processa contagem de arquivos por ID para a Opção A
arquivos_contagem = {}
for f in lista_arquivos_drive:
    name_str = f.get('name', '')
    if name_str.startswith("ID_"):
        parts = name_str.split("_")
        if len(parts) > 1:
            item_id = parts[1]
            arquivos_contagem[item_id] = arquivos_contagem.get(item_id, 0) + 1

# Adicionar item manual
st.sidebar.markdown("---")
st.sidebar.header("➕ Adicionar Item Novo")
with st.sidebar.form("form_novo_item", clear_on_submit=True):
    novo_item = st.text_input("Nome do Item/Serviço:")
    nova_fase = st.selectbox("Fase da Obra:", FASES)
    novo_comodo = st.selectbox("Cômodo:", COMODOS)
    nova_cat = st.selectbox("Categoria:", CATEGORIAS)
    novo_status = st.selectbox("Status Inicial:", STATUS_OPCOES)
    val_est = st.number_input("Valor Estimado (R$):", min_value=0.0)
    val_real = st.number_input("Valor Real Fechado (R$):", min_value=0.0)
    fornec = st.text_input("Fornecedor:")
    dt_venc_raw = st.date_input("Vencimento / 1ª Parcela:", value=datetime.today())
    meio_p = st.selectbox("Meio de Pagamento:", MEIOS_PAGAMENTO)
    condicao_p = st.selectbox("Condição de Pagamento:", CONDICOES_PAGAMENTO)
    qtd_p = st.number_input("Quantidade de Parcelas:", min_value=1, value=1, step=1)
    
    btn_salvar = st.form_submit_button("Inserir na Planilha Cloud")
    if btn_salvar and novo_item:
        qtd_final = 1 if condicao_p == "À vista" else int(qtd_p)
        try:
            novo_id = str(int(df_original['id'].astype(int).max() + 1))
        except:
            novo_id = "1"
        dt_hoje = datetime.today().strftime('%Y-%m-%d')
        
        nova_linha_dados = [
            str(novo_id), str(novo_item), str(nova_fase), str(novo_comodo), str(nova_cat), str(novo_status),
            float(val_est), str(val_real), str(fornec), str(dt_hoje), str(dt_venc_raw.strftime('%Y-%m-%d')), 
            str(meio_p), str(condicao_p), int(qtd_final), ""
        ]
        worksheet.append_row(nova_linha_dados, value_input_option="USER_ENTERED")
        st.sidebar.success("✅ Inserido no Google Sheets!")
        time.sleep(0.5)
        st.rerun()

df_original['custo_atual_projetado'] = df_original.apply(
    lambda r: r['valor_real'] if r['status'] in ["Contratado / Comprado", "Em Execução / Entrega", "Concluído & Pago"] and r['valor_real'] > 0 else r['valor_estimado'], 
    axis=1
)

df_filtrado = df_original.copy()
if filtro_fase:
    df_filtrado = df_filtrado[df_filtrado['fase'].isin(filtro_fase)]
if filtro_comodo:
    df_filtrado = df_filtrado[df_filtrado['comodo'].isin(filtro_comodo)]

# KPIs
col1, col2, col3 = st.columns(3)
col1.metric("💰 Orçamento Total Previsto", f"R$ {df_original['valor_estimado'].sum():,.2f}")
col2.metric("💸 Total Comprometido/Pago", f"R$ {df_original[df_original['status'].isin(['Contratado / Comprado', 'Em Execução / Entrega', 'Concluído & Pago'])]['valor_real'].sum():,.2f}")
col3.metric("📉 Projeção Final de Custo", f"R$ {df_original['custo_atual_projetado'].sum():,.2f}")

st.markdown("---")

# --- GRÁFICO ---
st.subheader("🗓️ Cronograma de Desembolso Mensal (Fluxo de Caixa Diluído)")
linhas_fluxo_calculado = []

for _, row in df_original.iterrows():
    custo_item = row['custo_atual_projetado']
    try:
        dt_base = pd.to_datetime(row['data_vencimento'])
    except:
        dt_base = pd.to_datetime(datetime.today().strftime('%Y-%m-%d'))
        
    condicao = row['condicao_pagamento']
    n_parcelas = int(row['qtd_parcelas']) if row['qtd_parcelas'] > 0 else 1
    
    if condicao == "Parcelado" and n_parcelas > 1:
        valor_parcela = custo_item / n_parcelas
        for i in range(n_parcelas):
            dt_futura = dt_base + pd.DateOffset(months=i)
            mes_ano_str = dt_futura.strftime('%Y-%m (%B)')
            linhas_fluxo_calculado.append({'mes_vencimento': mes_ano_str, 'valor_mes': valor_parcela})
    else:
        mes_ano_str = dt_base.strftime('%Y-%m (%B)')
        linhas_fluxo_calculado.append({'mes_vencimento': mes_ano_str, 'valor_mes': custo_item})

if linhas_fluxo_calculado:
    df_fluxo_processado = pd.DataFrame(linhas_fluxo_calculado)
    fluxo_caixa_sumario = df_fluxo_processado.groupby('mes_vencimento')['valor_mes'].sum().reset_index()
    fluxo_caixa_sumario = fluxo_caixa_sumario.sort_values(by='mes_vencimento')
    st.bar_chart(data=fluxo_caixa_sumario, x='mes_vencimento', y='valor_mes', use_container_width=True)

st.markdown("---")

# --- CENTRAL DE ARQUIVOS (VISUALIZAR, ADICIONAR MÚLTIPLOS E DELETAR) ---
st.subheader("📁 Central de Arquivos & Contratos (Múltiplos Anexos por Item)")

col_sel_item, col_upload_file = st.columns([5, 5])
with col_sel_item:
    opcoes_itens = {f"ID {row['id']} - {row['item']}": row['id'] for _, row in df_original.iterrows()}
    item_selecionado_label = st.selectbox("Selecione o item correspondente da obra:", list(opcoes_itens.keys()))
    id_item_upload = opcoes_itens[item_selecionado_label] if opcoes_itens else None

# Filtra arquivos específicos do ID selecionado
arquivos_desse_id = []
if id_item_upload:
    prefixo_procurado = f"ID_{id_item_upload}_"
    arquivos_desse_id = [f for f in lista_arquivos_drive if f.get('name', '').startswith(prefixo_procurado)]

with col_upload_file:
    arquivo_anexado = st.file_uploader("Adicionar novo arquivo para este item:", type=['pdf', 'png', 'jpg', 'jpeg'])
    if st.button("🚀 Confirmar e Enviar para o Drive") and arquivo_anexado and id_item_upload:
        with st.spinner("A carregar ficheiro para a nuvem..."):
            nome_limpo = arquivo_anexado.name.replace("_", "-")
            nome_seguro_arquivo = f"ID_{id_item_upload}_{nome_limpo}"
            upload_file_to_drive(arquivo_anexado, nome_seguro_arquivo)
            st.success(f"🎉 Arquivo adicionado à pasta!")
            time.sleep(0.5)
            st.rerun()

# Listagem de arquivos com botão de exclusão
if arquivos_desse_id:
    st.markdown("##### 📄 Arquivos já anexados a este item:")
    for arq in arquivos_desse_id:
        col_nome_arq, col_btn_open, col_btn_del = st.columns([6, 2, 2])
        nome_exibicao = arq['name'].replace(f"ID_{id_item_upload}_", "")
        
        col_nome_arq.write(f"📄 {nome_exibicao}")
        col_btn_open.markdown(f"[🔗 Abrir Arquivo]({arq['webViewLink']})")
        
        if col_btn_del.button("🗑️ Deletar", key=f"del_{arq['id']}", type="secondary"):
            with st.spinner("Apagando arquivo..."):
                if delete_file_from_drive(arq['id']):
                    st.toast("Arquivo removido permanentemente!", icon="🗑️")
                    time.sleep(0.5)
                    st.rerun()
else:
    st.info("ℹ️ Nenhum arquivo anexado a este item ainda.")

st.markdown("---")

# --- PLANILHA CLOUD (UX OPTIMIZED - COMPACT PIXELS) ---
st.subheader("📋 Matriz Geral de Controle da Reforma (Sincronizada em Nuvem)")

if not df_filtrado.empty:
    df_editor = df_filtrado.copy()
    if 'custo_atual_projetado' in df_editor.columns:
        df_editor = df_editor.drop(columns=['custo_atual_projetado'])
    if 'arquivo_url' in df_editor.columns:
        df_editor = df_editor.drop(columns=['arquivo_url'])
        
    df_editor['data_vencimento'] = pd.to_datetime(df_editor['data_vencimento']).dt.date

    # Injeta a contagem textual de anexos
    df_editor['Anexos'] = df_editor['id'].apply(
        lambda idx: f"📁 {arquivos_contagem[str(idx)]}" if str(idx) in arquivos_contagem else "➖"
    )

    # 📍 PASSO 1: Injeta a coluna booleana de seleção interativa no início da tabela
    if "Selec." not in df_editor.columns:
        df_editor.insert(0, "Selec.", False)

    # Reordena colunas para exibição limpa (incluindo o Selec.)
    colunas_ordenadas = [
        "Selec.", "id", "item", "fase", "comodo", "categoria", "status", 
        "valor_estimado", "valor_real", "fornecedor", "data_vencimento", 
        "meio_pagamento", "condicao_pagamento", "qtd_parcelas", "Anexos", "data_atualizacao"
    ]
    df_editor = df_editor[colunas_ordenadas]

    # Renderização da tabela principal
    edited_df = st.data_editor(
        df_editor,
        column_config={
            "Selec.": st.column_config.CheckboxColumn("📍", default=False, width=35),
            "id": st.column_config.NumberColumn("ID", disabled=True, width=35),
            "item": st.column_config.TextColumn("Item / Atividade", required=True, width=180),
            "fase": st.column_config.SelectboxColumn("Fase da Obra", options=FASES, required=True, width=208),
            "comodo": st.column_config.SelectboxColumn("Cômodo", options=COMODOS, required=True, width=100),
            "categoria": st.column_config.SelectboxColumn("Cat.", options=CATEGORIAS, width=60),
            "status": st.column_config.SelectboxColumn("Status", options=STATUS_OPCOES, required=True, width=110),
            "valor_estimado": st.column_config.NumberColumn("Est.(R$)", format="R$ %.2f", min_value=0.0, width=80),
            "valor_real": st.column_config.NumberColumn("Real(R$)", format="R$ %.2f", min_value=0.0, width=80),
            "fornecedor": st.column_config.TextColumn("Fornecedor", width=90),
            "data_vencimento": st.column_config.DateColumn("Venc.", format="DD/MM/YYYY", required=True, width=75),
            "meio_pagamento": st.column_config.SelectboxColumn("Meio", options=MEIOS_PAGAMENTO, required=True, width=70),
            "condicao_pagamento": st.column_config.SelectboxColumn("Cond.", options=CONDICOES_PAGAMENTO, required=True, width=70),
            "qtd_parcelas": st.column_config.NumberColumn("Parc.", min_value=1, step=1, format="%d", required=True, width=45),
            "Anexos": st.column_config.TextColumn("Docs", disabled=True, width=55),
            "data_atualizacao": st.column_config.TextColumn("Modificado", disabled=True, width=80)
        },
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        key="matriz_editor"
    )
    
    # 📍 PASSO 2: Varre se existe alguma linha selecionada pelo usuário para liberar a Action Bar
    linhas_selecionadas_existentes = edited_df[edited_df['Selec.'] == True] if 'Selec.' in edited_df.columns else pd.DataFrame()
    algum_selecionado = not linhas_selecionadas_existentes.empty

    # 📍 PASSO 3: RENDERIZAÇÃO DA BARRA DE AÇÕES DINÂMICA (ACTION BAR)
    col_act1, col_act2, col_act3, col_act4 = st.columns([2.5, 2.5, 4, 3])
    
    with col_act1:
        btn_excluir_linhas = st.button("❌ Excluir Marcados", disabled=not algum_selecionado, type="secondary", use_container_width=True, help="Remove permanentemente as linhas marcadas da nuvem.")
    with col_act2:
        btn_duplicar_linhas = st.button("👥 Duplicar Marcados", disabled=not algum_selecionado, type="secondary", use_container_width=True, help="Cria uma cópia exata de cada linha marcada gerando novos IDs.")
    with col_act4:
        btn_salvar_geral = st.button("💾 Salvar Planilha Geral", type="primary", use_container_width=True, help="Sincroniza todas as edições de texto feitas nas colunas para o Google Sheets.")

    # Lógica de Exclusão Direta na Nuvem
    if btn_excluir_linhas:
        with st.spinner("Removendo itens selecionados da nuvem..."):
            linhas_restantes = edited_df[edited_df['Selec.'] == False]
            all_rows = worksheet.get_all_values()
            headers = all_rows[0]
            worksheet.clear()
            worksheet.append_row(headers)
            
            novas_linhas = []
            for index, row in linhas_restantes.iterrows():
                venc_val = row.get('data_vencimento')
                venc_str = venc_val.strftime('%Y-%m-%d') if pd.notna(venc_val) else datetime.today().strftime('%Y-%m-%d')
                cond_txt = row.get('condicao_pagamento', 'À vista')
                parcelas_val = int(row.get('qtd_parcelas', 1)) if cond_txt == "Parcelado" else 1
                
                novas_linhas.append([
                    str(row['id']), str(row.get('item', 'Novo Item')), str(row.get('fase', FASES[0])),
                    str(row.get('comodo', COMODOS[0])), str(row.get('categoria', CATEGORIAS[0])), str(row.get('status', STATUS_OPCOES[0])),
                    str(row.get('valor_estimado', 0.0)), str(row.get('valor_real', 0.0)), str(row.get('fornecedor', '')),
                    datetime.today().strftime('%Y-%m-%d'), venc_str, str(row.get('meio_pagamento', 'Pix')),
                    str(cond_txt), str(parcelas_val), ""
                ])
            if novas_linhas:
                worksheet.append_rows(novas_linhas, value_input_option="USER_ENTERED")
            st.toast("Linhas excluídas com sucesso!", icon="🗑️")
            time.sleep(0.5)
            st.rerun()

    # Lógica de Duplicação Direta na Nuvem
    if btn_duplicar_linhas:
        with st.spinner("Duplicando itens na nuvem..."):
            dataset_completo = edited_df.copy()
            try:
                maior_id_atual = int(df_original['id'].astype(int).max())
            except:
                maior_id_atual = 1
                
            for _, row_para_copiar in linhas_selecionadas_existentes.iterrows():
                maior_id_atual += 1
                nova_copia = row_para_copiar.copy()
                nova_copia['id'] = str(maior_id_atual)
                nova_copia['item'] = f"{nova_copia['item']} (Cópia)"
                nova_copia['Selec.'] = False
                dataset_completo = pd.concat([dataset_completo, pd.DataFrame([nova_copia])], ignore_index=True)
                
            all_rows = worksheet.get_all_values()
            headers = all_rows[0]
            worksheet.clear()
            worksheet.append_row(headers)
            
            novas_linhas = []
            for index, row in dataset_completo.iterrows():
                venc_val = row.get('data_vencimento')
                venc_str = venc_val.strftime('%Y-%m-%d') if pd.notna(venc_val) else datetime.today().strftime('%Y-%m-%d')
                cond_txt = row.get('condicao_pagamento', 'À vista')
                parcelas_val = int(row.get('qtd_parcelas', 1)) if cond_txt == "Parcelado" else 1
                
                novas_linhas.append([
                    str(row['id']), str(row.get('item', 'Novo Item')), str(row.get('fase', FASES[0])),
                    str(row.get('comodo', COMODOS[0])), str(row.get('categoria', CATEGORIAS[0])), str(row.get('status', STATUS_OPCOES[0])),
                    str(row.get('valor_estimado', 0.0)), str(row.get('valor_real', 0.0)), str(row.get('fornecedor', '')),
                    datetime.today().strftime('%Y-%m-%d'), venc_str, str(row.get('meio_pagamento', 'Pix')),
                    str(cond_txt), str(parcelas_val), ""
                ])
            if novas_linhas:
                worksheet.append_rows(novas_linhas, value_input_option="USER_ENTERED")
            st.toast("Itens duplicados com sucesso!", icon="👥")
            time.sleep(0.5)
            st.rerun()

    # Lógica do Botão de Salvar Geral (Atualizações textuais comuns)
    if btn_salvar_geral:
        with st.spinner("A guardar dados na Planilha Google..."):
            all_rows = worksheet.get_all_values()
            headers = all_rows[0]
            worksheet.clear()
            worksheet.append_row(headers)
            
            novas_linhas = []
            for index, row in edited_df.iterrows():
                venc_val = row.get('data_vencimento')
                venc_str = venc_val.strftime('%Y-%m-%d') if pd.notna(venc_val) else datetime.today().strftime('%Y-%m-%d')
                cond_txt = row.get('condicao_pagamento', 'À vista')
                parcelas_val = int(row.get('qtd_parcelas', 1)) if cond_txt == "Parcelado" else 1
                
                novas_linhas.append([
                    str(row['id']) if pd.notna(row.get('id')) and str(row.get('id')).strip() != "" else str(index+1),
                    str(row.get('item', 'Novo Item')),
                    str(row.get('fase', FASES[0])),
                    str(row.get('comodo', COMODOS[0])),
                    str(row.get('categoria', CATEGORIAS[0])),
                    str(row.get('status', STATUS_OPCOES[0])),
                    str(row.get('valor_estimado', 0.0)),
                    str(row.get('valor_real', 0.0)),
                    str(row.get('fornecedor', '')),
                    datetime.today().strftime('%Y-%m-%d'),
                    venc_str,
                    str(row.get('meio_pagamento', 'Pix')),
                    str(cond_txt),
                    str(parcelas_val),
                    ""
                ])
                
            if novas_linhas:
                worksheet.append_rows(novas_linhas, value_input_option="USER_ENTERED")
            st.success("🔒 Sincronização Concluída!")
            time.sleep(1)
            st.rerun()
else:
    st.info("Nenhum item encontrado.")
