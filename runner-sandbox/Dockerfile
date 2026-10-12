# Imagem da sandbox: container descartavel que executa o codigo enviado pelo aluno.
# Criada sob demanda pelo worker, uma instancia por submissao, e removida ao final.
# As restricoes (memoria, CPU, timeout e rede desabilitada) nao sao definidas aqui,
# e sim aplicadas pelo worker ao criar o container.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY corrigeQuestao.py .
COPY biblioteca.py .