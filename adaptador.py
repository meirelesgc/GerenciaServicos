from bs4 import BeautifulSoup
import pandas as pd

# 1. Carregar o arquivo HTML salvo
# Nota: O SIGAA costuma usar 'windows-1252' ou 'iso-8859-1'. 
# Se der erro de caracteres, tente encoding='latin-1'
caminho_arquivo = 'BES.html' 

with open(caminho_arquivo, 'r', encoding='windows-1252') as f:
    soup = BeautifulSoup(f, 'html.parser')

# 2. Encontrar a tabela específica de turmas
# O ID 'lista-turmas' é único no SIGAA
tabela = soup.find('table', id='lista-turmas')

dados_extraidos = []
disciplina_atual = ""

# 3. Iterar sobre todas as linhas da tabela
if tabela:
    linhas = tabela.find_all('tr')
    
    for linha in linhas:
        classes = linha.get('class', [])
        
        # CASO A: Linha de Cabeçalho da Disciplina (classe 'destaque')
        # Ex: "GCETENS511 - ACESSIBILIDADE FÍSICA..."
        if 'destaque' in classes:
            # Limpa o texto (remove quebras de linha e espaços extras)
            texto_disciplina = linha.get_text(strip=True)
            # Remove o sufixo (GRADUAÇÃO) se quiser limpar mais
            disciplina_atual = texto_disciplina.replace('(GRADUAÇÃO)', '').strip()
            
        # CASO B: Linha de Turma (classe 'linhaPar' ou 'linhaImpar')
        # Ex: Turma 01, Docente, Horário...
        elif ('linhaPar' in classes or 'linhaImpar' in classes):
            # Ignorar as linhas ocultas de opções (menus) que têm style="display: none"
            if 'display: none' in str(linha.get('style')):
                continue
                
            colunas = linha.find_all('td')
            
            # Garante que a linha tem colunas suficientes para evitar erros
            if len(colunas) > 7:
                # Mapeamento baseado no cabeçalho da tabela:
                # 0: Ano/Período
                # 1: Turma (dentro de uma tag <a>)
                # 2: Docente
                # 3: Tipo
                # 4: Modalidade
                # 5: Situação
                # 6: Horário
                # 7: Local
                # 8: Matrícula/Capacidade
                
                turma = colunas[1].get_text(strip=True)
                docente = colunas[2].get_text(strip=True)
                situacao = colunas[5].get_text(strip=True) # Ex: ABERTA
                horario = colunas[6].get_text(strip=True)
                local = colunas[7].get_text(strip=True)
                capacidade = colunas[8].get_text(strip=True)

                # Adiciona à lista apenas se tivermos uma disciplina identificada
                if disciplina_atual:
                    dados_extraidos.append({
                        'Disciplina': disciplina_atual,
                        'Turma': turma,
                        'Docente': docente,
                        'Horario': horario,
                        'Local': local,
                        'Situacao': situacao,
                        'Vagas': capacidade
                    })

# 4. Criar DataFrame e Exportar
df = pd.DataFrame(dados_extraidos)

# Exibir as primeiras linhas para conferência
print(f"Total de turmas extraídas: {len(df)}")
print(df.head())

# Exportar para CSV (separador ponto e vírgula para abrir fácil no Excel BR)
df.to_csv('turmas_ufrb.csv', index=False, sep=';', encoding='utf-8-sig')
print("Arquivo 'turmas_ufrb.csv' gerado com sucesso!")