# TSC Virtual - captura do Windows para previa TSPL

## Pacote portatil para Windows

Use o ZIP completo de `Pacotes`, para **Windows 10/11 x64 (Intel/AMD)**.
Ele inclui **Python, bibliotecas e instalador do QZ Tray**. O computador de
destino nao precisa ter Python, Microsoft Store, pip nem internet para instalar
ou abrir o simulador. A instalacao da fila e do QZ requer administrador.

Extraia tudo em uma pasta permanente. Execute `INSTALAR_IMPRESSORA.bat` como
administrador uma vez e depois `INICIAR_SIMULADOR.bat` normalmente.
Mantenha a pasta `runtime` junto dos demais arquivos.

A `.venv` do projeto antigo nao e portatil: ela guarda caminhos absolutos do PC
onde foi criada. A abertura agora usa apenas `runtime\python.exe`, com caminhos
relativos e bibliotecas incluidas, e ignora essa `.venv` e o Python do sistema.

## Correcao de fidelidade da previa

O perfil padrao agora corresponde a **TSC TTP-245C, 8 dots/mm (203 dpi nominal)**.
O nome da fila Windows continua `TSC DA300`, para manter a selecao existente no QZ.
A previa anterior usava Arial proporcional, ignorava SHIFT e aceitava glifos do
Windows que nao apareciam na impressora. Isso podia esconder cortes e largura
excessiva de texto.

- Fontes residentes 1 a 8 agora avancam por celulas TSPL fixas, com multiplicadores,
  alinhamento e rotacao. O desenho das letras usa um substituto vetorial; nao e uma
  copia dos bitmaps do firmware.
- `SHIFT`, `REFERENCE`, `DIRECTION` e espelhamento entram na geometria. A orientacao
  da visualizacao e de leitura para `DIRECTION 1`; `DIRECTION 0` gira 180 graus.
- O papel e o vao entre etiquetas recortam o conteudo. Itens fora dos limites
  produzem avisos no painel e na propria previa. Nao ha ajuste automatico para caber.
- A decodificacao segue `CODEPAGE`. Nas fontes residentes com UTF-8, caracteres
  nao ASCII sao mostrados como celulas vazias e geram aviso, de forma conservadora
  para a TTP-245C usada no caso reportado. Nao ha substituicao automatica por acentos
  disponiveis no Windows.
- Nas etiquetas **103 x 40 mm**, uma linha vermelha marca **X=70 / 8,75 mm**, margem
  de seguranca retirada do lote aprovado. Conteudo antes dela gera aviso. Essa linha
  **nao afirma que a cabeca tenha uma margem morta de 70 dots** e nao corta essa area.
- O painel informa quando o alinhamento fisico ainda nao foi medido. Um desvio X/Y
  medido pode ser salvo em `perfil-impressora.json`; somente a simulacao muda.
  Valores negativos movem para esquerda/cima, positivos para direita/baixo. O perfil
  inicial usa zero sem declarar a impressora calibrada.
- Configuracoes TSPL persistem entre trabalhos recebidos enquanto o processo esta
  aberto. O painel permite **Atualizar previa** de um PRN capturado: isso cria outra
  conversao, preservando os bytes e os arquivos anteriores, sem imprimir na TSC.
  Capturas anteriores ficam identificadas como previas anteriores a correcao.

Reinicie o simulador depois de atualizar os arquivos. No historico, use
**Atualizar previa** para comparar uma captura anterior com estas regras.
Uma previa sem avisos valida a geometria representada; o alinhamento mecanico
so fica confirmado depois da comparacao com a impressora fisica.

Referencia das celulas, comandos e unidades: [manual TSPL/TSPL2 da TSC](https://shop.mediaform.de/media/wysiwyg/downloads/armilla/TSC_TSPL_TSPL2_Programming.pdf),
secoes TEXT, SHIFT, REFERENCE, DIRECTION e CODEPAGE.

Primeira versao experimental para **Windows 10/11** e trabalhos em **TSPL/TSPL2 bruto**, inclusive aqueles enviados pelo QZ Tray. A impressora aparece com o nome exato `TSC DA300`. Nenhuma mudanca no codigo do seu sistema e necessaria se ele envia TSPL para uma fila de impressao do Windows pelo nome.

## Passo a passo

O QZ Tray faz a ponte entre o site e a fila do Windows. So instalar a fila
nao basta para imprimir pelo site. **O instalador agora tambem instala o QZ Tray**
quando ele estiver ausente; uma instalacao existente do QZ e preservada.

1. Use um computador com **Windows 10/11 x64 (Intel/AMD)**. Este pacote nao foi preparado para Windows 32 bits ou ARM nativo.
2. Extraia todo o ZIP em uma pasta permanente, por exemplo `Documentos\TSC_DA300_Virtual`. Nao execute os arquivos de dentro do ZIP.
3. Execute `INSTALAR_IMPRESSORA.bat` **como administrador**. Ele valida o Python incluido, instala o **QZ Tray 2.3.0** pelo executavel incluido, se necessario, e cria a fila **TSC DA300** com driver `Generic / Text Only` e porta TCP local `127.0.0.1:19100`. O arquivo do QZ tem seu SHA-256 conferido antes de ser executado. Uma fila de mesmo nome que nao pertenca ao simulador nunca e modificada.
4. Execute `INICIAR_SIMULADOR.bat` normalmente, **sem administrador**. Ele usa o Python e as bibliotecas incluidos e abre o QZ Tray e o simulador, sem instalar dependencias. Deixe a janela preta e o QZ Tray abertos enquanto imprimir.
5. O painel abre em <http://127.0.0.1:8767/>. Atualize a pagina do seu sistema depois que o icone do QZ aparecer ao lado do relogio. Se o QZ pedir permissao para conectar o site, confira o endereco e permita. Selecione **TSC DA300** e imprima como de costume.
6. O PDF aparecera no painel, com um arquivo `.prn` ao lado, contendo **exatamente os bytes recebidos**. Os arquivos tambem ficam na pasta `Saidas`.

> Ordem recomendada: **iniciar o simulador primeiro; depois imprimir**. Se estiver fechado, a fila do Windows pode ficar em erro ou tentar novamente.

### Se voce ja instalou a impressora sem o QZ Tray

Execute `INSTALAR_IMPRESSORA.bat` novamente **como administrador**. Ele reconhece
a fila virtual existente e instala o QZ que faltou, sem recriar a impressora.
Depois, abra `INICIAR_SIMULADOR.bat` normalmente e atualize o site.

O ZIP portatil inclui `instaladores\qz-tray-2.3.0-x86_64.exe`, obtido na
[release oficial](https://github.com/qzind/tray/releases/tag/v2.3.0).
Se esse arquivo estiver ausente e o QZ nao estiver instalado, o instalador tenta
baixa-lo (cerca de 140 MB); nesse caso sera necessaria internet. O mesmo hash e conferido.
A instalacao silenciosa usa `/S`, conforme a [documentacao do QZ](https://qz.io/docs/deployment).

### Gerar novamente o pacote (desenvolvimento)

No computador de desenvolvimento, com Python **3.12 x64** e internet, execute:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\preparar_pacote.ps1
```

O script usa o [Python embeddable oficial](https://docs.python.org/3.12/using/windows.html#windows-embeddable),
valida o SHA-256 do ZIP, inclui as versoes de `requirements-portatil.txt`, valida
os imports e gera uma pasta e um ZIP em `Pacotes`. Tambem inclui o QZ oficial
validado por SHA-256. `.venv`, capturas, logs e perfis locais nao entram no pacote.
Um `runtime` existente e validado e reutilizado; para alterar suas bibliotecas,
renomeie essa pasta antes de gerar novamente. Guarde a pasta completa ou o ZIP
gerado para distribuir; copiar apenas os BATs nao e suficiente.

## Importante: resolucao da impressora

- Este pacote inicia com **203 dpi** porque o layout anterior de duas etiquetas usava o deslocamento `424 dots`, compativel com aproximadamente 53 mm em 8 dots/mm.
- O modelo fisico **DA300** e nominalmente **300 dpi**. Se os comandos do seu sistema forem de 300 dpi, execute `INICIAR_SIMULADOR.bat -Dpi 300` (com o simulador fechado). O tamanho fisico PDF segue o TSPL `SIZE` em ambas as opcoes; mudam as posicoes em dots.
- O arquivo de exemplo `exemplo_teste.prn` tem 103 x 30 mm, duas etiquetas lado a lado e textos/barcodes sinteticos.

## Teste manual sem o sistema

### Tamanho da etiqueta no PDF

O PDF respeita o `SIZE` recebido, sem adicionar margens ou incluir o `GAP`
na altura do papel. Ele solicita abertura em **100%** e impressao sem ajuste
automatico. O botao **Abrir PDF em 100%** tambem informa esse zoom ao navegador.
Novas impressoes mostram as medidas do papel no painel.

Uma faixa de **103 x 30 mm** contem duas etiquetas de **50 x 30 mm** e o vao
de **3 mm** entre elas; a pagina inteira nao corresponde a uma unica etiqueta.
Os layouts de ficha/lote com `SIZE 103 mm,40 mm` continuam com **103 x 40 mm**.
Nenhum conteudo e redimensionado ou recortado para remover areas brancas.

O painel oferece duas versoes do mesmo trabalho:

- **Ver etiquetas**: abre uma previa com papel branco, demarcacao escura fina e
  transparencia real no vao e nos cantos arredondados (raio visual de 1 mm).
  Alterne entre lado a lado e individuais, ajuste o zoom ou troque o fundo.
  O quadriculado do visualizador apenas indica transparencia, nao faz parte
  dos arquivos SVG e PNG. O PNG e gerado a ate 600 dpi; o SVG e vetorial.
- **PDF com demarcacao**: mantem o recorte visivel e as medidas do trabalho.
- **PDF individual**: uma etiqueta por pagina; no formato 103 x 30 mm,
  gera duas paginas de 50 x 30 mm por faixa.
- **PDF para imprimir**: apenas conteudo TSPL, sem contornos acrescentados.

O formato de duas etiquetas de 50 x 30 mm com vao de 3 mm usa como referencia
[este rolo real da Onix](https://www.onixetiquetas.com.br/etiquetas/automacao/6-rolos-de-etiqueta-50x30x2-couche-2-120-etiquetas-por-rolo).
O TSPL nao descreve o raio dos cantos: o recorte e uma referencia visual.
As celulas e o avanco das fontes residentes seguem o manual TSPL; os glifos sao
substitutos vetoriais com largura fixa para manter as medidas e a nitidez ao ampliar.
Codigos de barras tambem permanecem vetoriais. Nao ha textura, pixelizacao
artificial ou suporte bege. As posicoes do conteudo sao as do trabalho recebido.

Depois de atualizar os arquivos do simulador, feche sua janela e execute
`INICIAR_SIMULADOR.bat` novamente para carregar o novo conversor. PDFs antigos
permanecem como foram gerados; novas impressoes recebem as previas e os PDFs.

Se o leitor ainda ampliar, selecione **100% / Tamanho real**, em vez de
**Ajustar a pagina**. Na impressao, escolha **Tamanho real**, sem ajustar ao
papel. A medida aparente na tela depende da escala do Windows, do monitor e
do leitor; a medida fisica gravada no PDF continua sendo a do `SIZE`.

Com o simulador aberto, em **outro terminal PowerShell** na pasta do projeto:

```powershell
$dados = [System.IO.File]::ReadAllBytes((Resolve-Path '.\exemplo_teste.prn'))
$cliente = [System.Net.Sockets.TcpClient]::new('127.0.0.1', 19100)
$fluxo = $cliente.GetStream()
$fluxo.Write($dados, 0, $dados.Length)
$fluxo.Flush()
$cliente.Close()
```

Espere 1-2 segundos e consulte o painel. Isso valida o **conversor e a recepcao TCP**. Para validar a fila Windows/QZ Tray, imprima de fato pelo seu sistema.

## Comandos atuais

- Implementados: `SIZE`, `GAP` (parametro sem efeito no PDF), `REFERENCE`, `SHIFT`, `DIRECTION` e espelhamento, `CODEPAGE`, `CLS`, `PRINT`, `TEXT`, `BARCODE` (CODE128, CODE39; EAN13 aproximado), `BAR`, `BOX`, `CIRCLE`, `BITMAP` binario (modo OVERWRITE), `QRCODE`, e parametros gerais ignorados por nao alterarem a imagem. `OFFSET` e movimento de saida do papel, nao uma margem de texto.
- Limitacoes conhecidas: desenho substituto das fontes TSC; fontes baixadas nao fornecidas nao sao inventadas; `BITMAP` nos modos OR/XOR sem composicao fiel; `REVERSE` ainda nao suportado; comandos de logo/fontes descarregados na memoria da impressora; alguns codigos de barras; detalhes de HRI. Trabalhos sem `PRINT` nao geram PDF.
- Qualquer comando de desenho desconhecido gera um **aviso visivel no painel**. O `.prn` permite implementar compatibilidade exata sem tocar no sistema original.
- Limites de protecao: 50 MB por trabalho e 200 paginas por impressao. Nao automatiza exclusao de dados.

## Alcance e restricoes

Funciona quando o sistema procura a **fila instalada com este nome** e envia comandos de impressao RAW. **Nao simula um dispositivo USB fisico, identificadores USB (VID/PID), status completo/bidirecional da impressora ou descoberta de hardware**. Se o sistema exige uma impressora USB real, um driver proprietario especifico ou imprime por GDI/HTML/PDF (e nao TSPL), este metodo pode nao atender sem outra camada de conversao.

Esta fila usa **Generic / Text Only**, mas possui o nome **TSC DA300**. O QZ Tray aceita filas configuradas para impressao RAW; isso nao significa que ele converta um documento PDF em TSPL automaticamente.

Os PDFs podem conter dados pessoais/sensiveis dos pacientes. O programa fica restrito a `127.0.0.1`, nao acessa a internet para imprimir e salva as capturas **somente na pasta local**. Restrinja o acesso a essa pasta e remova os testes quando nao precisar mais deles.

## Desinstalacao

Execute `desinstalar_impressora.ps1` como administrador se desejar remover a fila e a porta especificas. **O script so remove a fila marcada como pertencente ao simulador**, e nao apaga PDFs nem altera outras impressoras.
O QZ Tray permanece instalado, pois pode ser usado por outros sites e impressoras.
Para remove-lo, use Aplicativos instalados do Windows.

## Solucao de problemas

- **No Python at ... / caminho de outro usuario**: era a `.venv` copiada de outro PC. Use o pacote portatil completo atualizado; a nova abertura usa apenas `runtime\python.exe` e nao tenta reparar ou executar aquela `.venv`.
- **Python do pacote ausente ou nao iniciou**: extraia o ZIP inteiro, incluindo `runtime`, em uma pasta local com permissao de escrita. Confira se o Windows e x64 e se o antivirus bloqueou algum arquivo. O erro deve ser resolvido antes de criar a fila ou abrir o QZ.
- **O site pede QZ Tray**: execute novamente `INSTALAR_IMPRESSORA.bat` como administrador e depois `INICIAR_SIMULADOR.bat` normalmente. Confira o icone do QZ junto ao relogio, atualize o site e autorize sua conexao se solicitado. Se continuar, confira a permissao de acesso a rede local do navegador para esse site e as mensagens exibidas pelo QZ.
- **Falha ao baixar o QZ**: confira a internet/proxy ou baixe pelo [site oficial](https://qz.io/download/) e instale manualmente. Depois execute novamente o instalador deste pacote. Uma falha nessa etapa nao e apresentada como instalacao concluida.
- **Nao aparece no sistema**: confira `Impressoras e scanners` e o nome exato; reinicie a enumeracao do QZ Tray ou a tela do sistema.
- **A impressao entra na fila mas nao aparece no painel**: confira que o simulador esta aberto e que a porta da fila e `TSC_DA300_VIRTUAL_19100` (`127.0.0.1:19100`).
- **Aparece um `.prn` mas nao um PDF**: pode ser um formato diferente de TSPL ou um trabalho sem `PRINT`; veja avisos e `simulador.log`.
- **PDF com elementos fora de lugar**: compare 203 e 300 dpi, e envie o `.prn` anonimo para expandir os comandos TSPL usados por seu sistema.
- **Ja existe TSC DA300 no Windows**: o instalador **nao renomeia nem substitui**. Remova ou renomeie manualmente apenas se souber que e a fila certa, e depois tente de novo.
