"""Gera relatório privado; não cadastra pedidos e não executa macros."""
import argparse
import html
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from core.excel_import import read_workbook, inferred_patterns

parser=argparse.ArgumentParser()
parser.add_argument('file',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
analysis=read_workbook(args.file.read_bytes())
patterns=inferred_patterns(analysis)
args.output.mkdir(parents=True,exist_ok=True)
weekdays={1:'Segunda',2:'Terça',3:'Quarta',4:'Quinta',5:'Sexta',6:'Sábado',7:'Domingo'}
book=Workbook();summary=book.active;summary.title='Leia primeiro'
for row in [
 ['Análise das rotinas de compra · TECO'],
 ['Fonte',args.file.name],['Clientes',analysis['clients']],['Produtos identificados',analysis['products']],
 ['Rotinas estáveis',sum(p['stable'] for p in patterns)],['Padrões variáveis',sum(not p['stable'] for p in patterns)],
 ['Pedidos importados',0],['Valores financeiros importados',0],
 ['Período','Outubro de 2026. Não há abas de 22 a 26/10.'],
 ['Critério','Moda por cliente, produto e dia da semana. Mínimo 2 ocorrências e 60% das datas disponíveis.'],
 ['Interpretação','Ausência só conta nas datas que existem. Dias sem aba não significam ausência de compra.'],
 ['Preços','Valores unitários de outubro vazios: não é possível calcular faturamento ou inadimplência.'],
 ['Observações','Textos históricos podem variar. Confirmar instruções, unidades e horário atual com o cliente.'],
 ['Clientes','Nomes preservados; filiais e horários não foram fundidos por semelhança de nome.'],
 ['Produtos','Abreviações foram preservadas, exceto P. ÁG/MARG. → P. ÁG C/ MARG. e P. LEITE/MARG. → P. LEITE C/ MARG.'],
]:summary.append(row)
headers=['Cliente','Produto','Dia','Quantidade mais frequente','Menor quantidade positiva','Maior quantidade positiva','Datas com compra','Datas disponíveis','Frequência da moda','Condição','Observações históricas']
for title,stable in [('Rotinas estáveis',True),('Variações a conferir',False)]:
 sheet=book.create_sheet(title);sheet.append(headers)
 for p in patterns:
  if p['stable']!=stable:continue
  sheet.append([p['client'],p['product'],weekdays[p['weekday']],float(p['quantity']),float(p['minimum']),float(p['maximum']),p['presence'],p['samples'],p['matches'],p['reason'],p['notes']])
notes=book.create_sheet('Observações por cliente');notes.append(['Cliente','Instrução histórica a conferir'])
for client in sorted({o['client'] for o in analysis['orders']}):
 texts=sorted({n for o in analysis['orders'] if o['client']==client for n in o['notes']})
 for text in texts:notes.append([client,text])
issues=book.create_sheet('Pendências de leitura');issues.append(['Cliente','Aba','Linha','Descrição','Motivo'])
for o in analysis['orders']:
 for p in o['problems']:issues.append([o['client'],o['sheet'],p['row'],p['description'],p['reason']])
for warning in analysis['warnings']:issues.append(['','','','',warning])
for sheet in book:
 sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
 for cell in sheet[1]:cell.fill=PatternFill('solid',fgColor='173D37');cell.font=Font(color='FFFFFF',bold=True)
 for row in sheet:
  for cell in row:
   cell.alignment=Alignment(vertical='top',wrap_text=True)
   # Neutraliza texto que poderia ser interpretado como fórmula ao exportar.
   if isinstance(cell.value,str) and cell.value.startswith(('=','+','-','@')):cell.data_type='s'
 for col in sheet.columns:
  letter=col[0].column_letter
  sheet.column_dimensions[letter].width=min(65,max(18,max(len(str(c.value or '')) for c in col[:60])+2))
book.save(args.output/'Rotinas_TECO_analise.xlsx')
rows=[]
for client in sorted({o['client'] for o in analysis['orders']}):
 entries=[p for p in patterns if p['client']==client]
 tr=[]
 for p in sorted(entries,key=lambda p:(p['weekday'],p['product'])):
  qty=p['quantity'] if p['quantity']!='0' else 'Sem compra é mais frequente'
  tr.append('<tr><td>'+weekdays[p['weekday']]+'</td><td>'+html.escape(p['product'])+'</td><td>'+html.escape(qty)+'</td><td>'+p['minimum']+'–'+p['maximum']+'</td><td>'+str(p['presence'])+'/'+str(p['samples'])+'</td><td><span class="tag '+('stable' if p['stable'] else '')+'">'+('Estável' if p['stable'] else 'Conferir')+'</span></td></tr>')
 texts=sorted({n for o in analysis['orders'] if o['client']==client for n in o['notes']})
 notes_html='<ul>'+''.join('<li>'+html.escape(n)+'</li>' for n in texts)+'</ul>' if texts else '<p class="muted">Sem observações adicionais identificadas.</p>'
 rows.append('<details class="client" data-name="'+html.escape(client,quote=True)+'"><summary>'+html.escape(client)+' <small>'+str(sum(p['stable'] for p in entries))+' padrões estáveis · '+str(sum(not p['stable'] for p in entries))+' a conferir</small></summary><div class="scroll"><table><tr><th>Dia</th><th>Produto</th><th>Quantidade mais frequente</th><th>Faixa positiva</th><th>Presença / datas disponíveis</th><th>Rotina</th></tr>'+''.join(tr)+'</table></div><h3>Observações históricas: confirmar instrução atual</h3>'+notes_html+'</details>')
doc='''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TECO · Rotinas de compra</title><style>*{box-sizing:border-box}body{background:#f5f7f3;color:#203936;font:14px/1.6 system-ui;margin:0}header{background:#173d37;color:#fff;padding:35px max(5%,calc((100vw - 1100px)/2))}header small{color:#d7ef8b;letter-spacing:2px}h1{font-size:32px}main{max-width:1160px;padding:24px;margin:auto}.muted{color:#71817d}.notice{background:#fff6e1;padding:18px;border-radius:10px;margin:20px 0}.kpis{display:flex;gap:15px;flex-wrap:wrap}.kpis div{padding:20px;background:white;border:1px solid #e5ebe6;border-radius:12px;flex:1;min-width:160px}.kpis strong{display:block;font-size:30px}input{width:100%;padding:14px;border:1px solid #d8e1d9;border-radius:9px;font:inherit;margin:20px 0}.client{padding:22px;background:white;border:1px solid #e5ebe6;border-radius:12px;margin:12px 0}summary{cursor:pointer;font-weight:700}summary small{font-weight:400;color:#71817d;display:block}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;margin:20px 0}td,th{padding:12px;border-bottom:1px solid #e5ebe6;text-align:left;min-width:90px}th{font-size:11px;color:#71817d}.tag{background:#fff0dc;color:#8b621f;padding:4px 8px;border-radius:5px;white-space:nowrap}.tag.stable{background:#eaf2e1;color:#41623c}li{margin:8px 0}button{border:1px solid #d8e1d9;background:white;padding:10px;border-radius:6px;cursor:pointer}</style><header><small>TECO · INTELIGÊNCIA DA ROTINA</small><h1>O comportamento de compra dos seus clientes</h1><p>Outubro de 2026 como referência. Novos pedidos começam do zero.</p></header><main><div class="kpis"><div><strong>CLIENTS</strong>clientes identificados</div><div><strong>PRODUCTS</strong>produtos identificados</div><div><strong>STABLE</strong>padrões por dia estáveis</div><div><strong>0</strong>pedidos antigos importados</div></div><div class="notice"><strong>Como interpretar:</strong> padrão estável = mesma quantidade em pelo menos 60% das datas disponíveis daquele dia da semana, com duas ocorrências ou mais. Faltam as abas de 22 a 26/10; esses dias não contam como ausência. Duas vias contam uma vez. Modelos de 2013 e registros de 2016 não foram usados. Preços vazios não geram valores financeiros. Quantidades e instruções compostas ficam para conferência.</div><label for="search">Encontre um cliente</label><input id="search" placeholder="Digite o nome do cliente…"><button id="open">Expandir clientes visíveis</button> <button id="close">Recolher</button><p id="count" class="muted"></p>CONTENT<p class="muted">Relatório privado. Não contém faturamento, dívidas ou pedidos importados. Quantidades de itens com unidade ambígua precisam de conferência antes do uso operacional.</p></main><script>const cards=[...document.querySelectorAll('.client')];const search=document.querySelector('#search');function filter(){let n=0;for(const c of cards){c.hidden=!c.dataset.name.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').includes(search.value.toUpperCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,''));if(!c.hidden)n++}document.querySelector('#count').textContent=n+' clientes encontrados'}search.addEventListener('input',filter);document.querySelector('#open').onclick=()=>cards.filter(c=>!c.hidden).forEach(c=>c.open=true);document.querySelector('#close').onclick=()=>cards.forEach(c=>c.open=false);filter();</script></html>'''
doc=doc.replace('CLIENTS',str(analysis['clients'])).replace('PRODUCTS',str(analysis['products'])).replace('STABLE',str(sum(p['stable'] for p in patterns))).replace('CONTENT',''.join(rows))
(args.output/'Rotinas_TECO_relatorio.html').write_text(doc)
print(f'Relatórios gerados: {analysis["clients"]} clientes; {analysis["products"]} produtos; nenhum pedido importado.')
