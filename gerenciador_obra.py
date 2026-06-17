import streamlit as st
import pandas as pd
import gspread
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials
import io
import os
import time
from datetime import datetime

# Configuração da página do Streamlit (Sidebar recolhida por padrão)
st.set_page_config(
    page_title="Gestor de Obra Inteligente",
    page_icon="🚧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CONFIGURAÇÃO DE CAMINHOS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

# Link real da sua planilha e Pasta de Anexos do Google Drive
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1EQaZqr1Mn4OcP0Y55S5VxwmZPnZfTeMyKCJmq2BPS3o/edit"
ANEXOS_FOLDER_ID = "14leb6weZguOux5HMcaovmonLNN3kw2_M"

@st.cache_resource
def get_google_services():
    """Autentica via OAuth2 e abre os recursos da planilha uma única vez em cache de conexão."""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    try:
        oauth_secrets = st.secrets.get("oauth")
    except:
        oauth_secrets = None

    if oauth_secrets:
        creds = Credentials(
            None,
            refresh_token=oauth_secrets["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=oauth_secrets["client_id"],
            client_secret=oauth_secrets["client_secret"],
            scopes=scopes
        )
    else:
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes)
        else:
            st.error("❌ Credenciais de acesso local ou em nuvem não foram encontradas!")
            st.stop()
            
    gc = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    
    try:
        sh = gc.open_by_url(SPREADSHEET_URL)
        worksheet = sh.get_worksheet(0)
    except Exception as e:
        st.error(f"Erro crítico ao abrir a estrutura da planilha no Google: {e}")
        st.stop()
        
    return gc, drive_service, worksheet

# Inicialização global das conexões por cache de recurso
try:
    gc, drive_service, worksheet = get_google_services()
except Exception as e:
    st.error(f"❌ Erro de conexão com a API do Google: {e}")
    st.stop()

@st.cache_data(ttl=600)
def load_cloud_data():
    """Lê todas as linhas cadastradas na Planilha Google e guarda em cache por performance."""
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    if not df.empty:
        df['id'] = df['id'].astype(str)
        df['valor_estimado'] = pd.to_numeric(df['valor_estimado'], errors='coerce').fillna(0.0)
        df['valor_real'] = pd.to_numeric(df['valor_real'], errors='coerce').fillna(0.0)
        df['qtd_parcelas'] = pd.to_numeric(df['qtd_parcelas'], errors='coerce').fillna(1).astype(int)
    else:
        df = pd.DataFrame(columns=[
            "id", "item", "fase", "comodo", "categoria", "status", 
            "valor_estimado", "valor_real", "fornecedor", "data_atualizacao", 
            "data_vencimento", "meio_pagamento", "condicao_pagamento", "qtd_parcelas", "arquivo_url"
        ])
    return df

@st.cache_data(ttl=600)
def get_drive_files_inventory():
    """Mapeia os anexos do Drive e armazena em cache para evitar travar a navegação."""
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

# --- DOMÍNIOS DE DADOS FIXOS ---
FASES = [
    "1. Infraestrutura Bruta", 
    "2. Gesso e Drywall", 
    "3. Revestimentos e Pisos", 
    "4. Marcenaria e Pedras", 
    "5. Pintura e Acabamento", 
    "6. Iluminação e Elétrica Fina",
    "7. Mobiliário e Equipamentos"
]
COMODOS = ["Geral / Todos", "Sala de Estar", "Cozinha", "Lavanderia", "Suíte Principal", "Quarto 2", "Banheiro Social", "Varanda Gourmet"]
STATUS_OPCOES = ["Não Iniciado", "Em Orçamento", "Orçamento Selecionado", "Orçamento Recusado", "Contratado / Comprado", "Em Execução / Entrega", "Concluído & Pago"]
CATEGORIAS = ["Material", "Serviço", "Material/Serviço"]
MEIOS_PAGAMENTO = ["Pix", "Cartão de Crédito", "Boleto"]
CONDICOES_PAGAMENTO = ["À vista", "Parcelado"]

# --- CARREGAMENTO DE DADOS ---
lista_arquivos_drive = get_drive_files_inventory()
df_original = load_cloud_data()

arquivos_contagem = {}
for f in lista_arquivos_drive:
    name_str = f.get('name', '')
    if name_str.startswith("ID_"):
        parts = name_str.split("_")
        if len(parts) > 1:
            arquivos_contagem[parts[1]] = arquivos_contagem.get(parts[1], 0) + 1

df_original['custo_atual_projetado'] = df_original.apply(
    lambda r: r['valor_real'] if r['status'] in ["Orçamento Selecionado", "Contratado / Comprado", "Em Execução / Entrega", "Concluído & Pago"] and r['valor_real'] > 0 else r['valor_estimado'], 
    axis=1
)

try:
    df_original['mes_venc_filtro'] = pd.to_datetime(df_original['data_vencimento'], errors='coerce').dt.strftime('%Y-%m')
    df_original['mes_venc_filtro'] = df_original['mes_venc_filtro'].fillna(datetime.today().strftime('%Y-%m'))
except:
    df_original['mes_venc_filtro'] = datetime.today().strftime('%Y-%m')
opcoes_meses = sorted(df_original['mes_venc_filtro'].dropna().unique())

# --- INTERFACE VISUAL ---
st.markdown('<h2 style="color:#1E3A8A; margin-bottom: 5px;">🚧 Gestor de Obra & Suprimentos Cloud</h2>', unsafe_allow_html=True)

# PROCESSAMENTO PRÉVIO DE FILTROS
if 'filtro_fase_sel' not in st.session_state: st.session_state.filtro_fase_sel = []
if 'filtro_comodo_sel' not in st.session_state: st.session_state.filtro_comodo_sel = []
if 'filtro_cat_sel' not in st.session_state: st.session_state.filtro_cat_sel = []
if 'filtro_status_sel' not in st.session_state: st.session_state.filtro_status_sel = []
if 'filtro_venc_sel' not in st.session_state: st.session_state.filtro_venc_sel = []

df_filtrado = df_original.copy()
if st.session_state.filtro_fase_sel: df_filtrado = df_filtrado[df_filtrado['fase'].isin(st.session_state.filtro_fase_sel)]
if st.session_state.filtro_comodo_sel: df_filtrado = df_filtrado[df_filtrado['comodo'].isin(st.session_state.filtro_comodo_sel)]
if st.session_state.filtro_cat_sel: df_filtrado = df_filtrado[df_filtrado['categoria'].isin(st.session_state.filtro_cat_sel)]
if st.session_state.filtro_status_sel: df_filtrado = df_filtrado[df_filtrado['status'].isin(st.session_state.filtro_status_sel)]
if st.session_state.filtro_venc_sel: df_filtrado = df_filtrado[df_filtrado['mes_venc_filtro'].isin(st.session_state.filtro_venc_sel)]

# ALGORITMO DE DEDUPLICAÇÃO DE ORÇAMENTOS PARA KPIs
df_limpo_calculo = df_filtrado[df_filtrado['status'] != "Orçamento Recusado"].copy()

def filtrar_melhor_opcao_orcamento(group):
    status_vencedores = ["Orçamento Selecionado", "Contratado / Comprado", "Em Execução / Entrega", "Concluído & Pago"]
    vencedores = group[group['status'].isin(status_vencedores)]
    if not vencedores.empty:
        return vencedores.head(1)
    return group.sort_values(by='custo_atual_projetado').head(1)

if not df_limpo_calculo.empty:
    df_kpi = df_limpo_calculo.groupby(['item', 'comodo'], as_index=False).apply(filtrar_melhor_opcao_orcamento).reset_index(drop=True)
else:
    df_kpi = df_limpo_calculo.copy()

# INDICADORES GLOBAIS COMPACTOS
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
total_orcado = df_kpi['valor_estimado'].sum()
total_comprometido = df_kpi[df_kpi['status'].isin(['Contratado / Comprado', 'Em Execução / Entrega', 'Concluído & Pago'])]['valor_real'].sum()
total_projetado = df_kpi['custo_atual_projetado'].sum()

total_itens = len(df_kpi)
itens_concluidos = len(df_kpi[df_kpi['status'] == "Concluído & Pago"])
pct_progresso = (itens_concluidos / total_itens * 100) if total_itens > 0 else 0.0

desvio = total_projetado - total_orcado
delta_label = f"R$ {desvio:,.2f}" if desvio == 0 else (f"⚠️ Estouro: R$ {desvio:,.2f}" if desvio > 0 else f"📉 Economia: R$ {abs(desvio):,.2f}")

kpi1.metric("💰 Orçamento Planejado", f"R$ {total_orcado:,.2f}")
kpi2.metric("💸 Gasto Comprometido", f"R$ {total_comprometido:,.2f}")
kpi3.metric("📉 Projeção Final Custo", f"R$ {total_projetado:,.2f}", delta=delta_label, delta_color="inverse")
kpi4.metric("🏗️ Progresso Físico", f"{pct_progresso:.1f}%", f"{itens_concluidos} de {total_itens} itens concluídos")

st.markdown("<hr style='margin-top: 5px; margin-bottom: 15px;'/>", unsafe_allow_html=True)

# LINHA DE FILTROS HORIZONTAIS
col_f1, col_f2, col_f3, col_f4, col_f5, col_btn = st.columns([2.2, 1.8, 1.4, 1.8, 1.4, 1.6])
with col_f1: st.session_state.filtro_fase_sel = st.multiselect("🏗️ Fase:", FASES, key="f_fase")
with col_f2: st.session_state.filtro_comodo_sel = st.multiselect("🏠 Cômodo:", COMODOS, key="f_com")
with col_f3: st.session_state.filtro_cat_sel = st.multiselect("🏷️ Cat.:", CATEGORIAS, key="f_cat")
with col_f4: st.session_state.filtro_status_sel = st.multiselect("🚦 Status:", STATUS_OPCOES, key="f_stat")
with col_f5: st.session_state.filtro_venc_sel = st.multiselect("📅 Data Ref. (Mês):", opcoes_meses, key="f_venc")
with col_btn:
    st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
    if st.button("➕ Incluir Item", type="primary", use_container_width=True):
        st.session_state.abrir_modal = not st.session_state.get("abrir_modal", False)

# --- MODAL EXPANSÍVEL DE INCLUSÃO ---
if st.session_state.get("abrir_modal", False):
    st.markdown("<div style='padding: 15px; border: 1px solid #1E3A8A; border-radius: 8px; margin-bottom: 20px;'>", unsafe_allow_html=True)
    st.markdown("<h4 style='color:#1E3A8A; margin-top:0;'>📝 Cadastro de Novo Item / Atividade</h4>", unsafe_allow_html=True)
    with st.form("form_modal_inclusao", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        novo_item = c1.text_input("Nome do Item/Serviço:")
        nova_fase = c1.selectbox("Fase da Obra:", FASES)
        novo_comodo = c1.selectbox("Cômodo:", COMODOS)
        nova_cat = c2.selectbox("Categoria:", CATEGORIAS)
        novo_status = c2.selectbox("Status Inicial:", STATUS_OPCOES)
        val_est = c2.number_input("Valor Estimado (R$):", min_value=0.0, format="%.2f")
        val_real = c3.number_input("Valor Real Fechado (R$):", min_value=0.0, format="%.2f")
        fornec = c3.text_input("Fornecedor:")
        dt_venc_raw = c3.date_input("Data Ref. (1º Vencimento):", value=datetime.today())
        c_p1, c_p2, c_p3 = st.columns(3)
        meio_p = c_p1.selectbox("Meio de Pagamento:", MEIOS_PAGAMENTO)
        condicao_p = c_p2.selectbox("Condição de Pagamento:", CONDICOES_PAGAMENTO)
        qtd_p = c_p3.number_input("Quantidade de Parcelas:", min_value=1, value=1, step=1)
        if st.form_submit_button("🚀 Gravar e Inserir no Google Sheets", use_container_width=True):
            if novo_item:
                try: novo_id = str(int(df_original['id'].astype(int).max() + 1))
                except: novo_id = "1"
                worksheet.append_row([str(novo_id), str(novo_item), str(nova_fase), str(novo_comodo), str(nova_cat), str(novo_status), float(val_est), str(val_real), str(fornec), datetime.today().strftime('%Y-%m-%d'), str(dt_venc_raw.strftime('%Y-%m-%d')), str(meio_p), str(condicao_p), int(1 if condicao_p == "À vista" else qtd_p), ""], value_input_option="USER_ENTERED")
                st.session_state.abrir_modal = False
                st.cache_data.clear()
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# --- NAVEGAÇÃO POR ABAS COESAS ---
tab_matriz, tab_arquivos, tab_dashboard = st.tabs([
    "📋 Matriz de Controle da Reforma", 
    "📁 Central de Arquivos & Contratos", 
    "📊 Fluxo de Caixa Diluído"
])

# === ABA 1: MATRIZ DE CONTROLE ===
with tab_matriz:
    if not df_filtrado.empty:
        df_editor = df_filtrado.copy()
        for col in ['custo_atual_projetado', 'arquivo_url', 'mes_venc_filtro']:
            if col in df_editor.columns: df_editor = df_editor.drop(columns=[col])
        df_editor['data_vencimento'] = pd.to_datetime(df_editor['data_vencimento']).dt.date
        df_editor['Anexos'] = df_editor['id'].apply(lambda idx: f"📁 {arquivos_contagem[str(idx)]}" if str(idx) in arquivos_contagem else "➖")
        if "Selec." not in df_editor.columns: df_editor.insert(0, "Selec.", False)
        
        colunas_ordenadas = ["Selec.", "id", "item", "fase", "comodo", "categoria", "status", "valor_estimado", "valor_real", "fornecedor", "data_vencimento", "meio_pagamento", "condicao_pagamento", "qtd_parcelas", "Anexos", "data_atualizacao"]
        df_editor = df_editor[colunas_ordenadas]

        # 🎯 MUDANÇA PARA TRATAMENTO DE ORDENAÇÃO INTERATIVA DE ALTA PERFORMANCE (num_rows="fixed")
        edited_df = st.data_editor(
            df_editor,
            column_config={
                "Selec.": st.column_config.CheckboxColumn("📍", default=False, width=25),
                "id": None, # Continua ocultado visualmente, preservado internamente
                "item": st.column_config.TextColumn("Item / Atividade", required=True, width=180),
                "fase": st.column_config.SelectboxColumn("Fase da Obra", options=FASES, required=True, width=185),
                "comodo": st.column_config.SelectboxColumn("Cômodo", options=COMODOS, required=True, width=120),
                "categoria": st.column_config.SelectboxColumn("Cat.", options=CATEGORIAS, width=60),
                "status": st.column_config.SelectboxColumn("Status", options=STATUS_OPCOES, required=True, width=110),
                "valor_estimado": st.column_config.NumberColumn("Est.(R$)", format="R$ %.2f", min_value=0.0, width=85),
                "valor_real": st.column_config.NumberColumn("Real(R$)", format="R$ %.2f", min_value=0.0, width=85),
                "fornecedor": st.column_config.TextColumn("Fornecedor", width=90),
                "data_vencimento": st.column_config.DateColumn("Data Ref.", format="DD/MM/YYYY", required=True, width=85),
                "meio_pagamento": st.column_config.SelectboxColumn("Meio", options=MEIOS_PAGAMENTO, required=True, width=70),
                "condicao_pagamento": st.column_config.SelectboxColumn("Cond.", options=CONDICOES_PAGAMENTO, required=True, width=70),
                "qtd_parcelas": st.column_config.NumberColumn("Parc.", min_value=1, step=1, format="%d", required=True, width=45),
                "Anexos": st.column_config.TextColumn("Docs", disabled=True, width=40),
                "data_atualizacao": st.column_config.TextColumn("Modificado", disabled=True, width=60)
            },
            hide_index=True, 
            num_rows="fixed", # 🔓 O SEGREDO DO DESBLOQUEIO ESTÁ AQUI! Ativa a ordenação nativa por clique no cabeçalho.
            use_container_width=True, 
            key="matriz_editor"
        )
        
        linhas_selecionadas_existentes = edited_df[edited_df['Selec.'] == True] if 'Selec.' in edited_df.columns else pd.DataFrame()
        algum_selecionado = not linhas_selecionadas_existentes.empty

        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
        col_act1, col_act2, col_act3, col_act4 = st.columns([2.5, 2.5, 4, 3])
        with col_act1: btn_excluir_linhas = st.button("❌ Excluir Marcados", disabled=not algum_selecionado, use_container_width=True)
        with col_act2: btn_duplicar_linhas = st.button("👥 Duplicar Marcados", disabled=not algum_selecionado, use_container_width=True)
        with col_act4: btn_salvar_geral = st.button("💾 Salvar Planilha Geral", type="primary", use_container_width=True)

        if btn_excluir_linhas:
            with st.spinner("Removendo itens..."):
                linhas_restantes = edited_df[edited_df['Selec.'] == False]
                worksheet.clear()
                worksheet.append_row(["id", "item", "fase", "comodo", "categoria", "status", "valor_estimado", "valor_real", "fornecedor", "data_atualizacao", "data_vencimento", "meio_pagamento", "condicao_pagamento", "qtd_parcelas", "arquivo_url"])
                novas_linhas = [[str(r['id']), str(r.get('item', 'Novo Item')), str(r.get('fase', FASES[0])), str(r.get('comodo', COMODOS[0])), str(r.get('categoria', CATEGORIAS[0])), str(r.get('status', STATUS_OPCOES[0])), str(r.get('valor_estimado', 0.0)), str(r.get('valor_real', 0.0)), str(r.get('fornecedor', '')), datetime.today().strftime('%Y-%m-%d'), r.get('data_vencimento').strftime('%Y-%m-%d') if pd.notna(r.get('data_vencimento')) else datetime.today().strftime('%Y-%m-%d'), str(r.get('meio_pagamento', 'Pix')), str(r.get('condicao_pagamento', 'À vista')), str(r.get('qtd_parcelas', 1)), ""] for _, r in linhas_restantes.iterrows()]
                if novas_linhas: worksheet.append_rows(novas_linhas, value_input_option="USER_ENTERED")
                st.cache_data.clear()
                st.rerun()

        if btn_duplicar_linhas:
            with st.spinner("Duplicando itens..."):
                dataset_completo = edited_df.copy()
                try: maior_id_atual = int(df_original['id'].astype(int).max())
                except: maior_id_atual = 1
                for _, row_para_copiar in linhas_selecionadas_existentes.iterrows():
                    maior_id_atual += 1
                    nova_copia = row_para_copiar.copy()
                    nova_copia['id'] = str(maior_id_atual)
                    nova_copia['item'] = f"{nova_copia['item']} (Cópia)"
                    nova_copia['Selec.'] = False
                    dataset_completo = pd.concat([dataset_completo, pd.DataFrame([nova_copia])], ignore_index=True)
                worksheet.clear()
                worksheet.append_row(["id", "item", "fase", "comodo", "categoria", "status", "valor_estimado", "valor_real", "fornecedor", "data_atualizacao", "data_vencimento", "meio_pagamento", "condicao_pagamento", "qtd_parcelas", "arquivo_url"])
                novas_linhas = [[str(r['id']), str(r.get('item', 'Novo Item')), str(r.get('fase', FASES[0])), str(r.get('comodo', COMODOS[0])), str(r.get('categoria', CATEGORIAS[0])), str(r.get('status', STATUS_OPCOES[0])), str(r.get('valor_estimado', 0.0)), str(r.get('valor_real', 0.0)), str(r.get('fornecedor', '')), datetime.today().strftime('%Y-%m-%d'), r.get('data_vencimento').strftime('%Y-%m-%d') if pd.notna(r.get('data_vencimento')) else datetime.today().strftime('%Y-%m-%d'), str(r.get('meio_pagamento', 'Pix')), str(r.get('condicao_pagamento', 'À vista')), str(r.get('qtd_parcelas', 1)), ""] for _, r in dataset_completo.iterrows()]
                if novas_linhas: worksheet.append_rows(novas_linhas, value_input_option="USER_ENTERED")
                st.cache_data.clear()
                st.rerun()

        if btn_salvar_geral:
            with st.spinner("Sincronizando modificações..."):
                worksheet.clear()
                worksheet.append_row(["id", "item", "fase", "comodo", "categoria", "status", "valor_estimado", "valor_real", "fornecedor", "data_atualizacao", "data_vencimento", "meio_pagamento", "condicao_pagamento", "qtd_parcelas", "arquivo_url"])
                novas_linhas = [[str(r['id']) if pd.notna(r.get('id')) and str(r.get('id')).strip() != "" else str(idx+1), str(r.get('item', 'Novo Item')), str(r.get('fase', FASES[0])), str(r.get('comodo', COMODOS[0])), str(r.get('categoria', CATEGORIAS[0])), str(r.get('status', STATUS_OPCOES[0])), str(r.get('valor_estimado', 0.0)), str(r.get('valor_real', 0.0)), str(r.get('fornecedor', '')), datetime.today().strftime('%Y-%m-%d'), r.get('data_vencimento').strftime('%Y-%m-%d') if pd.notna(r.get('data_vencimento')) else datetime.today().strftime('%Y-%m-%d'), str(r.get('meio_pagamento', 'Pix')), str(r.get('condicao_pagamento', 'À vista')), str(r.get('qtd_parcelas', 1)), ""] for idx, r in edited_df.iterrows()]
                if novas_linhas: worksheet.append_rows(novas_linhas, value_input_option="USER_ENTERED")
                st.success("🔒 Sincronizado!")
                time.sleep(0.5)
                st.cache_data.clear()
                st.rerun()
    else: st.info("Nenhum registro encontrado correspondente aos filtros.")

# === ABA 2: CENTRAL DE ARQUIVOS ===
with tab_arquivos:
    st.markdown("#### 📁 Gerenciador de Arquivos, Contratos e Notas Fiscais")
    col_sel_item, col_upload_file = st.columns([5, 5])
    with col_sel_item:
        opcoes_itens = {f"ID {row['id']} - {row['item']}": row['id'] for _, row in df_original.iterrows()}
        item_selecionado_label = st.selectbox("Selecione o item correspondente da obra para gerenciar:", list(opcoes_itens.keys()))
        id_item_upload = opcoes_itens[item_selecionado_label] if opcoes_itens else None

    arquivos_desse_id = [f for f in lista_arquivos_drive if f.get('name', '').startswith(f"ID_{id_item_upload}_")] if id_item_upload else []

    with col_upload_file:
        arquivo_anexado = st.file_uploader("Adicionar novo arquivo / PDF para este item:", type=['pdf', 'png', 'jpg', 'jpeg'])
        if st.button("🚀 Confirmar e Enviar para o Google Drive") and arquivo_anexado and id_item_upload:
            with st.spinner("Enviando..."):
                upload_file_to_drive(arquivo_anexado, f"ID_{id_item_upload}_{arquivo_anexado.name.replace('_', '-')}")
                st.success("🎉 Arquivo salvo!")
                time.sleep(0.5)
                st.cache_data.clear()
                st.rerun()

    st.markdown("---")
    if arquivos_desse_id:
        for arq in arquivos_desse_id:
            col_nome_arq, col_btn_open, col_btn_del = st.columns([6, 2, 2])
            col_nome_arq.write(f"📄 {arq['name'].replace(f'ID_{id_item_upload}_', '')}")
            col_btn_open.markdown(f"[🔗 Abrir Documento]({arq['webViewLink']})")
            if col_btn_del.button("🗑️ Deletar", key=f"del_{arq['id']}", type="secondary"):
                if delete_file_from_drive(arq['id']): 
                    st.cache_data.clear()
                    st.rerun()
    else: st.info("ℹ️ Nenhum arquivo anexado a este item.")

# === ABA 3: DASHBOARD FINANCEIRO ===
with tab_dashboard:
    st.markdown("##### 🗓️ Cronograma de Desembolso Mensal (Fluxo de Caixa Diluído por Parcelas)")
    linhas_fluxo_calculado = []
    
    for _, row in df_kpi.iterrows():
        custo_item = row['custo_atual_projetado']
        try: dt_base = pd.to_datetime(row['data_vencimento'])
        except: dt_base = pd.to_datetime(datetime.today().strftime('%Y-%m-%d'))
        n_parcelas = int(row['qtd_parcelas']) if row['qtd_parcelas'] > 1 else 1
        
        if row['condicao_pagamento'] == "Parcelado" and n_parcelas > 1:
            for i in range(n_parcelas):
                linhas_fluxo_calculado.append({'mes_vencimento': (dt_base + pd.DateOffset(months=i)).strftime('%Y-%m (%B)'), 'valor_mes': (custo_item / n_parcelas)})
        else:
            linhas_fluxo_calculado.append({'mes_vencimento': dt_base.strftime('%Y-%m (%B)'), 'valor_mes': custo_item})

    if linhas_fluxo_calculado:
        fluxo_caixa_sumario = pd.DataFrame(linhas_fluxo_calculado).groupby('mes_vencimento')['valor_mes'].sum().reset_index().sort_values(by='mes_vencimento')
        st.bar_chart(data=fluxo_caixa_sumario, x='mes_vencimento', y='valor_mes', use_container_width=True)
    else: st.info("Sem dados suficientes para consolidação de fluxo de caixa.")
