import streamlit as st
import pandas as pd
import random
import hashlib
import re
from bs4 import BeautifulSoup
from io import StringIO

# --- CONFIGURAÇÕES GERAIS ---
DIAS_SEMANA = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]
HORARIOS = list(range(7, 24))  # 7:00 as 23:00

# Mapeamento de Dias do SIGAA (2=Segunda, ..., 7=Sábado)
MAPA_DIAS_SIGAA = {
    '2': 1, '3': 2, '4': 3, '5': 4, '6': 5, '7': 6
}

# Mapeamento de Turnos e Horários do SIGAA para Hora Real (Início)
# M1=07h, M2=08h... T1=13h... N1=19h (ajustável)
MAPA_HORA_SIGAA = {
    'M': { '1': 7, '2': 8, '3': 9, '4': 10, '5': 11 },
    'T': { '1': 13, '2': 14, '3': 15, '4': 16, '5': 17, '6': 18 },
    'N': { '1': 19, '2': 20, '3': 21, '4': 22 }
}

# --- FUNÇÕES DE PARSING E CONVERSÃO (NOVO) ---

def parse_sigaa_horario(horario_str):
    """
    Converte strings como '35M23' ou '24T12 6M34' em uma lista de dicionários
    com formato: {'Dia': str, 'Inicio': int, 'Fim': int}
    """
    if not isinstance(horario_str, str) or not horario_str.strip():
        return []

    # Remove espaços extras e separa múltiplos horários (ex: "2M12 4T34")
    partes = horario_str.split()
    resultados = []

    # Regex para capturar grupos: (Dias)(Turno)(Horarios) ex: (35)(M)(23)
    regex = r"([2-7]+)([MTN])([1-6]+)"

    for parte in partes:
        match = re.match(regex, parte)
        if match:
            dias_chars, turno, horas_chars = match.groups()
            
            # Para cada dia mencionado no código (ex: 3 e 5)
            for d in dias_chars:
                dia_idx = MAPA_DIAS_SIGAA.get(d)
                if dia_idx is None: continue
                
                dia_nome = DIAS_SEMANA[dia_idx]
                
                # Converte horas chars ('23') para inteiros reais
                horas_reais = []
                for h in horas_chars:
                    h_real = MAPA_HORA_SIGAA.get(turno, {}).get(h)
                    if h_real is not None:
                        horas_reais.append(h_real)
                
                if horas_reais:
                    horas_reais.sort()
                    # Identifica blocos contíguos para criar (Inicio, Fim)
                    # Simplesmente pegamos min e max+1 para cada dia, assumindo continuidade
                    # Se houver buraco (ex: 8h e 11h), a lógica visual vai pintar tudo, 
                    # mas para matrícula simples funciona.
                    
                    # Vamos criar um registro por hora para facilitar a explosão depois
                    for h in horas_reais:
                         resultados.append({
                            'Dia': dia_nome,
                            'Inicio': h,
                            'Fim': h + 1 # Bloco de 1h
                        })
    return resultados

def extrair_dados_html(conteudo_html):
    """Lógica adaptada do adaptador.py para processar o HTML."""
    soup = BeautifulSoup(conteudo_html, 'html.parser')
    tabela = soup.find('table', id='lista-turmas')
    
    dados_extraidos = []
    disciplina_atual = ""

    if tabela:
        linhas = tabela.find_all('tr')
        for linha in linhas:
            classes = linha.get('class', [])
            
            # Cabeçalho da Disciplina
            if 'destaque' in classes:
                texto = linha.get_text(strip=True)
                disciplina_atual = texto.replace('(GRADUAÇÃO)', '').strip()
            
            # Linha da Turma
            elif ('linhaPar' in classes or 'linhaImpar' in classes):
                if 'display: none' in str(linha.get('style')):
                    continue
                
                colunas = linha.find_all('td')
                if len(colunas) > 7:
                    turma = colunas[1].get_text(strip=True)
                    docente = colunas[2].get_text(strip=True) # Pode ser usado no tooltip
                    horario = colunas[6].get_text(strip=True)
                    local = colunas[7].get_text(strip=True)
                    
                    if disciplina_atual:
                        # Processa o horário SIGAA imediatamente
                        blocos_processados = parse_sigaa_horario(horario)
                        
                        # Se não tiver horário definido (EAD ou A definir), ignora ou avisa
                        if not blocos_processados:
                            # Opcional: Adicionar turmas sem horário se quiser
                            continue

                        # Cria uma linha no DataFrame para CADA bloco de 1h
                        # Isso facilita a lógica de montar a grade depois
                        for bloco in blocos_processados:
                            dados_extraidos.append({
                                'Componente': disciplina_atual,
                                'Turma': turma,
                                'Docente': docente,
                                'Local': local,
                                'Dia': bloco['Dia'],
                                'Inicio': bloco['Inicio'],
                                'Fim': bloco['Fim'],
                                'Horario_Original': horario
                            })
                            
    return pd.DataFrame(dados_extraidos)

# --- FUNÇÕES DE LÓGICA DO APP ---

def inicializar_estado():
    if 'ofertas_db' not in st.session_state:
        st.session_state['ofertas_db'] = pd.DataFrame()
    if 'matricula' not in st.session_state:
        st.session_state['matricula'] = []

def gerar_cor_por_string(texto):
    hash_object = hashlib.md5(texto.encode())
    digest = hash_object.digest()
    r = (digest[0] % 128) + 127
    g = (digest[1] % 128) + 127
    b = (digest[2] % 128) + 127
    return '#%02X%02X%02X' % (r, g, b)

def verificar_problemas(nova_turma_blocos, nome_componente):
    alertas = []
    # 1. Conflito de Horário
    blocos_ocupados = set()
    for mat in st.session_state['matricula']:
        for bloco in mat['blocos']:
            blocos_ocupados.add(bloco)
            
    for novo_bloco in nova_turma_blocos:
        if novo_bloco in blocos_ocupados:
            dia_nome = DIAS_SEMANA[novo_bloco[0]]
            hora = novo_bloco[1]
            alertas.append(f"⚠️ Choque de horário: {dia_nome} às {hora}h.")
            break 

    # 2. Duplicidade
    for mat in st.session_state['matricula']:
        if mat['componente'] == nome_componente:
            alertas.append(f"⚠️ Atenção: Você já adicionou '{nome_componente}'.")
            break
            
    return alertas

def adicionar_turma_a_grade(nome, turma, docente, blocos_calculados):
    cor = gerar_cor_por_string(nome)
    nova_matricula = {
        'id_unique': f"{nome}_{turma}_{random.randint(1000,9999)}",
        'componente': nome,
        'turma': turma,
        'docente': docente,
        'blocos': blocos_calculados,
        'cor': cor
    }
    st.session_state['matricula'].append(nova_matricula)
    st.rerun()

def remover_matricula(id_unique):
    st.session_state['matricula'] = [
        m for m in st.session_state['matricula'] if m['id_unique'] != id_unique
    ]
    st.rerun()

def construir_grade_visual():
    df_visual = pd.DataFrame("", index=HORARIOS, columns=DIAS_SEMANA)
    df_style = pd.DataFrame("", index=HORARIOS, columns=DIAS_SEMANA)

    for item in st.session_state['matricula']:
        nome = item['componente']
        turma = item['turma']
        cor = item['cor']
        # Simplifica o nome para caber na grade (Pega as iniciais ou primeira palavra)
        nome_curto = nome.split('-')[0].strip() if '-' in nome else nome
        
        for dia_idx, hora in item['blocos']:
            if 7 <= hora <= 23:
                conteudo_atual = df_visual.iat[hora - 7, dia_idx]
                if conteudo_atual:
                    df_visual.iat[hora - 7, dia_idx] = f"{conteudo_atual} | {nome_curto}"
                    df_style.iat[hora - 7, dia_idx] = "background-color: #ffcccc; color: red; font-weight: bold; border: 2px solid red;"
                else:
                    df_visual.iat[hora - 7, dia_idx] = f"{nome_curto}\n({turma})"
                    df_style.iat[hora - 7, dia_idx] = f"background-color: {cor}; color: black; border-radius: 4px; font-size: 0.85em;"

    return df_visual, df_style

# --- INTERFACE ---

st.set_page_config(page_title="Organizador SIGAA", layout="wide")
inicializar_estado()

st.title("🎓 Organizador de Matrícula (Integração SIGAA)")

tab1, tab2 = st.tabs(["📂 1. Importar HTML SIGAA", "📅 2. Montar Grade"])

# --- ABA 1: IMPORTAÇÃO ---
with tab1:
    st.markdown("### Importação de Dados")
    st.info("Entre no SIGAA > Lista de Turmas > Salve a página como `.html` e carregue abaixo.")
    
    arquivo = st.file_uploader("Carregar arquivo HTML (Salvo do SIGAA)", type=["html"])
    
    if arquivo:
        try:
            # Lê o conteúdo do arquivo
            conteudo = arquivo.getvalue().decode("windows-1252", errors="ignore") # Tenta decodificar padrão SIGAA
            
            with st.spinner("Processando turmas e decodificando horários..."):
                df_proc = extrair_dados_html(conteudo)
            
            if df_proc.empty:
                st.error("Não foi possível extrair turmas. Verifique se o HTML é da página 'Lista de Turmas'.")
            else:
                st.session_state['ofertas_db'] = df_proc
                st.success(f"Sucesso! {len(df_proc)} blocos de horário processados.")
                st.caption("Abaixo, uma amostra dos dados já convertidos para dias e horas:")
                st.dataframe(df_proc[['Componente', 'Turma', 'Dia', 'Inicio', 'Horario_Original']].head(), use_container_width=True)
                
        except Exception as e:
            st.error(f"Erro ao processar arquivo: {e}")

# --- ABA 2: MONTAR GRADE ---
with tab2:
    col_left, col_right = st.columns([1.2, 2.8])
    
    with col_left:
        st.header("Selecionar")
        
        if st.session_state['ofertas_db'].empty:
            st.warning("⚠️ Importe o HTML primeiro.")
        else:
            df = st.session_state['ofertas_db']
            
            # Filtros em cascata
            componentes = sorted(df['Componente'].unique())
            comp_sel = st.selectbox("Disciplina", ["Selecione..."] + componentes)
            
            if comp_sel != "Selecione...":
                df_c = df[df['Componente'] == comp_sel]
                turmas = sorted(df_c['Turma'].unique())
                turma_sel = st.selectbox("Turma", turmas)
                
                # Coletar dados da turma selecionada
                # Como o DF agora tem 1 linha por hora de aula, agrupamos
                df_t = df_c[df_c['Turma'] == turma_sel]
                
                if not df_t.empty:
                    docente = df_t.iloc[0]['Docente']
                    local = df_t.iloc[0]['Local']
                    horario_orig = df_t.iloc[0]['Horario_Original']
                    
                    st.markdown(f"""
                    **Docente:** {docente}  
                    **Local:** {local}  
                    **Código Horário:** `{horario_orig}`
                    """)
                    
                    # Calcular blocos para a grade
                    blocos_turma = []
                    detalhes_visuais = []
                    
                    for _, row in df_t.iterrows():
                        dia_idx = DIAS_SEMANA.index(row['Dia'])
                        blocos_turma.append((dia_idx, row['Inicio']))
                        detalhes_visuais.append(f"{row['Dia']} {row['Inicio']}h-{row['Fim']}h")
                    
                    # Remove duplicatas visuais (para exibir bonitinho)
                    st.text("Horários decodificados:\n• " + "\n• ".join(sorted(set(detalhes_visuais))))

                    # Checar conflitos
                    problemas = verificar_problemas(blocos_turma, comp_sel)
                    
                    if problemas:
                        for p in problemas: st.warning(p)
                        if st.button("⚠️ Adicionar com Conflito", type="secondary"):
                            adicionar_turma_a_grade(comp_sel, turma_sel, docente, blocos_turma)
                    else:
                        st.success("Disponível")
                        if st.button("✅ Adicionar", type="primary"):
                            adicionar_turma_a_grade(comp_sel, turma_sel, docente, blocos_turma)

        st.divider()
        st.subheader("Matrículas")
        if not st.session_state['matricula']:
            st.caption("Nenhuma.")
        else:
            for item in st.session_state['matricula']:
                with st.container(border=True):
                    c1, c2 = st.columns([0.85, 0.15])
                    c1.markdown(f"**{item['componente']}**")
                    c1.caption(f"Turma {item['turma']} | {item.get('docente', '')}")
                    if c2.button("🗑️", key=item['id_unique']):
                        remover_matricula(item['id_unique'])

    with col_right:
        st.header("Visualização")
        df_vis, df_sty = construir_grade_visual()
        
        st.dataframe(
            df_vis.style.apply(lambda x: df_sty, axis=None),
            height=800,
            use_container_width=True,
            column_config={"_index": st.column_config.NumberColumn("Hora", format="%d:00")}
        )