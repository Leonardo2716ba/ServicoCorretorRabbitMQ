import base64
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from IPython.display import display

BASE = Path.cwd()                       # pasta do projeto; o relative_to(BASE) exige que FIGURAS fique dentro dela
FIGURAS = BASE / 'figuras'
FIGURAS.mkdir(parents=True, exist_ok=True)

ALPHA = 0.10                            # nivel do IC de 90%
AZUL = '#1f77b4'                        # troque pelo azul que voce ja usa nas outras figuras

def salvar_figura(fig,nome):
    if any(ax.get_title() or ax.get_title(loc='left') or ax.get_title(loc='right') for ax in fig.axes):
        raise ValueError('A identificação pertence à legenda externa da figura')
    if getattr(fig,'_suptitle',None) is not None:
        raise ValueError('A identificação pertence ao texto')
    w,h=fig.get_size_inches()
    if w>10 or h>10 or w<3 or h<2:
        raise ValueError('Dimensões físicas inadequadas')
    pdf=FIGURAS/f'{nome}.pdf'
    png=FIGURAS/f'{nome}.png'
    fig.savefig(pdf,format='pdf',dpi=600)
    fig.savefig(png,format='png',dpi=180)
    largura=1000 if len(fig.axes)>1 else 820
    display({'image/png':base64.b64encode(png.read_bytes()).decode('ascii')},raw=True,
        metadata={'image/png':{'width':largura,'height':round(largura*h/w)},
                  'fatorial_pdf':str(pdf.relative_to(BASE)),
                  'largura_polegadas':float(w),'altura_polegadas':float(h)})
 

CORES = ['#24577A', '#d95f02', '#1b9e77', '#7570b3', '#e7298a']
MARCADORES = ['o', 's', '^', 'D', 'v']
ROTULOS = {
    'workers': 'Número de workers',
    'submissions': 'Submissões',
    'makespan_s': 'Makespan médio (s)',
    'throughput_per_s': 'Vazão média (correções/s)',
    'container_runtime_median_s': 'Tempo mediano do container (s)',
}


def ler_resultados(caminho):
    df = pd.read_csv(caminho)
    bons = df['status'] == 'ok'
    # confere correcoes completas e nota 10; se o Node nao repassa esses campos, ignora a checagem
    bons &= df['status_ok'].isna() | (df['status_ok'] == df['completed'])
    bons &= df['score_mean'].isna() | (df['score_mean'] == 10)
    return df[bons]


def grafico_linhas_csv(caminho, prefixo, x='workers', linhas='submissions', y='makespan_s',
                       com_ic=True, log_y=True, tamanho=(5, 3)):
    df = ler_resultados(caminho)
    g = df.groupby([linhas, x])[y].agg(['mean', 'std', 'count']).reset_index()
    g['margem'] = stats.t.ppf(1 - ALPHA / 2, g['count'] - 1) * g['std'] / np.sqrt(g['count'])

    fig, ax = plt.subplots(figsize=tamanho, layout='constrained')
    for idx, (valor, d) in enumerate(g.groupby(linhas)):
        d = d.sort_values(x)
        cor = CORES[idx % len(CORES)]
        fmt = MARCADORES[idx % len(MARCADORES)] + '-'
        rotulo = f'{int(valor):,}'.replace(',', '.') if float(valor).is_integer() else str(valor)
        if com_ic:
            ax.errorbar(d[x], d['mean'], yerr=d['margem'].fillna(0), fmt=fmt, capsize=3, color=cor, label=rotulo)
        else:
            ax.plot(d[x], d['mean'], fmt, color=cor, label=rotulo)

    ax.set_xticks(sorted(df[x].unique()))
    ax.set_xlabel(ROTULOS.get(x, x))
    ax.set_ylabel(ROTULOS.get(y, y) + (f' e IC de {100 * (1 - ALPHA):.0f}%' if com_ic else ''))
    if log_y:
        ax.set_yscale('log')
    ax.tick_params(axis='y', labelleft=True)   # mantem os numeros do eixo y
    ax.margins(x=.05)
    ax.legend(title=ROTULOS.get(linhas, linhas), loc='upper right')
    salvar_figura(fig, prefixo + '_linhas')

grafico_linhas_csv('makespan_results.csv', 'makespan')                                   # makespan x workers, uma linha por nº de submissões
grafico_linhas_csv('makespan_results.csv', 'vazao', y='throughput_per_s', log_y=False)   # mesma figura para a vazão