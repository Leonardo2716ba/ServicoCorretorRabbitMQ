'''
Chamada: python corrigeQuestao.py <pasta da questão> <pasta da entrega> <nome da tarefa> <nome da questão> <nome do aluno>

Exemplo: python "/Volumes/GoogleDrive/Meu Drive/2021-02/BCC701/Aulas Práticas/TesteCorretor/corrigeQuestao.py" "/Volumes/GoogleDrive/Meu Drive/2021-02/BCC701/Aulas Práticas/P-05/Q14" "/Volumes/GoogleDrive/Meu Drive/2021-02/BCC701/Aulas Práticas/P-05" "Implementação de funções" questao01 "Teste de correção"

Pasta da questão:
- Deve conter os arquivos de criterios, entrada e saida padrão da correção, com o nome contendo os números sequenciais dos casos de teste.
- Estrutura da pasta: <home>/Questoes/Q<id da questão>/

Pasta da entrega:
- Deve conter a solução original postada pelo aluno "submission.py"
- Os arquivos de correção serão todos gerados nesta pasta
- Estrutura da pasta: <home>/Entregas/A<id do aluno>/T<id da tarefa>/Q<id da questão>/E<id da entrega>
'''

import glob, os, sys, re, os.path, shutil, json, pathlib
import subprocess
from unicodedata import normalize
from fuzzywuzzy import fuzz
import difflib
import inspect, ast, astunparse

colsExecucao = 42
colsFuncoes = 24
iniDiff = '<span class="diff_chg">'
fimDiff = '</span>'


class Correcao:
    def __init__(self):
        self.resultado = { 'NotaExecucoes': 0, 'NotaFuncoes': 0, 'NotaFinal': 0, 'Execucoes': [], 'Funcoes': [] }
    def addResultadoFuncao(self, funcao):
        self.resultado['Funcoes'].append(funcao)
        funcao['Pontuacao'] /= len(funcao['Testes'])
        self.resultado['NotaFuncoes'] += funcao['Pontuacao']
    def addResultadoExecucao(self, execucao):
        self.resultado['Execucoes'].append(execucao)
        self.resultado['NotaExecucoes'] += execucao['Pontuacao']
    def finalizarNota(self):
        totalExecucoes = self.resultado['NotaExecucoes'] / len(self.resultado['Execucoes'])
        self.resultado['NotaExecucoes'] = round(totalExecucoes, 1)
        if  len(self.resultado['Funcoes']) > 0:
            totalFuncoes = self.resultado['NotaFuncoes'] / len(self.resultado['Funcoes'])
            self.resultado['NotaFuncoes'] = round(totalFuncoes, 1)
            self.resultado['NotaFinal'] = round((totalFuncoes + totalExecucoes) / 2, 1)
        else:
            self.resultado['NotaFinal'] = round(totalExecucoes, 1)
    def salvar(self, outFold):
        def convertSaidas():
            def convertString(texto):
                linhas = texto.strip().split('\n')
                tabela = '<table class="diff">'
                for l, linha in enumerate(linhas):
                    tabela += f'<tr><td class="diff_header">{l + 1}</td><td>{linha}</td></tr>'
                tabela += '</table>'
                return tabela
            for caso in self.resultado['Execucoes']:
                caso['SaidaEsperada'] = convertString(caso['SaidaEsperada'])
                caso['SaidaObtida'] = convertString(caso['SaidaObtida'])
            for funcao in self.resultado['Funcoes']:
                for teste in funcao['Testes']:
                    teste['Entradas'] = convertString(teste['Entradas'].replace(':||:', '\n'))
                    teste['RetornosEsperados'] = convertString(teste['RetornosEsperados'].replace(':||:', '\n'))
                    teste['RetornosObtidos'] = convertString(teste['RetornosObtidos'].replace(':||:', '\n'))
        self.finalizarNota()
        if TESTE: generateTex(self.resultado, f'{outFold}/correcao.tex')
        nota = open(f'{outFold}/nota.txt', 'w')
        nota.write(f'{self.resultado["NotaFinal"]}')
        nota.close()
        convertSaidas()
        file = open(f'{outFold}/correcao.json', 'w', encoding='utf8')
        json.dump(self.resultado, file, indent=4, ensure_ascii=False)


def prepareSaida(saida, col):
    global JSON
    if JSON: return saida.split('\n')
    linhas = saida.replace(' ', '~').split('\n')
    for l in range(len(linhas)):
        lenL = len(linhas[l])
        if lenL >= col:
            for x in range(int(lenL/col)):
                ini = min(x * col + col, lenL-1)
                fim = x * col
                for i in range(ini, fim, -1):
                    if linhas[l][i] == '~':
                        linhas[l] = linhas[l][:i] + ' ' + linhas[l][i+1:]
                        break
    return linhas


def diffSaidas(Esperado, Obtido, erro, col):
    oldE = prepareSaida(Esperado, col)
    oldO = prepareSaida(Obtido, col)
    newE = ''
    newO = ''
    for l in range(max(len(oldE), len(oldO))):
        E = oldE[l] if l < len(oldE) else ''
        O = oldO[l] if l < len(oldO) else ''
        if erro:
            newE += iniDiff + E + fimDiff
            newO += iniDiff + O + fimDiff
        else:
            s = difflib.SequenceMatcher(None, E, O)
            for tag, i1, i2, j1, j2 in s.get_opcodes():
                if tag == 'equal':
                    newE += E[i1:i2]
                    newO += O[j1:j2]
                elif tag == 'replace':
                    newE += iniDiff + E[i1:i2] + fimDiff
                    newO += iniDiff + O[j1:j2] + fimDiff
                elif tag == 'delete':
                    newE += iniDiff + E[i1:i2] + fimDiff
                elif tag == 'insert':
                    newO += iniDiff + O[j1:j2] + fimDiff
        newE += '\n'
        newO += '\n'
    return [ newE.strip(), newO.strip() ]


def compareString(str_student, str_correct):
    def chr_remove(old, to_remove):
        new_string = old
        for x in to_remove: new_string = new_string.replace(x, '')
        return new_string
    str_student = normalize('NFKD', str_student).encode('ASCII', 'ignore',).decode('ASCII')
    str_correct = normalize('NFKD', str_correct).encode('ASCII', 'ignore',).decode('ASCII')
    str_student = str_student.replace(' ', '')
    str_correct = str_correct.replace(' ', '')
    str_student = str_student.replace('\n', '')
    str_correct = str_correct.replace('\n', '')
    str_student = chr_remove(str_student, '?,!|\t')
    str_correct = chr_remove(str_correct, '?,!|\t')
    str_correct = str_correct.lower()
    str_student = str_student.lower()
    if(len(str_student) < len(str_correct)-2): return 0
    similarity = fuzz.partial_ratio(str_correct, str_student)
    if(similarity < 80): return 0
    else: return similarity


def run_with_limited_time(comm, nameIn, nameOut , time=6):
    fileOut = open(nameOut, 'w')
    if nameIn == None:
        p = subprocess.Popen(['python', comm], stdout=fileOut, stderr=fileOut)
    else:
        fileIn = open(nameIn, 'r')
        p = subprocess.Popen(['python', comm], stdin=fileIn, stdout=fileOut, stderr=fileOut)
    try:
        p.wait(time)
        exec = True
    except subprocess.TimeoutExpired:
        p.kill()
        exec = False
    if nameIn != None: fileIn.close()
    fileOut.close()
    return exec


def scoreTestCase(caseNum, str_criterion, str_student):
    global resultado, questaoPath
    arq_criterion = open(str_criterion, 'r')
    arq_student = open(str_student, mode='r', encoding='utf-8', errors='ignore')
    text_student = arq_student.readlines()
    saidaObtida = ''.join(text_student)
    text_student = [x for x in text_student if x.strip() != '']
    number_lines = int(arq_criterion.readline())
    outputStudent = '\n'.join(text_student)
    score = 0.0
    t = ""
    erro = True
    if (fuzz.partial_ratio('Traceback (most recent call last):', outputStudent) > 80):
        saidaObtida = "Erro de Execução"
    elif (fuzz.partial_ratio('SyntaxError: invalid syntax', outputStudent) > 80):
        saidaObtida = "Erro de Sintaxe"
    elif (outputStudent == ""):
        saidaObtida = ""
    elif (re.search('Tempo Limite Excedido', outputStudent, re.IGNORECASE)):
        saidaObtida = "Tempo Limite Excedido."
    else:
        erro = False
        it = 0
        linhas = min((len(text_student)), number_lines)
        while (it < linhas):
            infoLine = arq_criterion.readline()
            infoLine = infoLine.split(" ")
            id_line = int(infoLine[0])
            number_part = int(infoLine[1])
            it2 = 0
            while (it2 < number_part and (len(text_student) >= id_line)):
                line = arq_criterion.readline()
                line = line.split('||')
                str_correct = line[0]
                partial_score = float(line[1])
                if (len(text_student) >= id_line):
                    result = compareString(text_student[id_line - 1], str_correct)
                    score = score + (result / 100 * partial_score)
                it2 += 1
            if ((len(text_student) >= id_line)):
                if (text_student[id_line - 1] != '\n'):
                    t += text_student[id_line - 1]
            it += 1
            score = min(score, 10.0)
            tx = t.strip('\n')
            t = tx
            tx = tx.split('\n')
            if (len(tx) < linhas):
                t += '\n'
    saidaFile = open(f'{questaoPath}/saida.{caseNum}.txt', 'r')
    saidaEsperada = ''.join(saidaFile.readlines())
    saidaFile.close()
    score = round(score, 1)
    saidas = diffSaidas(saidaEsperada, saidaObtida, erro, colsExecucao)
    resultadoExecucao = {'Caso': caseNum,
                         'Erro': erro,
                         'Pontuacao': score,
                         'SaidaEsperada': saidas[0],
                         'SaidaObtida': saidas[1] }
    resultado.addResultadoExecucao(resultadoExecucao)
    if TESTE: print(score)


def scoreFuncoes():
    global resultado, entregaPath, questaoPath, bibFile
    def addResultado(resultadoFuncao):
        if resultadoFuncao != None:
            resultado.addResultadoFuncao(resultadoFuncao)
            if TESTE: print(f'Função {resultadoFuncao["Nome"]}: {resultadoFuncao["Pontuacao"]:.1f}')
    testeFuncaoFile = open(f'{entregaPath}/testeFuncoes.py', 'w', errors='ignore', encoding="utf8")
    testeFuncaoFile.write(f'import sys, os, glob\n')
    testeFuncaoFile.write(f'from func_timeout import func_timeout, FunctionTimedOut\n')
    testeFuncaoFile.write(f'from unicodedata import normalize\n')
    testeFuncaoFile.write(f'from fuzzywuzzy import fuzz\n')
    testeFuncaoFile.write(f'sys.path.append("{bibFile}")\n')
    with open(f'{entregaPath}/submission.py', 'r') as source:
        for linha in source:
            if 'import' in linha:
                testeFuncaoFile.write(linha.strip()+'\n')
    testeFuncaoFile.write('\n')
    testeFuncaoFile.write(f'{inspect.getsource(compareString)}\n\n')
    testeFuncaoFile.write('### Ini: Funções a serem testadas\n')
    funcoesAluno = []
    source = open(f'{entregaPath}/submission.py', 'r').read()
    try:
        code = ast.parse(source)
        parseOk = True
    except:
        parseOk = False
    if parseOk:
        functions = [n for n in code.body if isinstance(n, ast.FunctionDef)]
        for functionNode in functions:
            funcoesAluno.append(functionNode.name)
            code = astunparse.unparse(functionNode)
            testeFuncaoFile.write(code)
        testeFuncaoFile.write(
            '\n\n### Fim: Funções a serem testadas\n\n'
            'def is_string_numeric(s):\n'
            '    try:\n'
            '        float(s)\n'
            '        return True\n'
            '    except ValueError:\n'
            '        return False\n'
            '    except TypeError:\n'
            '        return False\n'
            f'def myEval(expression):\n'
            f'    return str(eval(expression))\n\n'
            f'def converte(expression):\n'
            f'    r = expression.split(":||:")\n'
            f'    r = [ eval(x) if is_string_numeric(x) else x for x in r ]\n'
            f'    values = []\n'
            f'    for x in r: values.append(str(round(x, 5) if is_string_numeric(x) else x))\n'
            f'    return ":||:".join(values)\n\n'
            f'def test_functions():\n'
            f'    funcoesAluno = {funcoesAluno}\n'
            f'    outFile = open("{entregaPath}/testeFuncoes.txt","w")\n'
            f'    funcoes = glob.glob("{questaoPath}/*.func")\n'
            f'    for nomeFunc in funcoes:\n'
            f'        nomeFunc = os.path.basename(nomeFunc).replace(".func", "")\n'
            f'        outFile.write(f"Função:{{nomeFunc}}\\n")\n'
            f'        if nomeFunc in funcoesAluno:\n'
            f'            file = open(f"{questaoPath}/{{nomeFunc}}.func", "r")\n'
            f'            for line in file:\n'
            f'                case, arg, respEsperada = line.strip().split(":|:")\n'
            f'                try:\n'
            f'                    resp = func_timeout(6, myEval, args=[ f"{{nomeFunc}}({{arg.replace(\':||:\', \', \')}})" ])\n'
            f'                    if resp.startswith("(") and resp.endswith(")"):\n'
            f'                        if ", " in resp:\n'
            f'                            respAux = eval(resp)\n'
            f'                            resp = ":||:".join(str(k) for k in respAux)\n'
            f'                        else:\n'
            f'                            resp = resp[1:-1]\n'
            f'                    if resp == "None": resp = ""\n'
            f'                    resp = converte(resp)\n'
            f'                    respEsperada = converte(respEsperada)\n'
            f'                    nota = 10 * compareString(resp, respEsperada) / 100\n'
            f'                    outFile.write(f"{{case}}:|:{{arg}}:|:{{respEsperada}}:|:{{resp}}:|:{{nota}}\\n")\n'
            f'                except FunctionTimedOut:\n'
            f'                    res = "Tempo Limite Excedido."\n'
            f'                    outFile.write(f"{{case}}:|:{{arg}}:|:{{respEsperada}}:|:{{res}}:|:0.0\\n")\n'
            f'                except:\n'
            f'                    res = "Erro na chamada da função."\n'
            f'                    outFile.write(f"{{case}}:|:{{arg}}:|:{{respEsperada}}:|:{{res}}:|:0.0\\n")\n'
            f'        else:\n'
            f'            outFile.write("Função não encontrada.\n")\n'
            f'    outFile.close()\n'
            f'\n'
            f'if __name__ == "__main__":\n'
            f'    test_functions()\n'
        )
        testeFuncaoFile.close()
        os.chmod(f'{entregaPath}/testeFuncoes.py', 0o777)
        os.system(f'python -u "{entregaPath}"/testeFuncoes.py')
        tle = run_with_limited_time(f'{entregaPath}/testeFuncoes.py', None, f'{entregaPath}/testeFuncoes.out', 300)
    if not parseOk:
        resultadoFuncao = {}
        resultadoFuncao['Nome'] = 'Erro fatal'
        resultadoFuncao['Pontuacao'] = 0
        resultadoFuncao['Testes'] = []
        retornos = diffSaidas('', 'Erro de sintaxe.', True, colsFuncoes)
        teste = { 'Entradas': '',
                  'RetornosEsperados': retornos[0],
                  'RetornosObtidos': retornos[1],
                  'Pontuacao': 0,
                  'Erro': True }
        resultadoFuncao['Testes'].append(teste)
        addResultado(resultadoFuncao)
    elif not tle:
        resultadoFuncao = {}
        resultadoFuncao['Nome'] = 'Erro fatal'
        resultadoFuncao['Pontuacao'] = 0
        resultadoFuncao['Testes'] = []
        retornos = diffSaidas('', 'Tempo Limite Excedido.', True, colsFuncoes)
        teste = { 'Entradas': '',
                  'RetornosEsperados': retornos[0],
                  'RetornosObtidos': retornos[1],
                  'Pontuacao': 0,
                  'Erro': True }
        resultadoFuncao['Testes'].append(teste)
        addResultado(resultadoFuncao)
    elif os.path.exists(f'{entregaPath}/testeFuncoes.txt'):
        resultadoFuncao = None
        file = open(f'{entregaPath}/testeFuncoes.txt', 'r')
        for line in file:
            line = line.strip()
            if line.startswith('Função:'):
                addResultado(resultadoFuncao)
                resultadoFuncao = {}
                resultadoFuncao['Nome'] = line.split(':')[1]
                resultadoFuncao['Erro'] = False
                resultadoFuncao['Pontuacao'] = 0
                resultadoFuncao['Testes'] = []
            elif line == 'Função não encontrada.':
                retornos = diffSaidas('', line, True, colsFuncoes)
                teste = { 'Entradas': '',
                          'RetornosEsperados': retornos[0],
                          'RetornosObtidos': retornos[1],
                          'Pontuacao': 0,
                          'Erro': True }
                resultadoFuncao['Testes'].append(teste)
            else:
                line = line.split(':|:')
                erro = (line[3] == 'Erro na chamada da função.') or (line[3] == 'Tempo Limite Excedido.')
                retornos = diffSaidas(line[2].replace(':||:', '\n'), line[3].replace(':||:', '\n'), erro, colsFuncoes)
                teste = { 'Entradas': line[1],
                          'RetornosEsperados': retornos[0],
                          'RetornosObtidos': retornos[1],
                          'Pontuacao': float(line[4]),
                          'Erro': False }
                resultadoFuncao['Testes'].append(teste)
                resultadoFuncao['Pontuacao'] += teste['Pontuacao']
        addResultado(resultadoFuncao)
    if os.path.exists(f'{entregaPath}/testeFuncoes.py'): os.remove(f'{entregaPath}/testeFuncoes.py')
    if os.path.exists(f'{entregaPath}/testeFuncoes.txt'): os.remove(f'{entregaPath}/testeFuncoes.txt')
    if os.path.exists(f'{entregaPath}/testeFuncoes.out'): os.remove(f'{entregaPath}/testeFuncoes.out')


def generateCorretion(questaoPath, entregaPath):
    entradas = glob.glob(f'{questaoPath}/entrada.*')
    outputFile = f'{entregaPath}/output.txt'
    if os.path.exists(f'{questaoPath}/funcoes.txt'):
        if TESTE: print(f'\n*** FUNÇÕES ***')
        scoreFuncoes()
    if TESTE: print(f'\n*** EXECUÇÕES ***')
    for c in range(1, len(entradas)+1):
        if TESTE: print(f'Caso de teste {c}: ', end='')
        inputFile = f'{questaoPath}/entrada.{c}.txt'
        tle = run_with_limited_time(f'{entregaPath}/correcao.py', inputFile, outputFile)
        if (not tle):
            fileOutput = open(outputFile, 'w')
            fileOutput.write('\n\n\n\nTempo Limite Excedido')
            fileOutput.close()
        scoreTestCase(c, inputFile.replace('entrada', 'criterios'), outputFile)
        os.remove(outputFile)


def processPyFile(entregaPath):
    global bibFile
    biblioteca = f'sys.path.append("{bibFile}")\n'
    lines1 = [ '## Ini: Incorporado para corretor automático\n',
               'import sys\n',
               biblioteca,
               'class Tee(object):\n',
               '	def __init__(self, input_handle, output_handle):\n',
               '		self.input = input_handle\n',
               '		self.output = output_handle\n',
               '	def readline(self):\n',
               '		result = self.input.readline()\n',
               '		self.output.write(result)\n',
               '		return result\n',
               'if not sys.stdin.isatty():\n',
               '    sys.stdin = Tee(input_handle=sys.stdin, output_handle=sys.stdout)\n',
               '## Fim: Incorporado para corretor automático\n',
               '\n',
             ]
    f2 = open(f'{entregaPath}/submission.py', mode='r', errors='ignore', encoding="utf8")
    lines2 = f2.readlines()
    f2.close()
    f3 = open(f'{entregaPath}/correcao.py', mode='w', errors='ignore', encoding="utf8")
    f3.writelines(lines1)
    f3.writelines(lines2)
    f3.close()
    os.chmod(f'{entregaPath}/correcao.py', 0o777)


def substituicoes(texto):
    texto = texto.replace(iniDiff, '\\Diff{')
    texto = texto.replace(fimDiff, '}')
    texto = texto.replace('\n', '~\\par\n')
    texto = texto.replace('$', r'\$')
    texto = texto.replace('&', r'\&')
    texto = texto.replace('#', r'\#')
    texto = texto.replace('%', r'\%')
    texto = texto.replace('_', r'\_')
    texto = texto.replace('<', '$<$')
    texto = texto.replace('>', '$>$')
    texto = texto.replace('−', '-')
    texto = texto.replace('~\\~', '~$\\backslash$~')
    return texto


def generateTex(resultado, outFileName):
    global entregaPath, tarefa, aluno, questao
    outFile = open(outFileName, mode='w', encoding='utf-8')
    outFile.write('\\documentclass{article}\n')
    outFile.write('\\usepackage[utf8]{inputenc}\n')
    outFile.write('\\usepackage{listings}\n')
    outFile.write('\\usepackage{comment}\n')
    outFile.write('\\usepackage{float}\n')
    outFile.write('\\usepackage{colortbl}\n')
    outFile.write('\\usepackage{xspace}\n')
    outFile.write('\\usepackage{titlesec}\n')
    outFile.write('\\usepackage[portuguese]{babel}\n')
    outFile.write('\\titleformat{\\section}[display]{\\bfseries\\LARGE}{}{}{}\n')
    outFile.write('\\usepackage[table]{xcolor}\n')
    outFile.write('\\definecolor{lightgray}{gray}{0.9}\n')
    outFile.write('\\usepackage{anysize}\n')
    outFile.write('\\marginsize{1cm}{1cm}{1cm}{1cm}\n')
    outFile.write('\\usepackage[thinlines]{easytable}\n')
    outFile.write('\n')
    outFile.write('\\newcommand{\\Diff}[1]{\\textcolor{red}{#1}}\n')
    outFile.write('\n')
    outFile.write(f'\\title{{Discente: \\textbf{{{aluno}}}}}\n')
    outFile.write(f'\\author{{\\LARGE{{Tarefa: \\textbf{{{tarefa}}}}}}}\n')
    outFile.write('\\date{}\n')
    outFile.write('\n')
    outFile.write('\\begin{document}\n')
    outFile.write('\\maketitle\n')
    outFile.write('\n')
    outFile.write('\n')
    outFile.write('\\begin{center}\n')
    outFile.write('\\begin{TAB}(r,1cm,1.5cm)[5pt]{c}{|c|}\n')
    strQuestao = f'{questao:^70}'.replace(' ', '~')
    outFile.write(f'{{\\LARGE{{\\textbf{{{strQuestao}}}}}}}\n')
    outFile.write('\\end{TAB}\n\n')
    outFile.write(f'\\vspace{{0.7cm}}\n\n')
    outFile.write(f'\\Large \\textbf{{Resumo das avaliações}}\n')
    outFile.write(f'\\begin{{table}}[H]\n')
    outFile.write(f'\\centering\n')
    outFile.write(f'\\begin{{tabular}}{{|c|c|}} \\hline\n')
    outFile.write(f'\\rowcolor[rgb]{{0.85,0.85,0.85}}\n')
    outFile.write(f'\\multicolumn{{2}}{{|c|}}{{\\textbf{{Execuções do programa}}}} \\\\ \\hline \\hline\n')
    for e in range(len(resultado['Execucoes'])):
        outFile.write(f'Caso de teste {e+1} & {resultado["Execucoes"][e]["Pontuacao"]:.1f} \\\\ \\hline\n')
    outFile.write(f'\\hline\n')
    outFile.write(f'\\rowcolor[rgb]{{0.85,0.85,0.85}}\n')
    outFile.write(f'\\textbf{{Nota de Execuções}} & \\textbf{{{resultado["NotaExecucoes"]:.1f}}} \\\\ \\hline\n')
    outFile.write(f'\\end{{tabular}}\n')
    outFile.write(f'\\end{{table}}\n')
    if len(resultado["Funcoes"]) > 0:
        outFile.write(f'\n\\vspace{{-0.4cm}}\n\n')
        outFile.write(f'\\begin{{table}}[H]\n')
        outFile.write(f'\\centering\n')
        outFile.write(f'\\begin{{tabular}}{{|l|c|}} \\hline\n')
        outFile.write(f'\\rowcolor[rgb]{{0.85,0.85,0.85}}\n')
        outFile.write(f'\\multicolumn{{2}}{{|c|}}{{\\textbf{{Chamadas de funções}}}} \\\\ \\hline \\hline\n')
        for f in range(len(resultado['Funcoes'])):
            outFile.write(f'{resultado["Funcoes"][f]["Nome"]} & {resultado["Funcoes"][f]["Pontuacao"]:.1f} \\\\ \\hline\n')
        outFile.write(f'\\hline\n')
        outFile.write(f'\\rowcolor[rgb]{{0.85,0.85,0.85}}\n')
        outFile.write(f'\\textbf{{Nota de Funções}} & \\textbf{{{resultado["NotaFuncoes"]:.1f}}} \\\\ \\hline\n')
        outFile.write(f'\\end{{tabular}}\n')
        outFile.write(f'\\end{{table}}\n')
    outFile.write(f'\n\\vspace{{-0.4cm}}\n\n')
    outFile.write(f'\\begin{{table}}[H]\n')
    outFile.write(f'\\large\n')
    outFile.write(f'\\centering\n')
    outFile.write(f'\\begin{{tabular}}{{|c|c|}} \\hline\n')
    outFile.write(f'\\rowcolor[rgb]{{0.85,0.85,0.85}}\n')
    outFile.write(f'\\multicolumn{{2}}{{|c|}}{{\\textbf{{Resultado Final}}}} \\\\ \\hline \\hline\n')
    outFile.write(f'Nota de Execuções & {resultado["NotaExecucoes"]:.1f} \\\\ \\hline\n')
    if len(resultado["Funcoes"]) > 0:
        outFile.write(f'Nota de Funções & {resultado["NotaFuncoes"]:.1f} \\\\ \\hline\n')
    outFile.write(f'\\hline\n')
    outFile.write(f'\\rowcolor[rgb]{{0.85,0.85,0.85}}\n')
    outFile.write(f'\\textbf{{Nota Final}} & \\textbf{{{resultado["NotaFinal"]:.1f}}} \\\\ \\hline\n')
    outFile.write(f'\\end{{tabular}}\n')
    outFile.write(f'\\end{{table}}\n')
    outFile.write(f'\\end{{center}}\n')
    outFile.write(f'\\newpage\n')
    outFile.write(f'\\begin{{center}}\n')
    outFile.write(f'\\Large \\textbf{{Detalhes das Execuções do Programa}}\n')
    outFile.write(f'\\end{{center}}\n')
    for e in range(len(resultado['Execucoes'])):
        outFile.write('\\subsection*{Caso de teste ' + str(e+1) + '}\n')
        outFile.write('\\begin{table}[H]\n')
        outFile.write(f'\\centering\n')
        outFile.write('\\begin{tabular}{|p{7.8cm}|p{7.8cm}|c|}\n')
        outFile.write('\\hline\n')
        outFile.write('\\rowcolor[rgb]{0.85,0.85,0.85}\n')
        outFile.write('\\textbf{Saída esperada} & \\textbf{Saída obtida}  & \\textbf{Pontuação} \\\\ \\hline \\hline\n')
        saidaEsperada = substituicoes(resultado["Execucoes"][e]["SaidaEsperada"])
        saidaAluno = substituicoes(resultado["Execucoes"][e]["SaidaObtida"])
        notaCaso = resultado["Execucoes"][e]["Pontuacao"]
        outFile.write(f'\n\\ttfamily\n{saidaEsperada}\n& \n\\ttfamily\n{saidaAluno}\n& {notaCaso:.1f} \\\\ \\hline\n')
        outFile.write('\\end{tabular}\n')
        outFile.write('\\end{table}\n\n')
    if len(resultado["Funcoes"]) > 0:
        outFile.write(f'\\newpage\n')
        outFile.write(f'\\begin{{center}}\n')
        outFile.write(f'\\Large \\textbf{{Detalhes das Execuções das Funções}}\n')
        outFile.write(f'\\end{{center}}\n')
        for f in range(len(resultado['Funcoes'])):
            outFile.write('\\subsection*{Função: ' + resultado['Funcoes'][f]['Nome'] + '}\n')
            outFile.write('\\begin{table}[H]\n')
            outFile.write(f'\\centering\n')
            outFile.write('\\begin{tabular}{|c|p{4.5cm}|p{4.5cm}|p{4.5cm}|c|}\n')
            outFile.write('\\hline\n')
            outFile.write('\\rowcolor[rgb]{0.85,0.85,0.85}\n')
            outFile.write('\\textbf{Teste} & \\textbf{Entradas} & \\textbf{Retornos esperados} & \\textbf{Retornos obtidos}  & \\textbf{Pontuação} \\\\ \\hline \\hline\n')
            for t in range(len(resultado['Funcoes'][f]['Testes'])):
                entrada = substituicoes(resultado["Funcoes"][f]["Testes"][t]['Entradas'].replace(':||:', '\n'))
                saidaEsperada = substituicoes(resultado["Funcoes"][f]["Testes"][t]['RetornosEsperados'])
                saidaAluno = substituicoes(resultado["Funcoes"][f]["Testes"][t]['RetornosObtidos'])
                notaFunc = resultado["Funcoes"][f]["Pontuacao"]
                if resultado["Funcoes"][f]["Testes"][t]['Erro']:
                    outFile.write(f'\n\\multicolumn{{4}}{{|c|}}{{{saidaAluno}}}\n& {notaFunc:.1f} \\\\ \\hline\n')
                else:
                    outFile.write(f'\n{t+1}\n&\\ttfamily\n{entrada}\n&\\ttfamily\n{saidaEsperada}\n& \n\\ttfamily\n{saidaAluno}\n& {notaFunc:.1f} \\\\ \\hline\n')
            outFile.write('\\end{tabular}\n')
            outFile.write('\\end{table}\n\n')
    outFile.write('\\end{document}')
    outFile.close()
    proc = subprocess.Popen(['pdflatex', '-output-directory=%s' % entregaPath, outFileName], stdout=open(os.devnull, 'wb'))
    proc.communicate()
    os.remove(outFileName.replace('.tex', '.log'))
    os.remove(outFileName.replace('.tex', '.aux'))
    os.remove(outFileName)


def checkRecursos():
    import ast

    BUILTIN_FUNCS = {
        'abs', 'round', 'print', 'input', 'len', 'range', 'float', 'int', 'str',
        'criarVetor', 'criarMatriz', 'inputVetor', 'inputMatriz', 'dimMatriz'
    }
    MATH_FUNCS = {
        'sqrt', 'cos', 'sin', 'tan', 'trunc', 'ceil', 'floor',
        'log', 'log10', 'log2'
    }
    MATH_CONSTS = {'pi', 'e', 'tau', 'inf'}
    LIST_METHODS = {'append', 'pop'}
    ALLOWED_IMPORTS = {'math', 'biblioteca'}

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.erros = []
            self.importou_math_all = False
            self.funcoes_definidas = set()
            self.importou_math_nominal = set()

        def visit_Import(self, node):
            for alias in node.names:
                if alias.name not in ALLOWED_IMPORTS:
                    self.erros.append(f'Importação não permitida: {alias.name}')
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            if node.module == 'biblioteca':
                for alias in node.names:
                    if alias.name != '*':
                        # Permite importação nominal de funções da biblioteca
                        self.funcoes_definidas.add(alias.asname if alias.asname else alias.name)
            elif node.module == 'math':
                for alias in node.names:
                    if alias.name == '*':
                        self.importou_math_all = True
                    elif alias.name in MATH_FUNCS or alias.name in MATH_CONSTS:
                        self.importou_math_nominal.add(alias.name)
                    else:
                        self.erros.append(f'Importação não permitida da math: {alias.name}')
            else:
                self.erros.append(f'Importação não permitida: from {node.module} import ...')
            self.generic_visit(node)

        def visit_FunctionDef(self, node):
            self.funcoes_definidas.add(node.name)
            self.generic_visit(node)

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name):
                nome = node.func.id
                if nome in self.funcoes_definidas:
                    pass
                elif nome in BUILTIN_FUNCS:
                    pass
                elif self.importou_math_all and nome in MATH_FUNCS:
                    pass
                elif nome in self.importou_math_nominal:
                    pass
                else:
                    self.erros.append(f'Função não permitida: {nome}')
            elif isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    if node.func.value.id == 'math':
                        if node.func.attr not in MATH_FUNCS:
                            self.erros.append(f'Função math não permitida: math.{node.func.attr}')
                    # ALTERAÇÃO: Permite chamadas via namespace 'biblioteca.funcao()'
                    elif node.func.value.id == 'biblioteca':
                        pass
                    elif node.func.attr not in LIST_METHODS:
                        self.erros.append(f'Método de lista não permitido: {node.func.attr}')
            self.generic_visit(node)

        def visit_While(self, node):
            if node.orelse:
                self.erros.append('Uso de while com else não permitido')
            self.generic_visit(node)

        def visit_For(self, node):
            if not (isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == 'range'):
                self.erros.append('Uso de for permitido apenas com range()')
            self.generic_visit(node)

        def visit_IfExp(self, node): self.erros.append('Uso de if inline (condicional ternário) não permitido')
        def visit_Break(self, node): self.erros.append('Uso de break não permitido')
        def visit_Continue(self, node): self.erros.append('Uso de continue não permitido')
        def visit_ListComp(self, node): self.erros.append('Compreensão de listas não permitida')
        def visit_DictComp(self, node): self.erros.append('Compreensão de dicionários não permitida')
        def visit_SetComp(self, node): self.erros.append('Compreensão de conjuntos não permitida')
        def visit_Try(self, node): self.erros.append('Uso de try/except não permitido')
        def visit_With(self, node): self.erros.append('Uso de with não permitido')
        def visit_Lambda(self, node): self.erros.append('Uso de lambda não permitido')
        def visit_ClassDef(self, node): self.erros.append('Uso de classe não permitido')
        def visit_Name(self, node):
            if node.id in {'eval', 'exec', 'compile', 'globals', 'locals', '__import__'}:
                self.erros.append(f'Uso da função {node.id} não permitido')

    try:
        with open(f'{entregaPath}/submission.py', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except:
        return False, ["Erro de sintaxe no código-fonte"]

    visitor = Visitor()
    visitor.visit(tree)
    if visitor.erros:
        return False, visitor.erros
    return True, []


if __name__ == '__main__':
    submissionPath = sys.argv[1] if len(sys.argv) > 1 else 'submission.json'
    with open(submissionPath, 'r', encoding='utf-8') as f:
        submission = json.load(f)

    home = str(pathlib.Path(__file__).parent.resolve())
    TESTE = 'TesteCorretor' in home
    JSON = True

    questaoPath = f'{home}/questao'
    entregaPath = f'{home}/entrega'
    os.makedirs(questaoPath, exist_ok=True)
    os.makedirs(entregaPath, exist_ok=True)

    tarefa = str(submission['task_delivered_id'])
    # TODO ADICIONAR COMO PARAMENTROS OBRIGATORIOS A SEREM PASSADOS
    #questao = str(submission['id'])
    #aluno = str(submission['user_id'])
    questao = -1000
    aluno = -1000
    bibFile = home

    with open(f'{entregaPath}/submission.py', 'w', encoding='utf-8') as f:
        f.write(submission['code_sent'])

    for c, caso in enumerate(submission['test_cases'], start=1):
        with open(f'{questaoPath}/entrada.{c}.txt', 'w', encoding='utf-8') as f:
            f.write(caso['input'])
        with open(f'{questaoPath}/criterios.{c}.txt', 'w', encoding='utf-8') as f:
            f.write(caso['criterion'])
        with open(f'{questaoPath}/saida.{c}.txt', 'w', encoding='utf-8') as f:
            f.write(caso['output'])

    if TESTE:
        print('\nPrototipo carregado: ')
        print(json.dumps(submission, indent=2, ensure_ascii=False))

    resultado = Correcao()
    processPyFile(entregaPath)
    ok, erros = checkRecursos()
    if ok:
        generateCorretion(questaoPath, entregaPath)
    else:
        mensagem = f'<span class="diff_chg">Inconformidades encontradas:<br/><br/>' + \
                   ';<br/><br/>'.join([f'({i + 1}) {erro}' for i, erro in enumerate(erros)]) + \
                   '.</span>'
        resultadoExecucao = {'Caso': 0,
                             'Erro': True,
                             'Pontuacao': 0,
                             'SaidaEsperada': "",
                             'SaidaObtida': mensagem}

        resultado.addResultadoExecucao(resultadoExecucao)

    resultado.salvar(entregaPath)
    os.remove(f'{entregaPath}/correcao.py')

    if TESTE:
        print(f'\n*** NOTA FINAL ***\n{resultado.resultado["NotaFinal"]}')
    else:
        print(json.dumps(resultado.resultado, ensure_ascii=False))